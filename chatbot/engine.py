import json
from dataclasses import dataclass

import openai
import psycopg

from chatbot.catalog import CATALOG
from chatbot.matcher import match

UNRESOLVED_TEMPLATE = "I can't answer that yet - I don't have a way to look that up."
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
    intent_source: str          # "deterministic" | "llm_fallback" | "unresolved"
    query_id: str | None = None
    failure_reason: str | None = None
    scoped_out_reason: str | None = None


def answer_question(question: str, farm_code: str, dsn: str) -> Answer:
    conn = psycopg.connect(dsn, autocommit=True)
    _ensure_query_log_table(conn)

    result = match(question, CATALOG)

    if result.query_id is None:
        answer = Answer(
            text=UNRESOLVED_TEMPLATE,
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
            intent_source="deterministic",
            query_id=result.query_id,
            scoped_out_reason=inactive_domain,
        )
        _log(conn, farm_code, question, answer)
        conn.close()
        return answer

    cursor = conn.execute(catalog_entry.sql, result.params)
    columns = [d.name for d in cursor.description]
    computed = [dict(zip(columns, row)) for row in cursor.fetchall()]

    text = _phrase(question, computed)
    answer = Answer(text=text, intent_source="deterministic", query_id=result.query_id)
    _log(conn, farm_code, question, answer)
    conn.close()
    return answer


def _find_inactive_domain(conn, farm_code: str, domains: list) -> str | None:
    """Any domain the query touches with an inactive module fails scoping -
    not only if all of them are inactive. See spec-chatbot-answer-engine.md's
    cross-domain scoping rule."""
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


def _log(conn, farm_code: str, question: str, answer: Answer) -> None:
    try:
        conn.execute(
            """
            INSERT INTO query_log (
                farm_code, question_text, intent_source, query_id,
                failure_reason, scoped_out_reason
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                farm_code, question, answer.intent_source, answer.query_id,
                answer.failure_reason, answer.scoped_out_reason,
            ),
        )
    except Exception:
        pass  # fire-and-forget: a logging failure must never affect the answer
