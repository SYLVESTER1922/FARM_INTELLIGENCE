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

from chatbot.catalog import (
    active_headcount_asof,
    date_filter_sql,
    deaths_in_window,
    farrowing_records,
    fcr_by_batch,
    health_by_event_type,
)

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


LABOUR_SUMMARY_SQL = """
    SELECT COALESCE(SUM(hours), 0) AS total_hours,
           COALESCE(SUM(overtime_hours), 0) AS total_overtime_hours,
           COALESCE(SUM(labour_cost), 0) AS total_labour_cost
    FROM labour_log
    WHERE 1=1{date_filter}{domain_filter}
"""


def q_labour_summary(conn, domain: str | None = None, date_from=None, date_to=None) -> dict:
    """Total labour hours, overtime hours, and labour cost over a date
    range, farm-wide or for one domain. Closes a real gap: labour_log is
    tracked (daily hours/cost per staff member/task) but has zero
    dashboard page and zero prior chat coverage. `domain` optionally
    narrows to one domain, validated against the same closed vocabulary
    as expenses (labour_log can also carry shared/unassigned entries with
    a NULL domain, which a domain filter correctly excludes)."""
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

    sql = LABOUR_SUMMARY_SQL.format(date_filter=date_filter, domain_filter=domain_filter)
    total_hours, total_overtime_hours, total_labour_cost = conn.execute(sql, params).fetchone()
    return {
        "domain": domain or "all",
        "total_hours": float(total_hours),
        "total_overtime_hours": float(total_overtime_hours),
        "total_labour_cost": float(total_labour_cost),
    }


HARVEST_YIELD_SQL = """
    SELECT pl.planting_code, p.plot_code, pl.crop, pl.area_ha,
           SUM(h.quantity_kg) AS total_kg, SUM(h.field_loss_kg) AS total_loss_kg
    FROM harvest_log h
    JOIN plantings pl ON pl.planting_code = h.planting_code
    JOIN plots p ON p.plot_code = pl.plot_code
    WHERE 1=1{date_filter}
    GROUP BY pl.planting_code, p.plot_code, pl.crop, pl.area_ha
"""


def q_harvest_yield(conn, domain: str | None = None, date_from=None, date_to=None) -> dict:
    """Harvest yield in kg per hectare, per plot/planting - distinct from
    the Domain Lookup tab's total-kg-harvested figure, which never divides
    by area. Ranks plots by yield_kg_per_ha to answer "which plot yields
    best/worst". `domain` is accepted for a uniform tool-calling signature
    but unused - crops is the only domain harvest_log belongs to."""
    params = {}
    date_filter = date_filter_sql("h.date", date_from, date_to, params)
    sql = HARVEST_YIELD_SQL.format(date_filter=date_filter)
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        return {"found": False}

    by_plot = []
    for planting_code, plot_code, crop, area_ha, total_kg, total_loss_kg in rows:
        area_ha = float(area_ha) if area_ha else 0.0
        total_kg = float(total_kg) if total_kg is not None else 0.0
        by_plot.append({
            "plot_code": plot_code, "crop": crop, "area_ha": area_ha,
            "total_kg": total_kg,
            "yield_kg_per_ha": round(total_kg / area_ha, 1) if area_ha else None,
            "field_loss_kg": float(total_loss_kg) if total_loss_kg is not None else 0.0,
        })

    ranked = sorted((r for r in by_plot if r["yield_kg_per_ha"] is not None),
                     key=lambda r: r["yield_kg_per_ha"])
    return {
        "found": True,
        "total_harvested_kg": sum(r["total_kg"] for r in by_plot),
        "total_field_loss_kg": sum(r["field_loss_kg"] for r in by_plot),
        "best_plot": ranked[-1]["plot_code"] if ranked else None,
        "best_yield_kg_per_ha": ranked[-1]["yield_kg_per_ha"] if ranked else None,
        "worst_plot": ranked[0]["plot_code"] if ranked else None,
        "worst_yield_kg_per_ha": ranked[0]["yield_kg_per_ha"] if ranked else None,
        "by_plot": by_plot,
    }


def q_breeding_summary(conn, domain: str | None = None, date_from=None, date_to=None) -> dict:
    """Litters, born-alive, weaned counts, average litter size, and best
    sow (by born-alive count) over a date range (by service_date) -
    reusing the exact rows already computed for the dashboard's Breeding
    page (farrowing_records, relocated to chatbot/catalog.py so this tool
    and the dashboard share one source of truth). The Breeding page exists
    on the dashboard but has zero prior chat coverage. `domain` is
    accepted for a uniform tool-calling signature but unused - breeding
    is piggery-only, there is nothing to narrow."""
    rows = farrowing_records(conn, date_from=date_from, date_to=date_to)
    completed = [r for r in rows if r["farrow_date"] is not None]
    if not completed:
        return {"found": False}

    total_litters = len(completed)
    total_born_alive = sum(r["born_alive"] or 0 for r in completed)
    total_weaned = sum(r["weaned_count"] or 0 for r in completed)
    best = max(completed, key=lambda r: r["born_alive"] or 0)
    return {
        "found": True,
        "total_litters": total_litters,
        "total_born_alive": total_born_alive,
        "total_weaned": total_weaned,
        "avg_litter_size": round(total_born_alive / total_litters, 1) if total_litters else None,
        "best_sow": best["sow_tag"],
        "best_sow_born_alive": best["born_alive"],
    }


FEED_STOCK_SQL = """
    SELECT DISTINCT ON (domain, feed_type) domain, feed_type, closing_kg, date
    FROM feed_inventory
    WHERE date <= %(cutoff)s{domain_filter}
    ORDER BY domain, feed_type, date DESC
"""

_LATEST_FEED_INVENTORY_DATE_SQL = "SELECT MAX(date) FROM feed_inventory"


def _latest_feed_inventory_date(conn) -> datetime.date | None:
    return conn.execute(_LATEST_FEED_INVENTORY_DATE_SQL).fetchone()[0]


def q_feed_stock(conn, domain: str | None = None, date_from=None, date_to=None) -> dict:
    """Current feed stock on hand (closing_kg) per feed type, as of
    date_to (the currently-selected global filter's end date) or the
    latest logged inventory date - a point-in-time snapshot, like
    q_headcount, not a range aggregate; `date_from` is accepted for a
    uniform signature but unused. Distinct from feed *cost* (already
    covered by the dashboard's Feed Cost chart and q_expense_by_category)
    - this is physical stock on hand, closes a real gap ("are we running
    low on feed")."""
    if domain is not None and domain not in VALID_HEADCOUNT_DOMAINS:
        raise InvalidToolArgument(
            f"domain must be one of {sorted(VALID_HEADCOUNT_DOMAINS)}, got {domain!r}"
        )

    cutoff = date_to or _latest_feed_inventory_date(conn)
    if cutoff is None:
        return {"found": False}

    params = {"cutoff": cutoff}
    domain_filter = ""
    if domain is not None:
        domain_filter = " AND domain = %(domain)s"
        params["domain"] = domain

    sql = FEED_STOCK_SQL.format(domain_filter=domain_filter)
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        return {"found": False}

    stock = [{"domain": r[0], "feed_type": r[1],
              "closing_kg": float(r[2]) if r[2] is not None else None,
              "as_of": str(r[3])} for r in rows]
    return {
        "found": True, "as_of": str(cutoff),
        "stock_by_feed_type": stock,
        "total_kg": sum(s["closing_kg"] or 0 for s in stock),
    }


_LATEST_PIG_WEIGHT_SQL = """
    SELECT DISTINCT ON (batch_code) batch_code, avg_weight_kg, date
    FROM pig_weights WHERE date <= %(cutoff)s{batch_filter}
    ORDER BY batch_code, date DESC
"""
_LATEST_POULTRY_WEIGHT_SQL = """
    SELECT DISTINCT ON (batch_code) batch_code, avg_weight_g, date
    FROM poultry_weights WHERE date <= %(cutoff)s{batch_filter}
    ORDER BY batch_code, date DESC
"""


def q_batch_weight(conn, domain: str | None = None, batch_code: str | None = None,
                    date_from=None, date_to=None) -> dict:
    """Latest average sampled weight per batch, as of date_to or the
    latest headcount data date - a point-in-time snapshot. At least one of
    `domain` or `batch_code` is required (the schema below doesn't mark
    either individually required since both are legitimate ways to ask,
    but calling with neither is a genuine tool-call error). Piggery
    weights are kg, poultry weights are grams - kept as separate,
    explicitly-labelled fields (never merged into one "weight" number) so
    the narrator never mixes units."""
    if domain is not None and domain not in VALID_HEADCOUNT_DOMAINS:
        raise InvalidToolArgument(
            f"domain must be one of {sorted(VALID_HEADCOUNT_DOMAINS)}, got {domain!r}"
        )
    if domain is None and batch_code is None:
        raise InvalidToolArgument("q_batch_weight requires domain and/or batch_code")

    cutoff = date_to or _latest_headcount_date(conn)
    domains_to_check = [domain] if domain else ["piggery", "poultry"]

    piggery_weights = {}
    poultry_weights = {}
    for d in domains_to_check:
        params = {"cutoff": cutoff}
        batch_filter = ""
        if batch_code is not None:
            batch_filter = " AND batch_code = %(batch_code)s"
            params["batch_code"] = batch_code
        if d == "piggery":
            rows = conn.execute(_LATEST_PIG_WEIGHT_SQL.format(batch_filter=batch_filter), params).fetchall()
            piggery_weights = {r[0]: float(r[1]) for r in rows if r[1] is not None}
        else:
            rows = conn.execute(_LATEST_POULTRY_WEIGHT_SQL.format(batch_filter=batch_filter), params).fetchall()
            poultry_weights = {r[0]: float(r[1]) for r in rows if r[1] is not None}

    if not piggery_weights and not poultry_weights:
        return {"found": False}

    result = {"found": True, "as_of": str(cutoff)}
    if piggery_weights:
        result["piggery_avg_weight_kg_by_batch"] = piggery_weights
    if poultry_weights:
        result["poultry_avg_weight_g_by_batch"] = poultry_weights
    return result


PIG_MARKET_READINESS_SQL = """
    SELECT batch_code, target_market_date FROM pig_batches
    WHERE target_market_date IS NOT NULL
"""
POULTRY_MARKET_READINESS_SQL = """
    SELECT batch_code, target_off_date FROM poultry_batches
    WHERE target_off_date IS NOT NULL
"""


def q_market_readiness(conn, domain: str | None = None, date_from=None, date_to=None) -> dict:
    """Batches that are overdue for market/off-take (target date before
    the as-of date) or coming up within the next 30 days - "are any
    batches ready to sell / overdue". As-of date_to or the latest
    headcount data date; `date_from` is accepted for a uniform signature
    but unused (this is a point-in-time readiness check, not a range
    aggregate). Deliberately not filtered by a `status` column: real
    fixtures show pig_batches and poultry_batches use different status
    vocabularies (e.g. "Active" vs "Growing"), so a single hardcoded
    status string would silently exclude one domain's batches - safer to
    show every batch with a target date and let the farmer's own
    knowledge of which batches are already sold filter the rest, than to
    guess a status value and hide real results."""
    if domain is not None and domain not in VALID_HEADCOUNT_DOMAINS:
        raise InvalidToolArgument(
            f"domain must be one of {sorted(VALID_HEADCOUNT_DOMAINS)}, got {domain!r}"
        )

    today = date_to or _latest_headcount_date(conn)
    domains_to_check = [domain] if domain else ["piggery", "poultry"]
    horizon = today + datetime.timedelta(days=30)

    overdue = []
    upcoming = []
    for d in domains_to_check:
        sql = PIG_MARKET_READINESS_SQL if d == "piggery" else POULTRY_MARKET_READINESS_SQL
        for batch_code, target_date in conn.execute(sql).fetchall():
            entry = {"batch_code": batch_code, "domain": d, "target_date": str(target_date)}
            if target_date < today:
                overdue.append(entry)
            elif target_date <= horizon:
                upcoming.append(entry)

    return {"as_of": str(today), "overdue_batches": overdue, "upcoming_batches_30_days": upcoming}


def q_health_cost_summary(conn, domain: str | None = None, date_from=None, date_to=None) -> dict:
    """Total health/vet events and cost over a date range, farm-wide or
    for one domain, with a breakdown by event type - reusing the exact
    rows already computed for the dashboard's Health page
    (health_by_event_type, relocated to chatbot/catalog.py). Distinct from
    the existing piggery_disease_outbreak catalog query, which only ever
    surfaces today's single worst batch - this tool answers cost/trend
    questions over an arbitrary period instead."""
    if domain is not None and domain not in VALID_HEADCOUNT_DOMAINS:
        raise InvalidToolArgument(
            f"domain must be one of {sorted(VALID_HEADCOUNT_DOMAINS)}, got {domain!r}"
        )

    rows = health_by_event_type(conn, date_from=date_from, date_to=date_to)
    if domain is not None:
        rows = [r for r in rows if r["domain"] == domain]
    if not rows:
        return {"found": False}

    total_events = sum(r["event_count"] for r in rows)
    total_cost = float(sum(r["total_cost"] or 0 for r in rows))
    breakdown = [{"domain": r["domain"], "event_type": r["event_type"],
                  "count": r["event_count"], "cost": float(r["total_cost"] or 0)}
                 for r in rows]
    return {
        "found": True, "domain": domain or "all",
        "total_events": total_events, "total_cost": total_cost,
        "breakdown_by_event_type": breakdown,
    }


TOP_BUYERS_SQL = """
    SELECT buyer, SUM(total_amount) AS total FROM revenue
    WHERE buyer IS NOT NULL{date_filter}{domain_filter}
    GROUP BY buyer ORDER BY total DESC LIMIT 5
"""
TOP_PRODUCTS_SQL = """
    SELECT product, SUM(total_amount) AS total FROM revenue
    WHERE 1=1{date_filter}{domain_filter}
    GROUP BY product ORDER BY total DESC LIMIT 5
"""
VALID_REVENUE_BREAKDOWN_BY = {"buyer", "product"}


def q_revenue_breakdown(conn, by: str | None = None, domain: str | None = None,
                         date_from=None, date_to=None) -> dict:
    """Top 5 buyers or products by total revenue, over a date range,
    farm-wide or for one domain - "who's our biggest buyer", "what's our
    best-selling product". `by` is required in the tool schema (declared
    below) and validated explicitly, same pattern as q_cost_per_animal's
    required `domain`."""
    if by is None or by not in VALID_REVENUE_BREAKDOWN_BY:
        raise InvalidToolArgument(
            f"by must be one of {sorted(VALID_REVENUE_BREAKDOWN_BY)}, got {by!r}"
        )
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

    sql_template = TOP_BUYERS_SQL if by == "buyer" else TOP_PRODUCTS_SQL
    sql = sql_template.format(date_filter=date_filter, domain_filter=domain_filter)
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        return {"found": False}

    return {"found": True, "by": by, "domain": domain or "all",
            "top_5": [{by: r[0], "total_revenue": float(r[1])} for r in rows]}


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
    {"type": "function", "function": {
        "name": "q_labour_summary",
        "description": (
            "Total labour hours, overtime hours, and labour cost over a "
            "period, farm-wide or for one domain. Use for 'how many "
            "labour hours did we use', 'what's our labour cost', "
            "'overtime hours this month'."
        ),
        "parameters": {"type": "object", "properties": {
            "domain": {
                "type": "string", "enum": ["piggery", "poultry", "crops"],
                "description": "Omit for the farm-wide total.",
            },
        }},
    }},
    {"type": "function", "function": {
        "name": "q_harvest_yield",
        "description": (
            "Harvest yield in kg per hectare, per plot - a per-area "
            "efficiency figure, NOT the same as a total-kg-harvested "
            "number. Use for 'which plot yields best/worst', 'yield per "
            "hectare', 'how efficient was our harvest'."
        ),
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "q_breeding_summary",
        "description": (
            "Litters, piglets born alive, piglets weaned, average litter "
            "size, and best sow over a period. Use for 'how many litters "
            "this month', 'average litter size', 'which sow had the "
            "biggest litter', 'weaning numbers'."
        ),
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "q_feed_stock",
        "description": (
            "Current physical feed stock on hand (kg), by feed type - NOT "
            "feed cost or feed spending. Use for 'how much feed do we "
            "have left', 'are we running low on feed', 'current feed "
            "stock'."
        ),
        "parameters": {"type": "object", "properties": {
            "domain": {
                "type": "string", "enum": ["piggery", "poultry"],
                "description": "Omit to get stock for both domains.",
            },
        }},
    }},
    {"type": "function", "function": {
        "name": "q_batch_weight",
        "description": (
            "Latest average sampled weight for a batch, or all batches in "
            "a domain. Use for 'what's the average weight of batch X', "
            "'how heavy are the pigs/chickens right now', 'current growth "
            "weight'. At least one of domain or batch_code must be given."
        ),
        "parameters": {"type": "object", "properties": {
            "domain": {
                "type": "string", "enum": ["piggery", "poultry"],
                "description": "Which domain's batches to look up.",
            },
            "batch_code": {
                "type": "string",
                "description": "A specific batch code, if the question names one.",
            },
        }},
    }},
    {"type": "function", "function": {
        "name": "q_market_readiness",
        "description": (
            "Which batches are overdue for market/off-take, or coming up "
            "within 30 days. Use for 'which batches are ready to sell', "
            "'are any pigs/chickens overdue for market', 'upcoming "
            "off-take'."
        ),
        "parameters": {"type": "object", "properties": {
            "domain": {
                "type": "string", "enum": ["piggery", "poultry"],
                "description": "Omit to check both domains.",
            },
        }},
    }},
    {"type": "function", "function": {
        "name": "q_health_cost_summary",
        "description": (
            "Total health/vet events and cost over a period, farm-wide or "
            "for one domain, broken down by event type. Use ONLY for a "
            "question that explicitly names cost, spending, or events over "
            "a period, e.g. 'how much have we spent on vet care', 'health "
            "events this month', 'vet cost trend'. Do NOT use for a vague "
            "'is something wrong' / 'is there a problem with a batch' "
            "question that doesn't name a domain - that is genuinely "
            "ambiguous between a piggery and a poultry concern and must be "
            "left unresolved, not guessed at with this or any other tool."
        ),
        "parameters": {"type": "object", "properties": {
            "domain": {
                "type": "string", "enum": ["piggery", "poultry"],
                "description": "Omit for the farm-wide total.",
            },
        }},
    }},
    {"type": "function", "function": {
        "name": "q_revenue_breakdown",
        "description": (
            "Top 5 buyers or products by total revenue, over a period, "
            "farm-wide or for one domain. Use for 'who's our biggest "
            "buyer', 'what's our best-selling product', 'top customers'."
        ),
        "parameters": {"type": "object", "properties": {
            "by": {
                "type": "string", "enum": ["buyer", "product"],
                "description": "Required - which dimension to rank by.",
            },
            "domain": {
                "type": "string", "enum": ["piggery", "poultry", "crops"],
                "description": "Omit for the farm-wide total.",
            },
        }, "required": ["by"]},
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
    "q_labour_summary": q_labour_summary,
    "q_harvest_yield": q_harvest_yield,
    "q_breeding_summary": q_breeding_summary,
    "q_feed_stock": q_feed_stock,
    "q_batch_weight": q_batch_weight,
    "q_market_readiness": q_market_readiness,
    "q_health_cost_summary": q_health_cost_summary,
    "q_revenue_breakdown": q_revenue_breakdown,
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
    "q_labour_summary": ["piggery", "poultry", "crops"],
    "q_harvest_yield": ["crops"],
    "q_breeding_summary": ["piggery"],
    "q_feed_stock": ["piggery", "poultry"],
    "q_batch_weight": ["piggery", "poultry"],
    "q_market_readiness": ["piggery", "poultry"],
    "q_health_cost_summary": ["piggery", "poultry"],
    "q_revenue_breakdown": ["piggery", "poultry", "crops"],
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
