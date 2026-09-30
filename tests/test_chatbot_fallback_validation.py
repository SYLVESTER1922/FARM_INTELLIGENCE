"""
A narrow, deliberate second seam: chatbot/fallback.py's validate_llm_intent
directly, not the whole answer_question pipeline.

Why: this validates OUR closed-vocabulary check against a hand-constructed
"as if the LLM said this" dict - it's testing our own code, not the model's
behavior. Confirmed empirically (see ticket 04's notes) that GPT-4o-mini,
given the current extraction prompt, never actually hallucinates an unknown
query_id even under mild adversarial prompting - it either resolves
correctly or honestly declines. That means this specific branch can't be
reliably exercised through a live, unscripted API call, so a deterministic
unit test on the validation function is the only way to actually prove it -
agreed with the user before writing it, per the TDD skill's seam discipline.
"""

import datetime

from chatbot.catalog import CATALOG
from chatbot.fallback import validate_llm_intent


def test_validate_llm_intent_rejects_unknown_query_id():
    result = validate_llm_intent(
        {"query_id": "chicken_egg_report"}, CATALOG, tier1_reason="no_match"
    )

    assert result.query_id is None
    assert result.reason == "invalid_llm_intent"


def test_validate_llm_intent_preserves_tier1_reason_on_honest_decline():
    result = validate_llm_intent(
        {"query_id": None}, CATALOG, tier1_reason="ambiguous"
    )

    assert result.query_id is None
    assert result.reason == "ambiguous"


def test_validate_llm_intent_treats_missing_required_param_as_missing_parameter():
    result = validate_llm_intent(
        {"query_id": "feed_cost_split"},  # no "period" - genuinely absent, not hallucinated
        CATALOG,
        tier1_reason="missing_parameter",
    )

    assert result.query_id is None
    assert result.reason == "missing_parameter"


def test_validate_llm_intent_ignores_a_hallucinated_period_for_a_relative_phrase():
    # the real production bug: the model extracted period="October 2023"
    # for "this month" (its own training-era guess at "now," not this
    # project's real latest-data-date). When the ORIGINAL question names a
    # relative phrase, that hallucinated value must never be trusted -
    # resolved deterministically from anchor_date instead.
    result = validate_llm_intent(
        {"query_id": "feed_cost_split", "period": "October 2023"},
        CATALOG,
        tier1_reason="no_match",
        question="how does feed cost split between pigs and chickens this month",
        anchor_date=datetime.date(2026, 9, 15),
    )

    assert result.query_id == "feed_cost_split"
    assert result.params == {"period_start": "2026-09-01", "period_end": "2026-10-01"}


def test_validate_llm_intent_still_trusts_an_explicit_llm_extracted_period():
    # no relative phrase in the question - the pre-existing "explicit
    # Month Year" path must keep working unchanged.
    result = validate_llm_intent(
        {"query_id": "feed_cost_split", "period": "January 2026"},
        CATALOG,
        tier1_reason="no_match",
        question="how does feed cost split between pigs and chickens in January 2026",
        anchor_date=datetime.date(2026, 9, 15),
    )

    assert result.query_id == "feed_cost_split"
    assert result.params == {"period_start": "2026-01-01", "period_end": "2026-02-01"}
