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
