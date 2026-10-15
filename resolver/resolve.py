"""
The scope resolver (spec-chatbot-v2-plan.md, section 5; decisions D2 to D6). Turns the user's raw words, the
dashboard filter and the farm profile into a typed Scope that every registry metric takes. Pure code: no LLM, no
database, so every rule is exactly testable. When it cannot resolve something it says so (Unresolved) and never
guesses.

Period precedence, in order:
  1. a period named in the question wins (period_source "question"); the filter is ignored for that question
  2. explicit scope words ("all time", "overall", "ever", "since we started") override the filter (rule 2): all_time
  3. no period named and a filter set: the filter applies (period_source "filter")
  4. no period named and no filter: all recorded time (period_source "all_time")
  5. snapshot questions (headcount, stock on hand, balances) use the latest data date and ignore the filter
     (period_source "snapshot"); naming a past date sets as_of to the end of that period.
"""

import datetime as dt
import re
from dataclasses import dataclass, field

from registry.core import DOMAIN_LABELS, Metric, Scope
from resolver.lexicon import domain_words_in, find_batch_code
from resolver.periods import (
    Period, comparison_cue, extract_periods, fmt_range, has_all_time_words, normalise, unsupported_period_phrase,
)


@dataclass
class Unresolved:
    code: str          # unsupported_period | multiple_periods | month_without_year | period_not_supported |
                       # domain_unsupported | module_off | unsupported_aggregation
    message: str       # what to tell the user; they can act on it
    detail: dict = field(default_factory=dict)


@dataclass
class Resolution:
    metric_id: str
    scope: Scope
    period_source: str                  # question | filter | all_time | snapshot
    period_label: str = None            # "August 2026", "last month (September 2026)", "1–31 Aug 2026 (dashboard date filter)"
    all_time_reason: str = None         # explicit_words | no_period (when period_source == all_time)
    domain_source: str = "default_all"  # named | default_all | single_module | active_modules
    domain_words: tuple = ()
    filter_applied: bool = False
    offer_all_time_hint: bool = False   # the answer layer adds "Say 'all time' to ignore the dashboard filter."
                                        # when the filter changed the answer (it compares against the all-time result)
    unresolved: Unresolved = None
    notes: list = field(default_factory=list)

    @property
    def ok(self):
        return self.unresolved is None


def all_time_scope(scope: Scope) -> Scope:
    """The same question with the period removed: used to check whether the dashboard filter changed the answer."""
    return scope.with_(start=None, end=None, as_of=None, period_source="all_time")


def _fail(metric, code, message, **detail):
    return Resolution(metric.id, Scope(), "all_time", unresolved=Unresolved(code, message, detail))


# ------------------------------------------------------------------------------------------------ aggregation and grain
_AVG = re.compile(r"\b(average|avg|mean|typical)\b")
_WEEK = re.compile(r"\b(weekly|per week|a week|each week|every week|by week)\b")
_MONTH = re.compile(r"\b(monthly|per month|a month|each month|every month|by month|month by month|month on month)\b")
_DAY = re.compile(r"\b(per day|a day|each day|every day|day by day|daily(?! logs?))\b")


def _aggregation_and_grain(text):
    t = normalise(text)
    avg, week, month, day = _AVG.search(t), _WEEK.search(t), _MONTH.search(t), _DAY.search(t)
    if avg and week:
        return "avg_per_week", None, None
    if avg and (month or day):
        unit = "month" if month else "day"
        return None, None, Unresolved("unsupported_aggregation",
                                      f"I can give an average per week, not an average per {unit}.", {"unit": unit})
    if week:
        return None, None, Unresolved("unsupported_aggregation",
                                      "I can give an average per week, or totals month by month; I can't split by week.",
                                      {"unit": "week"})
    if day:
        return None, None, Unresolved("unsupported_aggregation",
                                      "I can't split figures by day.", {"unit": "day"})
    if month:
        return "total", "month", None
    return "total", None, None


# ------------------------------------------------------------------------------------------------ domains
def _domains(metric: Metric, text, modules):
    named, words = domain_words_in(text)
    supported = tuple(metric.domains)
    modules = modules or {}
    active = lambda d: d == "shared" or modules.get(d, True)

    if named:
        bad = [d for d in named if d not in supported]
        if bad:
            names = " and ".join(DOMAIN_LABELS[d].lower() for d in bad)
            return None, "named", words, Unresolved(
                "domain_unsupported", f"I can't give {metric.title} for {names}: it isn't tracked that way.",
                {"domains": bad})
        off = [d for d in named if not active(d)]
        if off:
            return None, "named", words, Unresolved(
                "module_off", f"The {off[0]} module is turned off for this farm - turn it on in the farm profile to ask about that.",
                {"domain": off[0]})
        if set(supported) <= set(named):
            return None, "named", words, None            # names everything the metric covers: same as default
        return tuple(named), "named", words, None

    on = tuple(d for d in supported if active(d))
    if supported and not on:
        return None, "default_all", words, Unresolved(
            "module_off", "None of the modules this needs are turned on for this farm.", {})
    if set(on) != set(supported):
        return on, ("single_module" if len(on) == 1 else "active_modules"), words, None
    return None, "default_all", words, None


# ------------------------------------------------------------------------------------------------ the resolver
def resolve(question: str, metric: Metric, *, today: dt.date, dashboard_filter=None, modules=None,
            week_start: int = 0) -> Resolution:
    """`dashboard_filter` is (date_from, date_to) or None; `modules` maps domain to active flag (default all on);
    `week_start` is the farm's first weekday (0 = Monday), from the per-farm setting."""
    bad = unsupported_period_phrase(question)
    if bad:
        return _fail(metric, "unsupported_period",
                     f"I can't work out '{bad}'. Try a month like 'March 2026', or 'last month', 'last 30 days', "
                     f"'this year', 'year to date'.", phrase=bad)

    periods, bare = extract_periods(question, today, week_start)

    # A comparison of periods ("vs last month", "same day last month compared to today") is a named refusal in v1.
    # Without this the comparison words are dropped and ONE of the periods is answered as if it were the question.
    cue = comparison_cue(question)
    named_count = len({(p.start, p.end) for p in periods}) + len(bare)
    if (cue == "period" and named_count >= 1) or (cue == "weak" and named_count >= 2):
        return _fail(metric, "comparison_not_supported",
                     "I can't compare two periods yet. Ask for each one separately, for example "
                     "'feed cost last month' and 'feed cost this month'.", periods=[p.label for p in periods])

    snapshotish = metric.period in ("snapshot", "none") or metric.snapshot_default
    if snapshotish:
        periods = [p for p in periods if p.label != "today"]       # "how many pigs today" is just "now"
    distinct = list({(p.start, p.end): p for p in periods}.values())
    if len(distinct) > 1 or (distinct and bare):
        return _fail(metric, "multiple_periods",
                     "That names more than one period. Which one do you want first? I can answer one period at a time.",
                     periods=[p.label for p in distinct])
    if bare and not distinct:
        month = bare[0].word.capitalize()
        return _fail(metric, "month_without_year", f"Which year do you mean for {month}? For example, \"{month} {today.year}\".",
                     month=bare[0].month)
    named: Period = distinct[0] if distinct else None

    domains, domain_source, words, bad_domain = _domains(metric, question, modules)
    if bad_domain:
        return Resolution(metric.id, Scope(), "all_time", domain_source=domain_source, domain_words=words,
                          unresolved=bad_domain)

    agg, grain, bad_agg = _aggregation_and_grain(question)
    if bad_agg is None and agg not in metric.aggregations:
        bad_agg = Unresolved("unsupported_aggregation", f"I can't give an average per week for {metric.title}.", {})
    if bad_agg is None and grain and grain not in metric.grains:
        bad_agg = Unresolved("unsupported_aggregation", f"I can't split {metric.title} month by month.", {})
    if bad_agg:
        return Resolution(metric.id, Scope(), "all_time", domain_source=domain_source, domain_words=words, unresolved=bad_agg)

    batch = find_batch_code(question)
    base = dict(domains=domains, aggregation=agg or "total", grain=grain, batch_code=batch)
    common = dict(metric_id=metric.id, domain_source=domain_source, domain_words=words)

    # ---- metrics with no period at all (batch count, sow count): always "now"
    if metric.period == "none":
        if named:
            return Resolution(**common, scope=Scope(**base, period_source="snapshot"), period_source="snapshot",
                              unresolved=Unresolved("period_not_supported",
                                                    f"{metric.title.capitalize()} are only available as they stand now, "
                                                    f"not for a past period.", {"period": named.label}))
        return Resolution(**common, scope=Scope(**base, period_source="snapshot"), period_source="snapshot")

    # ---- snapshot metrics (headcount, weight, stock, market readiness): latest data date, filter ignored (rule 5)
    if metric.period == "snapshot":
        if named:
            as_of = min(named.end, today)
            return Resolution(**common, scope=Scope(**base, as_of=as_of, period_source="question"),
                              period_source="question", period_label=f"as of {as_of}")
        return Resolution(**common, scope=Scope(**base, period_source="snapshot"), period_source="snapshot")

    # ---- range metrics
    if named:                                                                         # rule 1
        return Resolution(**common, scope=Scope(**base, start=named.start, end=named.end, period_source="question"),
                          period_source="question", period_label=named.label)

    if metric.snapshot_default:                                                       # weather with no period: latest
        return Resolution(**common, scope=Scope(**base, period_source="snapshot"), period_source="snapshot")

    if has_all_time_words(question):                                                  # rule 2
        return Resolution(**common, scope=Scope(**base, period_source="all_time"), period_source="all_time",
                          all_time_reason="explicit_words")

    if not metric.uses_filter:                                                        # a balance: ignores the filter
        return Resolution(**common, scope=Scope(**base, period_source="snapshot"), period_source="snapshot")

    f_start, f_end = dashboard_filter if dashboard_filter else (None, None)
    if f_start or f_end:                                                              # rule 3
        label = fmt_range(f_start, f_end) if (f_start and f_end) else (
            f"up to {f_end}" if f_end else f"from {f_start}")
        return Resolution(**common, scope=Scope(**base, start=f_start, end=f_end, period_source="filter"),
                          period_source="filter", period_label=f"{label} (dashboard date filter)",
                          filter_applied=True, offer_all_time_hint=True)

    return Resolution(**common, scope=Scope(**base, period_source="all_time"), period_source="all_time",   # rule 4
                      all_time_reason="no_period")
