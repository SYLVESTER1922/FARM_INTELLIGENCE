"""
The cross-check (plan section 6): the LLM's spec against what the deterministic code reads from the SAME words. The scope resolver
reads the period, the domain lexicon reads the domains, a small cue table reads the direction of the money and the verb. Where they
disagree there is no silent pick: the answer is a clarifying question with numbered options (or a named refusal), logged with a
reason code. Pure code, no database, no LLM.
"""

import re
from dataclasses import dataclass, field

from catalog.untracked import KNOWN
from registry import REGISTRY, label
from render.templates import TITLES
from resolver.periods import has_all_time_words, normalise

NOW_WORDS = {"today", "now", "currently", "current", "right now", "at the moment"}


@dataclass
class Disagreement:
    code: str                    # domain | period | all_time | aggregation | metric
    message: str                 # the clarifying question, with numbered options
    options: list = field(default_factory=list)     # the labels shown
    values: list = field(default_factory=list)      # what each option means, in the same order (applied when the user replies 1, 2, ...)


def _numbered(question, options):
    lines = [question] + [f"{i}) {o}" for i, o in enumerate(options, 1)]
    return "\n".join(lines) + f"\nReply {' or '.join(str(i) for i in range(1, len(options) + 1))}."


def option(metric_id):
    """One numbered option for a metric: the name the answers use, then what it answers."""
    return f"{TITLES[metric_id]}: {REGISTRY[metric_id].answers}"


def _normalise_domains(domains, metric):
    """Naming everything the metric covers is the same as naming nothing."""
    if not domains:
        return None
    return None if set(metric.domains) <= set(domains) else tuple(domains)


def _names(domains):
    return " and ".join(label(d) for d in domains)


# ---------------------------------------------------------------------------------------------------- metric cues
# (pattern, metrics that are acceptable when the pattern is present). A deterministic second opinion on direction and verb.
_CUES = [
    (re.compile(r"\b(owes? us|owing us|owed (?:to )?us|owe me|owing me|owes me|still owing|debtors?|haven'?t paid|not paid|unpaid)\b"),
     {"receivables"}),
    (re.compile(r"\b(bought|buy|buying|purchased?|purchases)\b.*\bfeed\b|\bfeed\b.*\b(bought|buy|buying|purchased?|purchases)\b"),
     {"feed_purchases"}),
    (re.compile(r"\b(died|dead|deaths?|mortality|dying)\b"), {"mortality"}),
    (re.compile(r"\b(feed conversion|fcr)\b"), {"fcr"}),
    (re.compile(r"\b(profit|profitable|making money)\b"), {"profit"}),
    (re.compile(r"\b(rain|rainfall|temperature|weather|humidity)\b"), {"weather"}),
    (re.compile(r"\bsows?\b"), {"sow_count", "breeding", "mortality", "health_events"}),
]
# Words that ask for a breakdown or a ranking. A dimension on the spec without any of them is the model adding a breakdown nobody asked for.
_BREAKDOWN_CUES = re.compile(r"\b(by|per|each|every|split|splits|breakdown|break down|broken down|which|who|whom|worst|best|highest|lowest|"
                            r"biggest|largest|top|most|least|compare|comparison|versus|vs|rank|ranking|ranked)\b")

# A named refusal that says "this is not tracked" must be backed by the user's own words; a model alone never gets to say it (plan
# section 4). If the words are not there the answer is a question, not a claim.
_REFUSAL_WORDS = {u.code: u.cues for u in KNOWN if u.cues is not None}
# Treatment wording: "being treated for illness" is a question about logged treatment events as much as about sickness now.
_TREATMENT_WORDS = re.compile(r"\b(treat\w*|vaccin\w*|medicat\w*|vet|vets|injected|dosed)\b")


def refusal_supported(code: str, question: str) -> bool:
    """True when the user's own words back a model-chosen named refusal. out_of_scope needs no support: it claims nothing."""
    t = normalise(question)
    if code == "accounts_payable":
        return accounts_payable_wording(question)
    rx = _REFUSAL_WORDS.get(code)
    return True if rx is None else bool(rx.search(t))


def sickness_vs_treatment(question: str) -> bool:
    t = normalise(question)
    return bool(_REFUSAL_WORDS["current_sickness"].search(t) and _TREATMENT_WORDS.search(t))


# Money the farm OWES others is not tracked. If the wording says so, the answer is that named refusal whatever the model picked.
_ACCOUNTS_PAYABLE = re.compile(r"\b(do we owe|are we owing|we owe|what we owe|who do we owe|bills (?:we|to) pay|owe (?:our |the )?suppliers?|"
                               r"bills?\b.*\bto pay|(?:pay|paying) (?:our |the )?(?:suppliers?|creditors?|bills))\b")

# A refusal the wording does not back, or that reads two ways, becomes a question between the nearest tracked metric and "not tracked".
NEAR_METRIC = {u.code: u.near_metric for u in KNOWN if u.near_metric}
NOT_TRACKED_OPTION = {u.code: u.option for u in KNOWN if u.near_metric}


_STAFF_PAY = re.compile(
    r"\b(pay rates?|rates? of pay|hourly rates?|daily rates?|salary (?:of|for)|\w+ s (?:salary|wage|pay)|"
    r"(?:salary|salaries|wages?|pay|paid|earns?|earnings?)\b.{0,40}\b(?:each|every|per|individual|which|any) (?:worker|employee|staff|person|labourer)|"
    r"(?:each|every|per|individual|which|any) (?:worker|employee|staff|person|labourer)\b.{0,40}\b(?:salary|salaries|wages?|pay|paid|earns?|earnings?)|"
    r"(?:how much|what) (?:does|do|is|are) (?!we\b|our\b|the farm\b)[a-z' ]{1,30}(?:earn|get paid|gets paid))\b")


def staff_pay_wording(question: str) -> bool:
    """Per-person pay is withheld by policy (plan 24.2): wording that asks what an individual is paid is refused whatever the model
    picked. Totals ("total salaries this month", "wages spent") are labour cost and are not matched."""
    return bool(_STAFF_PAY.search(normalise(question)))


def accounts_payable_wording(question: str) -> bool:
    return bool(_ACCOUNTS_PAYABLE.search(normalise(question)))


# Money spent on feed, with nothing saying whether it was bought or eaten: the prompt's rule, enforced here so a model cannot answer it
# silently as one or the other (or as an expense category). "feed cost" alone is the consumed cost and is not asked about.
_FEED_WORD = re.compile(r"\b(feed|feeds|chikafu|ukudla)\b")
_SPEND_WORD = re.compile(r"\b(spend|spent|spending|expense|expenses|expenditure|paid|pay|paying)\b")
_FEED_CLEAR = re.compile(r"\b(bought|buy|buying|purchas\w*|fed|feeding|eat|eaten|ate|used|use|consum\w*)\b")
FEED_PAIR = ("feed_consumed_cost", "feed_purchases")


def feed_spend_unclear(question) -> bool:
    t = normalise(question)
    return bool(_FEED_WORD.search(t) and _SPEND_WORD.search(t) and not _FEED_CLEAR.search(t))


def metric_disagreement(question, spec):
    t = normalise(question)
    if spec.metric in ("expenses", *FEED_PAIR) and feed_spend_unclear(question):
        ids = list(FEED_PAIR)
        return Disagreement("metric", _numbered("I can read that more than one way. Do you mean:", [option(m) for m in ids]),
                            [option(m) for m in ids], ids)
    for rx, allowed in _CUES:
        if rx.search(t) and spec.metric and spec.metric not in allowed:
            return Disagreement(
                "metric",
                _numbered("I want to be sure I read that right. Do you mean:",
                          [option(spec.metric)] +
                          [option(m) for m in sorted(allowed)][:2]),
                [spec.metric, *sorted(allowed)[:2]], [spec.metric, *sorted(allowed)[:2]])
    return None


# ---------------------------------------------------------------------------------------------------- scope cues
def check(question, spec, metric, resolution, dashboard_filter=None) -> list:
    """Every disagreement between the spec and the deterministic reading (empty list = they agree). `resolution` is the
    resolver's Resolution for this metric, already known to be ok."""
    out = []
    snapshotish = metric.period in ("snapshot", "none") or metric.snapshot_default

    # ---- domains: the lexicon (resolver) vs the model
    if not resolution.scope.batch_code:                      # a batch code names its domain; ignore the model's inference
        lexicon = resolution.scope.domains if resolution.domain_source == "named" else None
        model = _normalise_domains(spec.domains, metric)
        if lexicon != model:
            readings = [d for d in (lexicon, model) if d]
            readings = list(dict.fromkeys(readings))
            opts = [_names(r) for r in readings] + ["All sections of the farm"]
            out.append(Disagreement("domain", _numbered("Which part of the farm do you mean?", opts), opts, [*readings, ()]))

    # ---- period: the resolver's reading vs the phrase the model copied
    phrase = spec.period_phrase
    if phrase and snapshotish and normalise(phrase) in NOW_WORDS:
        phrase = None
    named = resolution.period_source == "question"
    if named and not phrase:
        opts = [resolution.period_label, "All recorded time"]
        out.append(Disagreement("period", _numbered("Which period do you mean?", opts), opts, ["question", "all_time"]))
    elif phrase and not named:
        out.append(Disagreement(
            "period", f"I couldn't work out '{phrase}' as a period. Could you name it another way, for example "
                      f"'last month', 'March 2026' or 'year to date'?", []))

    # ---- explicit all-time words. Only a dashboard date filter makes this matter: with no filter, a question that names no period is
    # answered for all recorded time whatever the model thought, so asking would be a pointless question.
    if dashboard_filter and not snapshotish and not named and spec.all_time != has_all_time_words(question):
        opts = ["All recorded time", "The dashboard's date range"]
        out.append(Disagreement("all_time", _numbered("Do you mean:", opts), opts, ["all_time", "filter"]))

    # ---- a breakdown nobody asked for
    # (by section is every multi-section metric's default view, and a batch code already names the breakdown: neither can change the headline)
    if (spec.dimension and spec.dimension != "domain" and not resolution.scope.batch_code
            and not _BREAKDOWN_CUES.search(normalise(question))):
        opts = ["The total", f"Broken down by {spec.dimension}"]
        out.append(Disagreement("dimension", _numbered("Do you want:", opts), opts, [None, spec.dimension]))

    # ---- aggregation and grain
    if (spec.aggregation or "total") != resolution.scope.aggregation or spec.grain != resolution.scope.grain:
        opts = ["The total", "The average per week", "Month by month"]
        out.append(Disagreement("aggregation", _numbered("How should I show it?", opts), opts,
                                [("total", None), ("avg_per_week", None), ("total", "month")]))
    return out
