"""
Tier-2 LLM fallback: one OpenAI call to extract structured intent when the
tier-1 deterministic matcher can't. The LLM's output is validated against
the exact same closed vocabularies (catalog query_ids, parameter parsing)
tier 1 uses before it's ever trusted - see spec-chatbot-answer-engine.md's
"Tier 2 - LLM fallback" decision. No retry: a validation miss here is a
single, final failure.
"""

import json

from chatbot.matcher import PARAM_EXTRACTORS, MatchResult


def _catalog_summary(catalog: list) -> str:
    lines = []
    for entry in catalog:
        needs = ", ".join(entry.required_params) or "nothing"
        lines.append(f'- "{entry.query_id}": e.g. "{entry.phrases[0]}" (needs: {needs})')
    return "\n".join(lines)


def _extraction_prompt(question: str, catalog: list) -> str:
    return (
        "You extract structured intent from a farm-management question, for "
        "a fixed catalog of known query types. Respond with ONLY a JSON "
        "object, no other text.\n\n"
        f"Known query types:\n{_catalog_summary(catalog)}\n\n"
        'If the question matches one of these, respond with '
        '{"query_id": "<the matching query_id>", '
        '"period": "<Month Year, only if that query needs a period>"}.\n'
        'If nothing fits, respond with {"query_id": null}.\n\n'
        f"Question: {question}"
    )


def llm_extract_intent(question: str, catalog: list, openai_client) -> dict | None:
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": _extraction_prompt(question, catalog)}],
        response_format={"type": "json_object"},
        max_tokens=100,
    )
    try:
        return json.loads(response.choices[0].message.content)
    except (json.JSONDecodeError, TypeError):
        return None


def validate_llm_intent(raw: dict | None, catalog: list, tier1_reason: str) -> MatchResult:
    """`tier1_reason` is preserved when the LLM honestly declines (no
    query_id at all) - that's not an invalid response, just confirmation of
    tier 1's own assessment. `invalid_llm_intent` is reserved for the LLM
    actively naming an unknown query_id - not a query_id that's valid but
    whose required parameter genuinely isn't present in the question (that's
    still a missing_parameter, same root cause as tier 1's own version of it,
    just confirmed at this tier instead)."""
    if not raw or not raw.get("query_id"):
        return MatchResult(query_id=None, reason=tier1_reason)

    entry = next((e for e in catalog if e.query_id == raw["query_id"]), None)
    if entry is None:
        return MatchResult(query_id=None, reason="invalid_llm_intent")

    params = {}
    for param_name in entry.required_params:
        raw_value = raw.get(param_name)
        if raw_value is None:
            return MatchResult(query_id=None, reason="missing_parameter")
        extracted = PARAM_EXTRACTORS[param_name](raw_value)
        if extracted is None:
            return MatchResult(query_id=None, reason="missing_parameter")
        params.update(extracted)

    return MatchResult(query_id=entry.query_id, params=params)
