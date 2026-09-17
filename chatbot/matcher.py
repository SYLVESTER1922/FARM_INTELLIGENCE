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
    if not phrase_tokens:
        return 0.0
    return len(question_tokens & phrase_tokens) / len(phrase_tokens)


def _best_score(question: str, catalog_entry) -> float:
    question_tokens = _tokenize(question)
    return max(_overlap(question_tokens, _tokenize(p)) for p in catalog_entry.phrases)


def extract_period(question: str) -> dict | None:
    """Look for an explicit '<Month> <Year>' phrase, e.g. 'January 2026'."""
    match = re.search(
        r"\b(" + "|".join(MONTH_NAMES) + r")\s+(\d{4})\b", question.lower()
    )
    if not match:
        return None
    month = MONTH_NAMES[match.group(1)]
    year = int(match.group(2))
    start = f"{year:04d}-{month:02d}-01"
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    end = f"{next_year:04d}-{next_month:02d}-01"
    return {"period_start": start, "period_end": end}


PARAM_EXTRACTORS = {"period": extract_period}


def match(question: str, catalog: list) -> MatchResult:
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
        extracted = PARAM_EXTRACTORS[param_name](question)
        if extracted is None:
            return MatchResult(query_id=None, reason="missing_parameter")
        params.update(extracted)

    return MatchResult(query_id=top_entry.query_id, params=params)
