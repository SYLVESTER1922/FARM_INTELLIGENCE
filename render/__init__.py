"""
Templated answers (spec-chatbot-v2-plan.md, decision D5). Every answer has the same fixed layout, filled from a
structured registry Result and the resolver's Resolution - no LLM writes any of it:

    line 1      the echoed scope: metric, domains, period (and how the period was chosen)
    then        the figure(s), with the per-domain / per-category breakdown, every row, largest first
    then        notes the result carries (the denominator, the days used), a coverage note, "Data through <date>.",
                and the "Say 'all time' ..." hint when the dashboard filter changed the answer

The LLM's only roles are mapping the question to a metric and scope, and the later exploratory lane.
"""

import re
from dataclasses import dataclass

from registry import REGISTRY, Result, label
from render import format as fmt
from render.constants import ALL_TIME_HINT, GREETING, SIGN_OFF  # noqa: F401
from render.templates import NO_DOMAIN_IN_ECHO, TEMPLATES, TITLES
from render.tracking import Touch


@dataclass
class RenderContext:
    currency: str = "USD"                  # farm_profile.currency
    data_through: object = None            # date of the last good sync snapshot; defaults to the result's last record
    all_time_result: Result = None         # the same question with no period, to decide whether the filter hint applies

    def money(self, x, nd=2):
        return fmt.money(x, self.currency, nd)


_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def _human_dates(text):
    """The registry's messages carry ISO dates ("latest record is 2026-09-15"); answers show 15 Sep 2026 throughout."""
    return _ISO_DATE.sub(lambda m: fmt.date(m.group(1)), text)


def _domains_text(metric, result):
    scope = result.scope
    if metric.id in NO_DOMAIN_IN_ECHO:
        return ""
    if scope.batch_code:
        return f"batch {scope.batch_code}"
    if scope.domains:
        return fmt.join_names(label(d) for d in scope.domains)
    return "all domains" if len(metric.domains) > 1 else label(metric.domains[0])


def _period_text(metric, resolution, result, fig, ctx):
    cov = result.coverage
    if result.ok and "as_of" in result.figures:
        return f"as of {fmt.date(fig['as_of'])}"
    if result.ok and "rainfall_mm" in result.figures:
        return f"latest logged day, {fmt.date(fig['date'])}"
    if metric.period == "none":
        return "as they stand now"
    if resolution.period_source == "all_time":
        return f"all recorded time (since {fmt.date(cov.first_record)})" if cov.first_record else "all recorded time"
    if resolution.period_source == "snapshot":
        d = ctx.data_through or cov.last_record
        return f"as of {fmt.date(d)}" if d else "now"
    return resolution.period_label or ""


def render_traced(resolution, result: Result, ctx: RenderContext = None):
    """(text, touch). `touch` records which result fields the template read, for the completeness test."""
    ctx = ctx or RenderContext()
    touch = Touch()
    fig, rows = touch.figures(result.figures), touch.rows(result.rows)
    metric = REGISTRY[result.metric_id]

    if result.ok:
        suffix, lines = TEMPLATES[result.metric_id](result, fig, rows, ctx)
    else:
        suffix, lines = "", [_human_dates(result.message)]

    echo = ", ".join(x for x in (TITLES[result.metric_id] + suffix, _domains_text(metric, result),
                                 _period_text(metric, resolution, result, fig, ctx)) if x)
    out = [echo] + lines + [_human_dates(n) for n in result.notes]

    cov, scope = result.coverage, result.scope
    if result.ok and cov.partial and cov.days_covered and scope.start and scope.end:
        total = (scope.end - scope.start).days + 1
        out.append(f"Only {fmt.num(cov.days_covered)} of the {fmt.num(total)} days in this period have records "
                   f"(records run {fmt.date(cov.first_record)} to {fmt.date(cov.last_record)}).")
    through = ctx.data_through or (cov.last_record if result.ok else None)
    if through:
        out.append(f"Data through {fmt.date(through)}.")
    if (resolution.offer_all_time_hint and result.ok and ctx.all_time_result is not None and ctx.all_time_result.ok
            and ctx.all_time_result.figures != result.figures):
        out.append(ALL_TIME_HINT)
    return "\n".join(out), touch


def render(resolution, result: Result, ctx: RenderContext = None) -> str:
    return render_traced(resolution, result, ctx)[0]


def render_refusal(resolution) -> str:
    """A named refusal from the resolver (unresolved period, domain, comparison...): its message, nothing else."""
    return resolution.unresolved.message
