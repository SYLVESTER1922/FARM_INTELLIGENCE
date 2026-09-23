import json
from dataclasses import dataclass

import openai
import psycopg

from chatbot.catalog import (
    CATALOG,
    CROP_DEBTOR_DATE_COLUMN,
    PIGGERY_DISEASE_OUTBREAK_DATE_COLUMN,
    POULTRY_MORTALITY_SPIKE_DATE_COLUMN,
    date_filter_sql,
)
from chatbot.data_dictionary import explain_gap
from chatbot.fallback import llm_extract_intent, validate_llm_intent
from chatbot.greetings import GREETING_RESPONSE, HELP_RESPONSE, match_tier0
from chatbot.matcher import match
from chatbot.tools import (
    TOOL_DOMAINS,
    TOOL_FUNC_MAP,
    InvalidToolArgument,
    resolve_tool_call,
)

# Which column the optional global date-range filter applies to, per
# catalog entry - feed_cost_split isn't here because it already requires
# its own explicit period parameter, which already scopes it; layering a
# second, independent date restriction on top would be redundant at best
# and could silently contradict a period the user explicitly named.
CATALOG_DATE_COLUMNS = {
    "poultry_mortality_spike": POULTRY_MORTALITY_SPIKE_DATE_COLUMN,
    "piggery_disease_outbreak": PIGGERY_DISEASE_OUTBREAK_DATE_COLUMN,
    "crop_debtor": CROP_DEBTOR_DATE_COLUMN,
}

UNRESOLVED_TEMPLATE = "I can't answer that yet - I don't have a way to look that up."
# The catalog's only required_params entry today ("period", used solely by
# feed_cost_split) is a month/year - so this is safe to word specifically
# rather than generically. If a second required-parameter type is ever
# added, this needs to become reason-aware (which parameter was missing),
# not just reason-generic - matcher.py's MatchResult doesn't currently
# carry that through, by design, so this is a deliberate simplification,
# not an oversight.
MISSING_PARAMETER_TEMPLATE = (
    "I understood what you're asking, I just need one more detail: which "
    "month (and year) do you mean? For example, \"in January 2026\"."
)
SCOPED_OUT_TEMPLATE = (
    "The {module} module is turned off for this farm - turn it on in the "
    "farm profile to ask about that."
)

MODULE_ACTIVE_COLUMNS = {
    "piggery": "module_piggery_active",
    "poultry": "module_poultry_active",
    "crops": "module_crops_active",
}

_OPENAI_CLIENT = None


def _openai_client():
    """Relies on the OPENAI_API_KEY environment variable (standard OpenAI SDK
    behavior) - the key itself is never read from a hardcoded path here."""
    global _OPENAI_CLIENT
    if _OPENAI_CLIENT is None:
        _OPENAI_CLIENT = openai.OpenAI()
    return _OPENAI_CLIENT


@dataclass
class Answer:
    text: str
    intent_source: str          # "deterministic" | "llm_fallback" | "tool_fallback" | "tier0_greeting" | "tier0_help" | "unresolved"
    query_id: str | None = None
    failure_reason: str | None = None
    scoped_out_reason: str | None = None
    tool_name: str | None = None       # set only for tier-3 hits
    tool_arguments: dict | None = None  # set only for tier-3 hits


def answer_question(question: str, farm_code: str, dsn: str,
                     date_from=None, date_to=None) -> Answer:
    """`date_from`/`date_to` are optional: the currently-selected global
    date filter, if any - matching Savanna's structure, chat always
    operates within whatever range is currently selected. A date named in
    the question itself (e.g. "in March") is handled separately by the
    catalog's own period matching and narrows *within* this range, not
    instead of it."""
    # prepare_threshold=None: Supabase's DSN is the transaction-pooler
    # (pgbouncer) connection string, which is incompatible with psycopg3's
    # default server-side prepared statements - see sync/engine.py's
    # matching comment for the failure mode this avoids.
    conn = psycopg.connect(dsn, autocommit=True, prepare_threshold=None)
    _ensure_query_log_table(conn)

    tier0 = match_tier0(question)
    if tier0 is not None:
        text = GREETING_RESPONSE if tier0 == "greeting" else HELP_RESPONSE
        answer = Answer(text=text, intent_source=f"tier0_{tier0}")
        _log(conn, farm_code, question, answer)
        conn.close()
        return answer

    result = match(question, CATALOG)
    intent_source = "deterministic"

    if result.query_id is None:
        # tier 1 missed - one LLM attempt before giving up, no retry
        tier1_reason = result.reason
        raw = llm_extract_intent(question, CATALOG, _openai_client())
        result = validate_llm_intent(raw, CATALOG, tier1_reason)
        intent_source = "llm_fallback"

    if result.reason == "missing_parameter":
        answer = Answer(
            text=MISSING_PARAMETER_TEMPLATE,
            intent_source="unresolved",
            failure_reason=result.reason,
        )
        _log(conn, farm_code, question, answer)
        conn.close()
        return answer

    if result.query_id is None:
        # tier 1 and tier 2 both missed with a true no_match/ambiguous
        # (missing_parameter already returned above) - try tier-3's
        # tool-calling fallback before giving up.
        tool_result = resolve_tool_call(question, _openai_client())
        if tool_result.tool_name is not None:
            answer = _run_tool_call(conn, farm_code, question, tool_result, date_from, date_to)
            if answer is not None:
                _log(conn, farm_code, question, answer)
                conn.close()
                return answer

        # Genuine full miss at every tier - one bounded attempt to explain
        # *why*, honestly distinguishing "not tracked at all" from a
        # generic refusal, before giving up. See
        # spec-chatbot-catalog-expansion.md's honesty decision.
        gap_explanation = explain_gap(question, _openai_client())
        answer = Answer(
            text=gap_explanation if gap_explanation is not None else UNRESOLVED_TEMPLATE,
            intent_source="unresolved",
            failure_reason=result.reason,
        )
        _log(conn, farm_code, question, answer)
        conn.close()
        return answer

    catalog_entry = next(e for e in CATALOG if e.query_id == result.query_id)

    inactive_domain = _find_inactive_domain(conn, farm_code, catalog_entry.domains)
    if inactive_domain is not None:
        answer = Answer(
            text=SCOPED_OUT_TEMPLATE.format(module=inactive_domain),
            intent_source=intent_source,
            query_id=result.query_id,
            scoped_out_reason=inactive_domain,
        )
        _log(conn, farm_code, question, answer)
        conn.close()
        return answer

    date_column = CATALOG_DATE_COLUMNS.get(result.query_id)
    filter_params = {}
    date_filter = (date_filter_sql(date_column, date_from, date_to, filter_params)
                   if date_column else "")
    sql = catalog_entry.sql.format(date_filter=date_filter)
    params = {**result.params, **filter_params}
    cursor = conn.execute(sql, params)
    columns = [d.name for d in cursor.description]
    computed = [dict(zip(columns, row)) for row in cursor.fetchall()]

    text = _phrase(question, computed)
    answer = Answer(text=text, intent_source=intent_source, query_id=result.query_id)
    _log(conn, farm_code, question, answer)
    conn.close()
    return answer


def _run_tool_call(conn, farm_code: str, question: str, tool_result, date_from, date_to) -> "Answer | None":
    """Executes a tier-3 tool call end to end: module scoping (same static
    per-tool declaration + uniform check the catalog already uses),
    argument validation (a single, final failure, no retry - same
    precedent as tier-2), then narration via the same _phrase() every
    other tier already uses. Returns None only for a tool name the API
    somehow returned that isn't actually registered (should not happen in
    practice, since OpenAI only ever returns names from TOOLS_SCHEMA) -
    the caller falls through to the generic unresolved message in that
    case."""
    fn = TOOL_FUNC_MAP.get(tool_result.tool_name)
    if fn is None:
        return None

    domains = TOOL_DOMAINS.get(tool_result.tool_name, [])
    inactive_domain = _find_inactive_domain(conn, farm_code, domains)
    if inactive_domain is not None:
        return Answer(
            text=SCOPED_OUT_TEMPLATE.format(module=inactive_domain),
            intent_source="tool_fallback",
            scoped_out_reason=inactive_domain,
            tool_name=tool_result.tool_name,
            tool_arguments=tool_result.arguments,
        )

    try:
        computed = fn(conn, date_from=date_from, date_to=date_to, **tool_result.arguments)
    except (InvalidToolArgument, TypeError):
        return Answer(
            text=UNRESOLVED_TEMPLATE,
            intent_source="unresolved",
            failure_reason="invalid_tool_argument",
            tool_name=tool_result.tool_name,
            tool_arguments=tool_result.arguments,
        )

    text = _phrase(question, [computed])
    return Answer(
        text=text,
        intent_source="tool_fallback",
        tool_name=tool_result.tool_name,
        tool_arguments=tool_result.arguments,
    )


def _find_inactive_domain(conn, farm_code: str, domains: list) -> str | None:
    """Any domain the query touches with an inactive module fails scoping -
    not only if all of them are inactive. See spec-chatbot-answer-engine.md's
    cross-domain scoping rule. Every existing catalog entry always declares
    at least one domain, but a tier-3 tool can genuinely be farm-wide and
    touch none (e.g. a weather lookup) - an empty list means no module to
    check, not "select nothing," which would otherwise be invalid SQL."""
    if not domains:
        return None
    columns = ", ".join(MODULE_ACTIVE_COLUMNS[d] for d in domains)
    row = conn.execute(
        f"SELECT {columns} FROM farm_profile WHERE farm_code = %s", (farm_code,)
    ).fetchone()
    if row is None:
        return None
    for domain, active in zip(domains, row):
        if not active:
            return domain
    return None


def _phrase(question: str, computed: list) -> str:
    prompt = (
        "Answer the user's question in one short, natural sentence or two, "
        "using ONLY the computed data below. Every field in the data - "
        "identifiers, labels, and numbers alike - is there because it's part "
        "of the answer; mention all of them by their exact value, do not "
        "round or recompute any number, and do not omit or invent anything "
        "not present in the data.\n\n"
        f"Question: {question}\n"
        f"Computed data (JSON): {json.dumps(computed, default=str)}"
    )
    response = _openai_client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
    )
    return response.choices[0].message.content


def _ensure_query_log_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS query_log (
            id SERIAL PRIMARY KEY,
            logged_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            farm_code TEXT NOT NULL,
            question_text TEXT NOT NULL,
            intent_source TEXT NOT NULL,
            query_id TEXT,
            failure_reason TEXT,
            scoped_out_reason TEXT
        )
    """)
    # ADD COLUMN IF NOT EXISTS rather than folding these into the CREATE
    # above - CREATE TABLE IF NOT EXISTS is a no-op against the table that
    # already exists in production, so a schema addition has to go through
    # ALTER instead, same idempotent-DDL pattern the sync engine already
    # uses throughout. Tier-3 hits record which tool was selected and its
    # validated arguments (structured, safe data - never LLM-authored SQL
    # text) - see spec-chatbot-catalog-expansion.md's observability decision.
    conn.execute("ALTER TABLE query_log ADD COLUMN IF NOT EXISTS tool_name TEXT")
    conn.execute("ALTER TABLE query_log ADD COLUMN IF NOT EXISTS tool_arguments JSONB")


def _log(conn, farm_code: str, question: str, answer: Answer) -> None:
    try:
        conn.execute(
            """
            INSERT INTO query_log (
                farm_code, question_text, intent_source, query_id,
                failure_reason, scoped_out_reason, tool_name, tool_arguments
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                farm_code, question, answer.intent_source, answer.query_id,
                answer.failure_reason, answer.scoped_out_reason,
                answer.tool_name,
                json.dumps(answer.tool_arguments) if answer.tool_arguments is not None else None,
            ),
        )
    except Exception:
        pass  # fire-and-forget: a logging failure must never affect the answer
