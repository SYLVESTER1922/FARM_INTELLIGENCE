"""
Tier-1 deterministic concept-cluster matcher. Pure Python, no ML
dependency, no network call. See spec-chatbot-answer-engine.md's
"Tier 1" decision.
"""

import calendar
import re
from dataclasses import dataclass, field

MATCH_THRESHOLD = 0.6

MONTH_NAMES = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}


@dataclass
class MatchResult:
    query_id: str | None
    params: dict = field(default_factory=dict)
    reason: str | None = None  # None on success; else no_match/ambiguous/missing_parameter


def _tokenize(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _overlap(question_tokens: set, phrase_tokens: set) -> float:
    """Jaccard similarity (intersection / union), not recall-on-phrase-only
    (intersection / phrase length). A real bug found via a QA pass: recall
    let a short, generic-template phrase ("which X has the worst Y") score
    high against ANY question sharing that template regardless of what Y
    actually was - "which batch has the worst feed conversion ratio"
    scored 0.714 against "which poultry batch has the worst mortality"
    (5 of the phrase's 7 tokens matched, template words only - "mortality"
    itself was irrelevant to the score), clearing the 0.6 threshold and
    mismatching FCR questions to a mortality catalog entry. Jaccard scores
    the same case at 0.5 (5 shared / 10 total distinct tokens across
    both), correctly below threshold, while every exact-phrase match in
    this catalog still scores a full 1.0 exactly as before (intersection
    == union when the texts are identical) - verified against the full
    test suite, zero regressions."""
    if not phrase_tokens:
        return 0.0
    union = question_tokens | phrase_tokens
    if not union:
        return 0.0
    return len(question_tokens & phrase_tokens) / len(union)


def _best_score(question: str, catalog_entry) -> float:
    question_tokens = _tokenize(question)
    return max(_overlap(question_tokens, _tokenize(p)) for p in catalog_entry.phrases)


def _month_bounds(year: int, month: int) -> tuple:
    start = f"{year:04d}-{month:02d}-01"
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    end = f"{next_year:04d}-{next_month:02d}-01"
    return start, end


_RELATIVE_PERIOD_PHRASES = ("this month", "last month")


def mentions_relative_period(question: str) -> bool:
    """Cheap, deterministic pre-check so a caller (chatbot/engine.py) only
    pays for the real anchor-date lookup (a DB query) when a question could
    actually use it - most questions never mention a relative period at
    all, and some minimal test fixtures don't even have the tables that
    query touches."""
    q = question.lower()
    return any(phrase in q for phrase in _RELATIVE_PERIOD_PHRASES)


def extract_relative_period(question: str, anchor_date) -> dict | None:
    """Resolves "this month"/"last month" using `anchor_date` (the real
    latest logged data date, supplied by the caller - matcher.py has no DB
    access, matching date_filter_sql's existing DB-agnostic placement here)
    as "today," never the calendar date and never an LLM's own guess. A
    real bug found in production: tier-2's LLM-extracted period for "how
    does feed cost split... this month" came back as "October 2023" - the
    model's own training-era notion of "now," off by years, not this
    project's real latest-data-date concept. Checked *before* ever trusting
    an LLM-extracted period string for relative language, in both
    chatbot/matcher.py's own tier-1 dispatch and chatbot/fallback.py's
    tier-2 validation - the same "the LLM never computes a relative date
    itself" principle already applied to q_mortality_rate's symbolic period
    enum (chatbot/tools.py), extended to tier-1/2's free-text period
    parameter instead of a closed enum, since feed_cost_split predates that
    design and still takes a free-text period."""
    q = question.lower()
    if "this month" in q:
        start, end = _month_bounds(anchor_date.year, anchor_date.month)
        return {"period_start": start, "period_end": end}
    if "last month" in q:
        month = anchor_date.month - 1 or 12
        year = anchor_date.year if anchor_date.month > 1 else anchor_date.year - 1
        start, end = _month_bounds(year, month)
        return {"period_start": start, "period_end": end}
    return None


def extract_period(question: str, anchor_date=None) -> dict | None:
    """Look for an explicit '<Month> <Year>' phrase, e.g. 'January 2026' -
    unchanged, and checked first, so an explicit month always wins over a
    relative phrase if a question somehow named both. Falls back to
    extract_relative_period only when `anchor_date` is given (kept optional
    so any existing caller that doesn't pass one - e.g. a direct unit test -
    behaves exactly as before)."""
    match = re.search(
        r"\b(" + "|".join(MONTH_NAMES) + r")\s+(\d{4})\b", question.lower()
    )
    if match:
        month = MONTH_NAMES[match.group(1)]
        year = int(match.group(2))
        start, end = _month_bounds(year, month)
        return {"period_start": start, "period_end": end}
    if anchor_date is not None:
        return extract_relative_period(question, anchor_date)
    return None


PARAM_EXTRACTORS = {"period": extract_period}


def match(question: str, catalog: list, anchor_date=None) -> MatchResult:
    """`anchor_date` (the real latest logged data date) is optional and
    threaded straight through to extract_period, so a relative period
    phrase ("this month") can be resolved without the calendar date or an
    LLM ever entering the picture - see extract_relative_period above."""
    scored = sorted(
        ((_best_score(question, entry), entry) for entry in catalog),
        key=lambda pair: -pair[0],
    )
    top_score, top_entry = scored[0]
    if top_score < MATCH_THRESHOLD:
        return MatchResult(query_id=None, reason="no_match")

    if len(scored) > 1:
        second_score = scored[1][0]
        if second_score >= MATCH_THRESHOLD:
            return MatchResult(query_id=None, reason="ambiguous")

    params = {}
    for param_name in top_entry.required_params:
        extracted = PARAM_EXTRACTORS[param_name](question, anchor_date=anchor_date)
        if extracted is None:
            return MatchResult(query_id=None, reason="missing_parameter")
        params.update(extracted)

    return MatchResult(query_id=top_entry.query_id, params=params)
