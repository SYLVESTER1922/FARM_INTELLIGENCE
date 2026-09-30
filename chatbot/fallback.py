"""
Tier-2 LLM fallback: one OpenAI call to extract structured intent when the
tier-1 deterministic matcher can't. The LLM's output is validated against
the exact same closed vocabularies (catalog query_ids, parameter parsing)
tier 1 uses before it's ever trusted - see spec-chatbot-answer-engine.md's
"Tier 2 - LLM fallback" decision. No retry: a validation miss here is a
single, final failure.
"""

import json

from chatbot.matcher import PARAM_EXTRACTORS, MatchResult, extract_relative_period


def _catalog_summary(catalog: list) -> str:
    """Shows up to 2 example phrases per entry, not just the first - a
    single example gave too little context to correctly reject a
    direction-sensitive but vocabulary-overlapping question (a real,
    reproducible case: "are we owing anyone" was matched to crop_debtor,
    which tracks money owed *to* the farm, not the reverse - see that
    entry's own phrase-ordering comment in chatbot/catalog.py)."""
    lines = []
    for entry in catalog:
        needs = ", ".join(entry.required_params) or "nothing"
        examples = " / ".join(f'"{p}"' for p in entry.phrases[:2])
        lines.append(f'- "{entry.query_id}": e.g. {examples} (needs: {needs})')
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


def validate_llm_intent(raw: dict | None, catalog: list, tier1_reason: str,
                         question: str | None = None, anchor_date=None) -> MatchResult:
    """`tier1_reason` is preserved when the LLM honestly declines (no
    query_id at all) - that's not an invalid response, just confirmation of
    tier 1's own assessment. `invalid_llm_intent` is reserved for the LLM
    actively naming an unknown query_id - not a query_id that's valid but
    whose required parameter genuinely isn't present in the question (that's
    still a missing_parameter, same root cause as tier 1's own version of it,
    just confirmed at this tier instead).

    `question`/`anchor_date` (both optional, for backward compatibility with
    the direct unit tests in tests/test_chatbot_fallback_validation.py,
    which don't need them) exist to catch a real bug found in production:
    the extraction prompt above asks the LLM to freely state a "period" as
    a bare Month/Year string, with no anchor to real data - for a relative
    phrase like "this month" it produced "October 2023" (its own
    training-era guess at "now"), which then passed straight through
    extract_period's own Month-Year regex as if it were a real, explicit
    date. A relative phrase in the ORIGINAL question (never the LLM's own
    restated "period" value, which by then may already be wrong) is checked
    first and, if found, resolved deterministically and used instead of
    ever consulting the LLM's freeform value for it."""
    if not raw or not raw.get("query_id"):
        return MatchResult(query_id=None, reason=tier1_reason)

    entry = next((e for e in catalog if e.query_id == raw["query_id"]), None)
    if entry is None:
        return MatchResult(query_id=None, reason="invalid_llm_intent")

    params = {}
    for param_name in entry.required_params:
        if param_name == "period" and question is not None and anchor_date is not None:
            relative = extract_relative_period(question, anchor_date)
            if relative is not None:
                params.update(relative)
                continue

        raw_value = raw.get(param_name)
        if raw_value is None:
            return MatchResult(query_id=None, reason="missing_parameter")
        extracted = PARAM_EXTRACTORS[param_name](raw_value)
        if extracted is None:
            return MatchResult(query_id=None, reason="missing_parameter")
        params.update(extracted)

    return MatchResult(query_id=entry.query_id, params=params)
