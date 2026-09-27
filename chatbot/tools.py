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

from chatbot.catalog import active_headcount_asof, date_filter_sql, deaths_in_window, fcr_by_batch

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


def q_expenses_by_domain(conn, date_from=None, date_to=None) -> dict:
    """A breakdown of cumulative expenses-to-date by domain, for
    comparison questions ("compare piggery and poultry costs") that
    q_expenses_to_date's single-total-or-one-domain shape can't answer -
    tier-3 only calls one tool once per turn (see resolve_tool_call), so a
    real comparison needs a tool that returns multiple domains' figures
    together, not two separate tool calls. Reuses q_expenses_to_date's
    same per-domain query three times, not a new SQL pattern."""
    cutoff = date_to or _latest_expense_date(conn)
    return {
        "as_of": str(cutoff) if cutoff else None,
        "piggery": q_expenses_to_date(conn, domain="piggery", date_to=date_to)["total_expenses"],
        "poultry": q_expenses_to_date(conn, domain="poultry", date_to=date_to)["total_expenses"],
        "crops": q_expenses_to_date(conn, domain="crops", date_to=date_to)["total_expenses"],
    }


VALID_ANIMAL_DOMAINS = {"piggery", "poultry"}


def q_cost_per_animal(conn, domain: str | None = None, date_from=None, date_to=None) -> dict:
    """Cost per animal = total domain expenses to date / current active
    headcount for that domain - a real division, always computed here in
    Python from two already-correct deterministic queries, never left for
    the LLM to claim it computed (the real bug this tool fixes: the
    narrator previously said "the cost per pig is calculated based on
    total expenses of X" without ever actually dividing by headcount).
    `domain` is required in the tool schema (declared below), but
    validated explicitly here too rather than relying on a bare TypeError
    for a missing argument - a clearer, more intentional failure mode."""
    if domain is None or domain not in VALID_ANIMAL_DOMAINS:
        raise InvalidToolArgument(
            f"domain must be one of {sorted(VALID_ANIMAL_DOMAINS)}, got {domain!r}"
        )

    table = "pig_daily_log" if domain == "piggery" else "poultry_daily_log"
    count_col = "closing_count" if domain == "piggery" else "closing_birds"
    cutoff = date_to or _latest_headcount_date(conn)
    headcount = active_headcount_asof(conn, cutoff, table, count_col)
    total_expenses = q_expenses_to_date(conn, domain=domain, date_to=date_to)["total_expenses"]

    if not headcount:
        return {"as_of": str(cutoff), "domain": domain, "headcount": 0,
                "total_expenses": total_expenses, "cost_per_animal": None}

    return {
        "as_of": str(cutoff), "domain": domain, "headcount": headcount,
        "total_expenses": total_expenses,
        "cost_per_animal": round(total_expenses / headcount, 2),
    }


_LATEST_FINANCIAL_DATE_SQL = """
    SELECT MAX(d) FROM (
        SELECT date AS d FROM expenses
        UNION ALL SELECT date FROM revenue
    ) all_dates
"""


def _latest_financial_date(conn) -> datetime.date | None:
    return conn.execute(_LATEST_FINANCIAL_DATE_SQL).fetchone()[0]


REVENUE_TO_DATE_SQL = """
    SELECT COALESCE(SUM(total_amount), 0) AS total
    FROM revenue
    WHERE date <= %(cutoff)s{domain_filter}
"""


def q_profit(conn, domain: str | None = None, date_from=None, date_to=None) -> dict:
    """Profit = revenue to date - expenses to date, both cumulative up to
    the same cutoff (matching q_expenses_to_date's "to date" semantics,
    not a date_from-bounded range). Reuses q_expenses_to_date's existing
    total and one new, equally simple revenue total - a real subtraction
    always computed here in Python, never left for the LLM. The
    dashboard's Expenses vs Revenue chart shows both series as separate
    lines but never computes their difference - this tool closes that
    gap without a new query shape, not because the chart was missing
    data."""
    if domain is not None and domain not in VALID_EXPENSE_DOMAINS:
        raise InvalidToolArgument(
            f"domain must be one of {sorted(VALID_EXPENSE_DOMAINS)}, got {domain!r}"
        )

    cutoff = date_to or _latest_financial_date(conn)
    if cutoff is None:
        return {"found": False}

    expenses = q_expenses_to_date(conn, domain=domain, date_to=cutoff)["total_expenses"]

    params = {"cutoff": cutoff}
    domain_filter = ""
    if domain is not None:
        domain_filter = " AND domain = %(domain)s"
        params["domain"] = domain
    revenue_sql = REVENUE_TO_DATE_SQL.format(domain_filter=domain_filter)
    revenue = float(conn.execute(revenue_sql, params).fetchone()[0])

    return {
        "as_of": str(cutoff), "domain": domain or "all",
        "total_revenue": revenue, "total_expenses": expenses,
        "profit": round(revenue - expenses, 2),
    }


_PERIOD_DAYS = {"last_7_days": 7, "last_30_days": 30, "last_90_days": 90}
VALID_MORTALITY_DOMAINS = {"piggery", "poultry"}


def q_mortality_rate(conn, domain: str | None = None, period: str | None = None,
                      date_from=None, date_to=None) -> dict:
    """Death count and mortality rate (%), farm-wide (piggery + poultry
    combined) if domain is omitted, or for one domain - reusing the exact
    methodology already computed for the dashboard's Mortality Rate stat
    card (deaths_in_window / active_headcount_asof, both relocated to
    chatbot/catalog.py so this tool and the dashboard share one source of
    truth), just exposed as a chat-answerable tool. `period` is a
    symbolic relative-time enum ("last_7_days" etc.), not an LLM-computed
    date - the LLM must never compute "today minus 7 days" itself (it has
    no way to know "today" here means the latest real data date, not the
    calendar date); this tool computes the real window boundary instead,
    matching Savanna QSR Intelligence's own proven q_revenue_by_period
    pattern (verified by reading its real code) rather than trusting an
    LLM-supplied date. `period` takes precedence over date_from/date_to
    when both are somehow given, since a period named in the question
    itself is more specific than whatever the global filter happens to be
    set to."""
    if domain is not None and domain not in VALID_MORTALITY_DOMAINS:
        raise InvalidToolArgument(
            f"domain must be one of {sorted(VALID_MORTALITY_DOMAINS)}, got {domain!r}"
        )
    if period is not None and period not in _PERIOD_DAYS:
        raise InvalidToolArgument(
            f"period must be one of {sorted(_PERIOD_DAYS)}, got {period!r}"
        )

    window_end = date_to or _latest_headcount_date(conn)
    if period is not None:
        window_start = window_end - datetime.timedelta(days=_PERIOD_DAYS[period])
    else:
        window_start = date_from or (window_end - datetime.timedelta(days=30))

    domains = [domain] if domain else ["piggery", "poultry"]
    deaths = 0
    headcount = 0
    for d in domains:
        table = "pig_daily_log" if d == "piggery" else "poultry_daily_log"
        count_col = "closing_count" if d == "piggery" else "closing_birds"
        deaths += deaths_in_window(conn, window_start, window_end, table)
        headcount += active_headcount_asof(conn, window_end, table, count_col)

    return {
        "window_start": str(window_start), "window_end": str(window_end),
        "domain": domain or "farm-wide (piggery + poultry)",
        "deaths": deaths, "headcount": headcount,
        "mortality_rate_pct": round(deaths / headcount * 100, 2) if headcount else None,
    }


VALID_FCR_DOMAINS = {"piggery", "poultry"}


def q_fcr_ranking(conn, domain: str | None = None, date_from=None, date_to=None) -> dict:
    """Ranks batches by feed conversion ratio (FCR = feed consumed /
    liveweight gain; lower is better/more efficient) - reusing the exact
    methodology and approximation already computed for the dashboard's
    FCR chart (fcr_by_batch, relocated to chatbot/catalog.py so this tool
    and the dashboard share one source of truth), just exposed as a
    chat-answerable tool. Closes a real gap found via a QA pass: "which
    batch has the worst feed conversion ratio" was previously mismatched
    at tier-1 to poultry_mortality_spike (a different metric entirely) -
    see matcher.py's Jaccard-scoring fix for the routing half of that fix;
    this tool is the "actually answer it" half."""
    if domain is not None and domain not in VALID_FCR_DOMAINS:
        raise InvalidToolArgument(
            f"domain must be one of {sorted(VALID_FCR_DOMAINS)}, got {domain!r}"
        )

    rows = fcr_by_batch(conn, date_from=date_from, date_to=date_to)
    if domain is not None:
        rows = [r for r in rows if r["domain"] == domain]
    if not rows:
        return {"found": False}

    ranked = sorted(rows, key=lambda r: float(r["fcr"]))
    return {
        "found": True,
        "best_batch": ranked[0]["batch_code"], "best_fcr": float(ranked[0]["fcr"]),
        "worst_batch": ranked[-1]["batch_code"], "worst_fcr": float(ranked[-1]["fcr"]),
        "all_fcr_by_batch": {r["batch_code"]: float(r["fcr"]) for r in ranked},
    }


EXPENSE_BY_CATEGORY_SQL = """
    SELECT category, SUM(total_cost) AS total
    FROM expenses
    WHERE 1=1{date_filter}{domain_filter}
    GROUP BY category
    ORDER BY total DESC
"""


def q_expense_by_category(conn, domain: str | None = None, date_from=None, date_to=None) -> dict:
    """Expense breakdown by CATEGORY (Feed, Labour, Vet, etc.) - a
    different dimension from q_expenses_by_domain's piggery/poultry/crops
    breakdown, never interchangeable with it. Closes a real bug found via
    a QA pass: "what's our biggest expense category" was previously
    answered using the domain breakdown, calling a domain (e.g.
    "piggery") a category. `domain` optionally narrows the category
    breakdown to one domain, but is not itself a category - both this
    tool's own description and q_expenses_by_domain's were tightened so
    the LLM doesn't conflate the two dimensions again."""
    if domain is not None and domain not in VALID_EXPENSE_DOMAINS:
        raise InvalidToolArgument(
            f"domain must be one of {sorted(VALID_EXPENSE_DOMAINS)}, got {domain!r}"
        )

    params = {}
    date_filter = date_filter_sql("date", date_from, date_to, params)
    domain_filter = ""
    if domain is not None:
        domain_filter = " AND domain = %(domain)s"
        params["domain"] = domain

    sql = EXPENSE_BY_CATEGORY_SQL.format(date_filter=date_filter, domain_filter=domain_filter)
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        return {"found": False}

    breakdown = {r[0]: float(r[1]) for r in rows}
    biggest_category, biggest_amount = max(breakdown.items(), key=lambda kv: kv[1])
    return {
        "found": True, "breakdown_by_category": breakdown,
        "biggest_category": biggest_category, "biggest_amount": biggest_amount,
    }


TOOLS_SCHEMA = [
    {"type": "function", "function": {
        "name": "q_headcount",
        "description": (
            "Current active headcount of pigs and/or poultry. Use for "
            "'how many pigs do we have', 'how many chickens/poultry do we "
            "have', 'current headcount', 'how many animals do we have'. "
            "For a COMBINED question asking about both pigs and poultry "
            "together ('how many pigs and chickens combined', 'total "
            "animals'), OMIT domain entirely to get both totals - do not "
            "guess a single domain when the question asks about both."
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
            "A SINGLE cumulative total expenses figure to date - either "
            "the farm-wide total, or one domain's total if asked. Use for "
            "'what's the expense amount to date', 'total expenses so "
            "far', 'how much have we spent'. NOT for comparing multiple "
            "domains against each other ('compare piggery and poultry "
            "costs') - use q_expenses_by_domain for that, since this tool "
            "only ever returns one number. Do NOT use for questions "
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
    {"type": "function", "function": {
        "name": "q_expenses_by_domain",
        "description": (
            "A BREAKDOWN of total expenses to date by DOMAIN (piggery, "
            "poultry, crops) - NOT by category. Use for 'compare piggery "
            "and poultry costs', 'expense breakdown by domain', 'which "
            "domain costs more'. Domain and category are different "
            "dimensions - do NOT use this for a category question like "
            "'biggest expense category' (Feed/Labour/Vet); use "
            "q_expense_by_category for that instead."
        ),
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "q_expense_by_category",
        "description": (
            "A breakdown of total expenses by CATEGORY (Feed, Labour, "
            "Vet, etc.) - NOT by domain. Use for 'what's our biggest "
            "expense category', 'expense breakdown by category', "
            "'how much do we spend on feed vs labour'. Category and "
            "domain are different dimensions - do NOT use this for a "
            "domain comparison like 'compare piggery and poultry costs'; "
            "use q_expenses_by_domain for that instead."
        ),
        "parameters": {"type": "object", "properties": {
            "domain": {
                "type": "string", "enum": ["piggery", "poultry", "crops"],
                "description": "Optional - narrow the category breakdown to one domain.",
            },
        }},
    }},
    {"type": "function", "function": {
        "name": "q_fcr_ranking",
        "description": (
            "Ranks batches by feed conversion ratio (FCR) - a specific "
            "metric (feed used / weight gain), NOT mortality or any "
            "other metric. Use for 'which batch has the worst/best feed "
            "conversion ratio', 'FCR by batch', 'most efficient batch'."
        ),
        "parameters": {"type": "object", "properties": {
            "domain": {
                "type": "string", "enum": ["piggery", "poultry"],
                "description": "Omit to rank across both domains together.",
            },
        }},
    }},
    {"type": "function", "function": {
        "name": "q_cost_per_animal",
        "description": (
            "Cost per pig or per bird - total domain expenses divided by "
            "current headcount for that domain. Use for 'what's the cost "
            "per pig', 'cost per bird', 'cost per chicken'."
        ),
        "parameters": {"type": "object", "properties": {
            "domain": {
                "type": "string", "enum": ["piggery", "poultry"],
                "description": "Required - which domain's cost-per-animal to compute.",
            },
        }, "required": ["domain"]},
    }},
    {"type": "function", "function": {
        "name": "q_profit",
        "description": (
            "Profit (revenue minus expenses) to date, farm-wide or for "
            "one domain. Use for 'is the piggery profitable', 'what's "
            "our profit', 'are we making money'."
        ),
        "parameters": {"type": "object", "properties": {
            "domain": {
                "type": "string", "enum": ["piggery", "poultry", "crops"],
                "description": "Omit for the farm-wide total.",
            },
        }},
    }},
    {"type": "function", "function": {
        "name": "q_mortality_rate",
        "description": (
            "Death count and mortality rate (%), farm-wide (piggery + "
            "poultry combined) or for one domain, over a period. Use for "
            "'mortality rate for the whole farm', 'how many chickens/pigs "
            "died last week/month', 'death count this month'."
        ),
        "parameters": {"type": "object", "properties": {
            "domain": {
                "type": "string", "enum": ["piggery", "poultry"],
                "description": "Omit for farm-wide (both domains combined).",
            },
            "period": {
                "type": "string", "enum": ["last_7_days", "last_30_days", "last_90_days"],
                "description": ("A relative period named in the question (e.g. "
                                 "'last week' -> last_7_days). Omit if the question "
                                 "doesn't name one - the global date filter or a "
                                 "30-day default applies instead."),
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
    "q_expenses_by_domain": q_expenses_by_domain,
    "q_cost_per_animal": q_cost_per_animal,
    "q_profit": q_profit,
    "q_mortality_rate": q_mortality_rate,
    "q_expense_by_category": q_expense_by_category,
    "q_fcr_ranking": q_fcr_ranking,
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
    "q_expenses_by_domain": ["piggery", "poultry", "crops"],
    "q_cost_per_animal": ["piggery", "poultry"],
    "q_profit": ["piggery", "poultry", "crops"],
    "q_mortality_rate": ["piggery", "poultry"],
    "q_expense_by_category": ["piggery", "poultry", "crops"],
    "q_fcr_ranking": ["piggery", "poultry"],
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
    project's one-shot simplicity elsewhere.

    No system prompt - a genuinely subject-less question ("how's it
    doing?", "how many?") is caught deterministically before this
    function is ever called (see chatbot/ambiguity.py); an LLM-prompted
    version of that check was tried first and found unreliable (it
    over-applied to cases explicitly excluded in its own prompt), so this
    function stays exactly as simple as it was before that attempt."""
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
