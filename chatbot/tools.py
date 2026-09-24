"""
Tier-3: a small, growing set of named query functions registered as OpenAI
tools. Medium-granularity - not one function per exact phrasing, not a
single maximal generic "aggregate metric by dimension" primitive - matching
the actual pattern already proven in production by Savanna QSR Intelligence
and Lobels Stores Intelligence (both verified directly against their real
code, not assumed). See spec-chatbot-catalog-expansion.md.

Reached only when tier-1 and tier-2 both produce a true no_match/ambiguous -
never for missing_parameter (a targeted clarifying question instead) or
scoped_out (final at whichever tier found it), both handled in
chatbot/engine.py before tier-3 is ever reached.

Every tool executes through parameterized queries only - the LLM never
supplies table names, column names, or SQL text, only filter *values*.
Closed-vocabulary arguments (e.g. domain) are validated against a fixed
list before the query runs and raise InvalidToolArgument on a bad value (a
single, final failure - no retry, same precedent as tier-2's own
validation); free-text arguments are trusted to the database, which
returns nothing for a value that doesn't exist.
"""

import datetime
import json
from dataclasses import dataclass, field

from chatbot.catalog import active_headcount_asof, date_filter_sql

VALID_HEADCOUNT_DOMAINS = {"piggery", "poultry"}


class InvalidToolArgument(Exception):
    """A closed-vocabulary tool argument failed validation - the tool call
    itself doesn't make sense, distinct from a legitimate query that
    happens to return no rows."""


_LATEST_HEADCOUNT_DATE_SQL = """
    SELECT MAX(d) FROM (
        SELECT date AS d FROM pig_daily_log
        UNION ALL SELECT date FROM poultry_daily_log
    ) all_dates
"""


def _latest_headcount_date(conn) -> datetime.date:
    return conn.execute(_LATEST_HEADCOUNT_DATE_SQL).fetchone()[0]


def q_headcount(conn, domain: str | None = None, date_from=None, date_to=None) -> dict:
    """Current active headcount - piggery, poultry, or both if domain is
    omitted. "Active as of" `date_to` (the currently-selected global date
    filter's end date) if given, else the latest real data date - the same
    as-of-a-cutoff treatment the dashboard's Active Headcount stat card
    already gives date_to, not a WHERE-clause range filter (this tool's
    underlying query is fundamentally a point-in-time snapshot, not a
    range aggregate, so it doesn't use the {date_filter} SQL-fragment
    pattern tier-1/2's range queries use - a deliberate, reasoned
    difference, not an inconsistency). `date_from` is accepted (every
    tier-3 tool is called with both, for a uniform dispatch signature) but
    unused - "how many do we have right now" has no meaningful start
    bound."""
    if domain is not None and domain not in VALID_HEADCOUNT_DOMAINS:
        raise InvalidToolArgument(
            f"domain must be one of {sorted(VALID_HEADCOUNT_DOMAINS)}, got {domain!r}"
        )

    cutoff = date_to or _latest_headcount_date(conn)

    counts = {}
    if domain in (None, "piggery"):
        counts["piggery"] = active_headcount_asof(
            conn, cutoff, "pig_daily_log", "closing_count")
    if domain in (None, "poultry"):
        counts["poultry"] = active_headcount_asof(
            conn, cutoff, "poultry_daily_log", "closing_birds")

    return {"as_of": str(cutoff), **counts, "total": sum(counts.values())}


CROP_AREA_PLANTED_SQL = """
    SELECT COALESCE(SUM(area_ha), 0) AS total_ha
    FROM plantings
    WHERE 1=1{date_filter}
"""


def q_crop_area_planted(conn, domain: str | None = None, date_from=None, date_to=None) -> dict:
    """Total hectares planted across all plantings - a genuine range
    aggregate (unlike q_headcount's point-in-time snapshot), so this uses
    the same {date_filter}/date_filter_sql range-filtering pattern tier-1/2
    already use, filtered by planting_date. `domain` is accepted for a
    uniform tool-calling signature but unused - crops is the only domain
    plantings belong to, there is nothing to narrow."""
    params = {}
    date_filter = date_filter_sql("planting_date", date_from, date_to, params)
    sql = CROP_AREA_PLANTED_SQL.format(date_filter=date_filter)
    total_ha = conn.execute(sql, params).fetchone()[0]
    return {"total_hectares_planted": float(total_ha)}


WEATHER_ASOF_SQL = """
    SELECT date, rainfall_mm, temp_min_c, temp_max_c, humidity_pct, event
    FROM weather_log
    WHERE date <= %(cutoff)s
    ORDER BY date DESC
    LIMIT 1
"""

_LATEST_WEATHER_DATE_SQL = "SELECT MAX(date) FROM weather_log"


def _latest_weather_date(conn) -> datetime.date | None:
    return conn.execute(_LATEST_WEATHER_DATE_SQL).fetchone()[0]


def q_weather(conn, domain: str | None = None, date_from=None, date_to=None) -> dict:
    """The most recent real logged weather conditions as of `date_to` (the
    currently-selected global filter's end date) or the latest real logged
    date if none given. "Today" honestly means the latest real data date,
    not the calendar date - this is historical logged data, not a live
    feed, matching how freshness is already handled elsewhere in this app
    (e.g. Data Coverage). A point-in-time lookup, like q_headcount, not a
    range aggregate like q_crop_area_planted - `date_from` and `domain`
    are accepted for a uniform tool-calling signature but unused; weather
    isn't owned by any single domain module."""
    cutoff = date_to or _latest_weather_date(conn)
    if cutoff is None:
        return {"found": False}

    row = conn.execute(WEATHER_ASOF_SQL, {"cutoff": cutoff}).fetchone()
    if row is None:
        return {"found": False}

    date, rainfall_mm, temp_min_c, temp_max_c, humidity_pct, event = row
    return {
        "found": True,
        "date": str(date),
        "rainfall_mm": float(rainfall_mm) if rainfall_mm is not None else None,
        "temp_min_c": float(temp_min_c) if temp_min_c is not None else None,
        "temp_max_c": float(temp_max_c) if temp_max_c is not None else None,
        "humidity_pct": float(humidity_pct) if humidity_pct is not None else None,
        "event": event,
    }


CROP_TYPES_SQL = """
    SELECT DISTINCT crop
    FROM plantings
    WHERE 1=1{date_filter}
    ORDER BY crop
"""


def q_crop_types(conn, domain: str | None = None, date_from=None, date_to=None) -> dict:
    """Distinct crop types planted, optionally scoped to the selected date
    range (by planting_date) - a listing, not an aggregate, complementing
    q_crop_area_planted's total hectares. Same range-filtering pattern as
    q_crop_area_planted; `domain` accepted but unused for the same reason."""
    params = {}
    date_filter = date_filter_sql("planting_date", date_from, date_to, params)
    sql = CROP_TYPES_SQL.format(date_filter=date_filter)
    rows = conn.execute(sql, params).fetchall()
    crops = [r[0] for r in rows if r[0] is not None]
    return {"crops": crops, "count": len(crops)}


VALID_EXPENSE_DOMAINS = {"piggery", "poultry", "crops"}

EXPENSES_TO_DATE_SQL = """
    SELECT COALESCE(SUM(total_cost), 0) AS total
    FROM expenses
    WHERE date <= %(cutoff)s{domain_filter}
"""

_LATEST_EXPENSE_DATE_SQL = "SELECT MAX(date) FROM expenses"


def _latest_expense_date(conn) -> datetime.date | None:
    return conn.execute(_LATEST_EXPENSE_DATE_SQL).fetchone()[0]


def q_expenses_to_date(conn, domain: str | None = None, date_from=None, date_to=None) -> dict:
    """Cumulative total expenses up to and including date_to (the
    currently-selected global filter's end date) or the latest real
    expense date if none given - "to date" means everything up through a
    cutoff, matching the dashboard's existing cumulative stat-card
    treatment (Total Livestock Placed, Piglets Born), not a
    date_from-bounded range. `date_from` is accepted for a uniform
    tool-calling signature but unused - a cumulative total has no
    meaningful start bound. `domain` is optional and validated against the
    closed vocabulary before querying, same pattern as q_headcount's."""
    if domain is not None and domain not in VALID_EXPENSE_DOMAINS:
        raise InvalidToolArgument(
            f"domain must be one of {sorted(VALID_EXPENSE_DOMAINS)}, got {domain!r}"
        )

    cutoff = date_to or _latest_expense_date(conn)
    if cutoff is None:
        return {"found": False}

    params = {"cutoff": cutoff}
    domain_filter = ""
    if domain is not None:
        domain_filter = " AND domain = %(domain)s"
        params["domain"] = domain

    sql = EXPENSES_TO_DATE_SQL.format(domain_filter=domain_filter)
    total = conn.execute(sql, params).fetchone()[0]
    return {"as_of": str(cutoff), "domain": domain or "all", "total_expenses": float(total)}


TOOLS_SCHEMA = [
    {"type": "function", "function": {
        "name": "q_headcount",
        "description": (
            "Current active headcount of pigs and/or poultry. Use for "
            "'how many pigs do we have', 'how many chickens/poultry do we "
            "have', 'current headcount', 'how many animals do we have'."
        ),
        "parameters": {"type": "object", "properties": {
            "domain": {
                "type": "string", "enum": ["piggery", "poultry"],
                "description": "Omit to get both piggery and poultry totals.",
            },
        }},
    }},
    {"type": "function", "function": {
        "name": "q_crop_area_planted",
        "description": (
            "Total hectares of crop planted. Use for 'how many hectares "
            "of crop is planted', 'how much land is planted', 'total crop "
            "area'."
        ),
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "q_weather",
        "description": (
            "The most recent logged weather conditions - rainfall, "
            "temperature, humidity. Use for 'what's the weather like "
            "today', 'how much rain have we had', 'current weather'."
        ),
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "q_crop_types",
        "description": (
            "Which crop types are planted (a list, not a total area). "
            "Use for 'what crops do we have', 'what crops are we "
            "growing', 'which crops are planted'."
        ),
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "q_expenses_to_date",
        "description": (
            "Cumulative total expenses to date (optionally for one "
            "domain) - money the farm has already spent/paid. Use for "
            "'what's the expense amount to date', 'total expenses so "
            "far', 'how much have we spent'. Do NOT use for questions "
            "about money the farm owes to others / accounts payable "
            "('are we owing anyone', 'do we owe our suppliers', 'what "
            "do we owe') - that is a different, untracked concept; do "
            "not call any tool for those."
        ),
        "parameters": {"type": "object", "properties": {
            "domain": {
                "type": "string", "enum": ["piggery", "poultry", "crops"],
                "description": "Omit for the total across all domains.",
            },
        }},
    }},
]

TOOL_FUNC_MAP = {
    "q_headcount": q_headcount,
    "q_crop_area_planted": q_crop_area_planted,
    "q_weather": q_weather,
    "q_crop_types": q_crop_types,
    "q_expenses_to_date": q_expenses_to_date,
}

# Statically declared per tool, at registration time - same rule the
# existing catalog already applies (a tool that can touch multiple domains
# declares all of them, regardless of what a runtime argument narrows to).
# See spec-chatbot-catalog-expansion.md's module-scoping decision. Weather
# is farm-wide, not owned by any single domain module - an empty list, not
# "no domains declared yet."
TOOL_DOMAINS = {
    "q_headcount": ["piggery", "poultry"],
    "q_crop_area_planted": ["crops"],
    "q_weather": [],
    "q_crop_types": ["crops"],
    "q_expenses_to_date": ["piggery", "poultry", "crops"],
}


@dataclass
class ToolCallResult:
    """Which tool (if any) OpenAI's tool-calling picked, and its raw,
    not-yet-validated arguments - or the LLM's own text when it picked no
    tool at all."""
    tool_name: str | None
    arguments: dict = field(default_factory=dict)
    raw_content: str | None = None


def resolve_tool_call(question: str, openai_client) -> ToolCallResult:
    """Round-trips one OpenAI tool-calling request. This is the narrow,
    explicitly-agreed seam tier-3's tool-selection tests assert against
    directly (see spec-chatbot-catalog-expansion.md's Testing Decisions) -
    the direct analogue of tier-2's validate_llm_intent being tested
    directly, since the real model empirically won't misbehave on demand
    for this branch either. Only the first tool call is used - tier-3
    tools are independent lookups, not composed in one turn, matching this
    project's one-shot simplicity elsewhere."""
    resp = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": question}],
        tools=TOOLS_SCHEMA,
        tool_choice="auto",
        temperature=0,
    )
    msg = resp.choices[0].message
    if not msg.tool_calls:
        return ToolCallResult(tool_name=None, raw_content=msg.content)

    tc = msg.tool_calls[0]
    try:
        arguments = json.loads(tc.function.arguments or "{}")
    except json.JSONDecodeError:
        arguments = {}
    return ToolCallResult(tool_name=tc.function.name, arguments=arguments)
