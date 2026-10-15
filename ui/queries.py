"""
Read-only SQL data-fetching for the dashboard tabs (Herd & Flock, Financials,
Findings & Alerts, Data Coverage). Mirrors chatbot/engine.py's connection and
row-fetching style (conn.execute + zip columns into dicts) for consistency,
but is otherwise independent of the chat/answer-engine seam - nothing here
is used by chatbot/engine.py or ui/app.py's handle_message/_chat_fn.

Every function takes a psycopg connection and returns plain Python data
(lists/dicts of already-computed values) - no arithmetic happens in the UI
layer beyond what SQL already computed, same principle the chatbot's
SQL-then-phrase split already established.
"""

import datetime

from chatbot.catalog import (
    CROP_DEBTOR_DATE_COLUMN,
    CROP_DEBTOR_SQL,
    PIGGERY_DISEASE_OUTBREAK_DATE_COLUMN,
    PIGGERY_DISEASE_OUTBREAK_SQL,
    POULTRY_MORTALITY_SPIKE_DATE_COLUMN,
    POULTRY_MORTALITY_SPIKE_SQL,
    date_filter_sql,
)
from registry import Scope, compute
from registry.headcount import headcount_asof

# Every figure below that has a registry metric is computed BY the registry
# (registry/), the one definition shared with the chatbot's v2 path - this file
# only adapts the registry's result to the shape each chart already expects.
# Tests: tests/test_registry_parity.py.


def _scope(date_from, date_to, **kw):
    return Scope(start=date_from, end=date_to, **kw)


def _rows_or_empty(result):
    """A period with no record shows an empty chart, never a fabricated zero."""
    return result.rows if result.ok else []

MONTHLY_HEADCOUNT_SQL = """
    SELECT month, SUM(headcount) AS headcount FROM (
        SELECT DISTINCT ON (date_trunc('month', date), batch_code)
            date_trunc('month', date)::date AS month,
            batch_code, {count_col} AS headcount
        FROM {table}
        WHERE 1=1{date_filter}
        ORDER BY date_trunc('month', date), batch_code, date DESC
    ) latest_per_batch_per_month
    GROUP BY month
    ORDER BY month
"""


def _rows(conn, sql, params=None):
    cursor = conn.execute(sql, params or {})
    columns = [d.name for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def fetch_mortality_by_month(conn, date_from=None, date_to=None):
    """{'piggery': [(month, deaths), ...], 'poultry': [...]} - registry metric `mortality`, monthly."""
    rows = _rows_or_empty(compute("mortality", conn, _scope(date_from, date_to, grain="month")))
    return {d: [(r["month_start"], r["deaths"]) for r in rows if r["domain"] == d]
            for d in ("piggery", "poultry")}


def fetch_headcount_by_month(conn, date_from=None, date_to=None):
    """{'piggery': [(month, headcount), ...], 'poultry': [...]}"""
    params = {}
    date_filter = date_filter_sql("date", date_from, date_to, params)
    pig = _rows(conn, MONTHLY_HEADCOUNT_SQL.format(
        table="pig_daily_log", count_col="closing_count", date_filter=date_filter), params)
    poultry = _rows(conn, MONTHLY_HEADCOUNT_SQL.format(
        table="poultry_daily_log", count_col="closing_birds", date_filter=date_filter), params)
    return {
        "piggery": [(r["month"], r["headcount"]) for r in pig],
        "poultry": [(r["month"], r["headcount"]) for r in poultry],
    }


def fetch_fcr_by_batch(conn, date_from=None, date_to=None):
    """[{'batch_code', 'domain', 'fcr'}, ...] - registry metric `fcr`. A batch without enough weight
    samples is left out of the chart (the chatbot says why)."""
    result = compute("fcr", conn, _scope(date_from, date_to))
    return [{"batch_code": r["batch_code"], "domain": r["domain"], "fcr": r["fcr"]}
            for r in result.rows if r["fcr"] is not None]


def fetch_expenses_vs_revenue(conn, date_from=None, date_to=None):
    """Registry metrics `expenses` and `revenue`, monthly."""
    expenses = _rows_or_empty(compute("expenses", conn, _scope(date_from, date_to, grain="month")))
    revenue = _rows_or_empty(compute("revenue", conn, _scope(date_from, date_to, grain="month")))
    return {
        "expenses": [(r["month_start"], r["total"]) for r in expenses],
        "revenue": [(r["month_start"], r["total"]) for r in revenue],
    }


def fetch_feed_cost_by_domain(conn, date_from=None, date_to=None):
    """[{'domain', 'total_kg', 'feed_cost'}, ...] - registry metric `feed_consumed_cost` (Finance page)."""
    rows = _rows_or_empty(compute("feed_consumed_cost", conn, _scope(date_from, date_to)))
    return sorted(({"domain": r["domain"], "total_kg": r["feed_kg"], "feed_cost": r["feed_cost"]} for r in rows),
                  key=lambda r: r["domain"])


def fetch_debtors(conn, date_from=None, date_to=None):
    """Sales still owing, every domain - registry metric `receivables`."""
    rows = _rows_or_empty(compute("receivables", conn, _scope(date_from, date_to)))
    return [{k: r[k] for k in ("date", "domain", "product", "buyer", "total_amount", "batch_ref")} for r in rows]


def fetch_findings(conn, date_from=None, date_to=None):
    """The three planted findings, using the exact same catalog SQL the
    chatbot itself answers from - real numbers, not hand-typed ones. When a
    date range excludes a finding's underlying event, that finding comes
    back None (honestly reflecting the selected range, not always-full-
    history) - see spec-chatbot-ui.md's grilled decision on this."""
    poultry_params = {}
    poultry_filter = date_filter_sql(
        POULTRY_MORTALITY_SPIKE_DATE_COLUMN, date_from, date_to, poultry_params)
    piggery_params = {}
    piggery_filter = date_filter_sql(
        PIGGERY_DISEASE_OUTBREAK_DATE_COLUMN, date_from, date_to, piggery_params)
    debtor_params = {}
    debtor_filter = date_filter_sql(
        CROP_DEBTOR_DATE_COLUMN, date_from, date_to, debtor_params)

    poultry_rows = _rows(conn, POULTRY_MORTALITY_SPIKE_SQL.format(date_filter=poultry_filter), poultry_params)
    piggery_rows = _rows(conn, PIGGERY_DISEASE_OUTBREAK_SQL.format(date_filter=piggery_filter), piggery_params)
    debtor_rows = _rows(conn, CROP_DEBTOR_SQL.format(date_filter=debtor_filter), debtor_params)
    return {
        "poultry_mortality_spike": poultry_rows[0] if poultry_rows else None,
        "piggery_disease_outbreak": piggery_rows[0] if piggery_rows else None,
        "crop_debtor": debtor_rows[0] if debtor_rows else None,
    }


DATA_COVERAGE_DATE_RANGE_SQL = """
    SELECT MIN(d), MAX(d) FROM (
        SELECT date AS d FROM pig_daily_log
        UNION ALL SELECT date FROM poultry_daily_log
        UNION ALL SELECT date FROM expenses
        UNION ALL SELECT date FROM revenue
        UNION ALL SELECT date FROM harvest_log
    ) all_dates
"""


def _latest_date(conn):
    return _rows(conn, DATA_COVERAGE_DATE_RANGE_SQL)[0]["max"]


def fetch_data_coverage(conn):
    """Batch/planting counts per domain, and the operational date range.
    There is no sync-run audit table (the sync is an idempotent
    truncate+reload with no timestamp column) - "how current is this data"
    is answered the same way the Lobels reference app answers it: the
    latest real record date across the domain log tables, not a fabricated
    sync-log timestamp."""
    date_range = _rows(conn, DATA_COVERAGE_DATE_RANGE_SQL)[0]
    counts = {
        "piggery_batches": _rows(conn, "SELECT COUNT(*) AS n FROM pig_batches")[0]["n"],
        "poultry_batches": _rows(conn, "SELECT COUNT(*) AS n FROM poultry_batches")[0]["n"],
        "plantings": _rows(conn, "SELECT COUNT(*) AS n FROM plantings")[0]["n"],
    }
    return {
        "earliest_date": date_range["min"],
        "latest_date": date_range["max"],
        "counts": counts,
    }


# ---------------------------------------------------------------------------
# Dashboard home view: stat cards + expense breakdown donut
#
# There's no historical status log (pig_batches.status/poultry_batches.status
# are current-only), so "was this batch active as of some past date" can't
# honestly be answered from the status column - it's derived instead from
# each batch's own logged date range (a batch is "active as of D" if it has
# daily-log rows both on/before and on/after D). This avoids the inaccuracy
# of using today's status to judge a batch's state 30 days ago.
# ---------------------------------------------------------------------------

TOTAL_PLACED_ASOF_SQL = """
    SELECT COALESCE(SUM(start_count), 0) AS total
    FROM pig_batches WHERE start_date <= %(cutoff)s
"""

TOTAL_CHICKS_ASOF_SQL = """
    SELECT COALESCE(SUM(chicks_placed), 0) AS total
    FROM poultry_batches WHERE placement_date <= %(cutoff)s
"""

TOTAL_BORN_ASOF_SQL = """
    SELECT COALESCE(SUM(born_alive), 0) AS total
    FROM breeding_farrowing
    WHERE farrow_date IS NOT NULL AND farrow_date <= %(cutoff)s
"""

EARLIEST_PLACEMENT_SQL = """
    SELECT LEAST(
        (SELECT MIN(start_date) FROM pig_batches),
        (SELECT MIN(placement_date) FROM poultry_batches)
    ) AS total
"""

EARLIEST_FARROW_SQL = """
    SELECT MIN(farrow_date) AS total FROM breeding_farrowing WHERE farrow_date IS NOT NULL
"""


def _scalar(conn, sql, params):
    return _rows(conn, sql, params)[0]["total"]


def _active_headcount_asof(conn, cutoff):
    # The registry's one definition of "animals on the farm as of a date" (registry/headcount.py).
    return headcount_asof(conn, "piggery", cutoff), headcount_asof(conn, "poultry", cutoff)


def _mortality_rate(conn, first_day, last_day):
    """Registry metric `mortality` over first_day..last_day INCLUSIVE: deaths / animals at risk. 0.0 when there
    is no record. (The card used to exclude its first day when a range was selected; both ends count now.)"""
    result = compute("mortality", conn, Scope(start=first_day, end=last_day))
    if not result.ok or result.figures["rate_pct"] is None:
        return 0.0
    return result.figures["rate_pct"]


def _pct_change(current, prior):
    """None when a meaningful percentage can't be computed (no prior-period
    baseline to compare against) - displayed as "New" rather than a
    fabricated or divide-by-zero number."""
    if not prior:
        return None
    return round((float(current) - float(prior)) / float(prior) * 100, 1)


def fetch_dashboard_stats(conn, date_from=None, date_to=None):
    """Four headline stat cards. Active Headcount and Mortality Rate are
    genuine flow/snapshot metrics: with no filter they compare (as-of the
    latest real data date) vs (30 days earlier), same as always; with a
    date range selected, the window becomes the selected range itself and
    the comparison baseline becomes the same-length period immediately
    before it. Total Livestock Placed and Piglets Born are lifetime
    cumulative totals - a percentage on a cumulative count is misleading
    regardless of the filter, so those two always get a neutral "Since
    <earliest date>" caption instead, using the filter's end date (or the
    latest real date, if unset) as the as-of cutoff.
    Returns a list of dicts: label, icon, value, and either pct_change
    (a number or None) or caption (a string) - never both."""
    latest = _latest_date(conn)
    range_end = date_to or latest

    if date_from and date_to:
        span_days = (date_to - date_from).days + 1
        window_start, window_end = date_from, date_to
        prior_window_end = date_from - datetime.timedelta(days=1)
        prior_window_start = prior_window_end - datetime.timedelta(days=span_days - 1)
    else:
        window_end = range_end
        window_start = window_end - datetime.timedelta(days=30)
        prior_window_end = window_start
        prior_window_start = prior_window_end - datetime.timedelta(days=30)

    total_now = (_scalar(conn, TOTAL_PLACED_ASOF_SQL, {"cutoff": range_end}) +
                 _scalar(conn, TOTAL_CHICKS_ASOF_SQL, {"cutoff": range_end}))
    earliest_placement = _scalar(conn, EARLIEST_PLACEMENT_SQL, {})
    placed_caption = (f"Since {earliest_placement} (through {range_end})"
                       if date_to else f"Since {earliest_placement}")

    active_pig_now, active_poultry_now = _active_headcount_asof(conn, window_end)
    active_pig_prior, active_poultry_prior = _active_headcount_asof(conn, prior_window_end)
    active_now = active_pig_now + active_poultry_now
    active_prior = active_pig_prior + active_poultry_prior

    born_now = _scalar(conn, TOTAL_BORN_ASOF_SQL, {"cutoff": range_end})
    earliest_farrow = _scalar(conn, EARLIEST_FARROW_SQL, {})
    if not earliest_farrow:
        born_caption = "No litters recorded yet"
    elif date_to:
        born_caption = f"Since {earliest_farrow} (through {range_end})"
    else:
        born_caption = f"Since {earliest_farrow}"

    # Mortality = deaths / animals at risk (opening headcount + additions), registry metric `mortality`.
    one_day = datetime.timedelta(days=1)
    if date_from and date_to:
        mortality_rate = _mortality_rate(conn, date_from, date_to)
        mortality_rate_prior = _mortality_rate(conn, prior_window_start, prior_window_end)
    else:       # the default windows are the 30 days ending at window_end / prior_window_end
        mortality_rate = _mortality_rate(conn, window_start + one_day, window_end)
        mortality_rate_prior = _mortality_rate(conn, prior_window_start + one_day, prior_window_end)
    mortality_label = ("Mortality Rate (selected range)" if (date_from and date_to)
                        else "Mortality Rate (30 days)")

    return [
        {"label": "Total Livestock Placed", "icon": "🐖", "value": f"{total_now:,}",
         "caption": placed_caption},
        {"label": "Active Headcount", "icon": "✅", "value": f"{active_now:,}",
         "pct_change": _pct_change(active_now, active_prior)},
        {"label": "Piglets Born (cumulative)", "icon": "🐷", "value": f"{born_now:,}",
         "caption": born_caption},
        {"label": mortality_label, "icon": "⚠️", "value": f"{mortality_rate}%",
         "pct_change": _pct_change(mortality_rate, mortality_rate_prior)},
    ]


def fetch_expense_breakdown(conn):
    """[{'category', 'total'}, ...] largest first - registry metric `expenses`, by category."""
    rows = _rows_or_empty(compute("expenses", conn, Scope(dimension="category")))
    return [{"category": r["key"], "total": r["total"]} for r in rows]


# ---------------------------------------------------------------------------
# Feeding page
# ---------------------------------------------------------------------------


def fetch_feed_cost_by_month(conn, date_from=None, date_to=None):
    """Feeding page. Registry metric `feed_consumed_cost`, monthly - the SAME definition the Finance page and
    the chatbot use (daily-log feed_kg priced from feed_inventory). This page used to cost
    feed_inventory.used_kg instead; see registry/CHANGELOG-dashboard.md."""
    rows = _rows_or_empty(compute("feed_consumed_cost", conn, _scope(date_from, date_to, grain="month")))
    return {d: [(r["month_start"], r["feed_cost"]) for r in rows if r["domain"] == d]
            for d in ("piggery", "poultry")}


# ---------------------------------------------------------------------------
# Health page
# ---------------------------------------------------------------------------

RECENT_HEALTH_EVENTS_SQL = """
    SELECT date, domain, batch_ref, event_type, diagnosis, cost
    FROM health_log WHERE 1=1{date_filter} ORDER BY date DESC LIMIT 10
"""


def fetch_health_summary(conn, date_from=None, date_to=None):
    """[{'domain', 'event_type', 'event_count', 'total_cost'}, ...] - registry metric `health_events`."""
    rows = _rows_or_empty(compute("health_events", conn, _scope(date_from, date_to)))
    return [{k: r[k] for k in ("domain", "event_type", "event_count", "total_cost")} for r in rows]


def fetch_recent_health_events(conn, date_from=None, date_to=None):
    params = {}
    date_filter = date_filter_sql("date", date_from, date_to, params)
    return _rows(conn, RECENT_HEALTH_EVENTS_SQL.format(date_filter=date_filter), params)


# ---------------------------------------------------------------------------
# Breeding page
# ---------------------------------------------------------------------------

def fetch_breeding_summary(conn, date_from=None, date_to=None):
    """Registry metric `breeding`."""
    result = compute("breeding", conn, _scope(date_from, date_to))
    figures = result.figures if result.ok else {}
    return {
        "records": result.rows if result.ok else [],
        "total_litters": figures.get("litters", 0),
        "total_born_alive": figures.get("born_alive", 0),
        "total_weaned": figures.get("weaned", 0),
    }


# ---------------------------------------------------------------------------
# Settings page - real farm configuration, not a fabricated settings UI
# ---------------------------------------------------------------------------

FARM_PROFILE_SQL = """
    SELECT farm_code, farm_name, region_district, currency, total_hectares,
           module_piggery_active, module_poultry_active, module_crops_active,
           financial_year_start
    FROM farm_profile LIMIT 1
"""


def fetch_farm_profile(conn):
    rows = _rows(conn, FARM_PROFILE_SQL)
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# Chat page's "Quick Lookup" widget - pen and batch, a fast at-a-glance
# summary distinct from asking the chatbot a full question. Debtor lookup
# needs no new query - it reuses fetch_debtors above directly.
# ---------------------------------------------------------------------------

PEN_SUMMARY_SQL = """
    SELECT b.batch_code, b.breed, b.status, b.start_date,
           b.target_market_date AS target_date,
           lc.date AS latest_date, lc.closing_count AS headcount
    FROM pig_batches b
    LEFT JOIN LATERAL (
        SELECT date, closing_count FROM pig_daily_log
        WHERE batch_code = b.batch_code ORDER BY date DESC LIMIT 1
    ) lc ON true
    WHERE b.pen = %(pen)s
    ORDER BY b.start_date DESC
"""


def fetch_pen_summary(conn, pen):
    """Every batch ever recorded in `pen` (pens get reused over a farm's
    life, unlike batch codes), most recent first - piggery-only, since
    poultry_batches tracks a house, not a pen, in this schema."""
    return _rows(conn, PEN_SUMMARY_SQL, {"pen": pen})


PIG_BATCH_SUMMARY_SQL = """
    SELECT b.batch_code, 'piggery' AS domain, b.pen AS location, b.breed,
           b.status, b.start_date, b.target_market_date AS target_date,
           lc.date AS latest_date, lc.closing_count AS headcount,
           lw.avg_weight_kg AS avg_weight, 'kg' AS weight_unit
    FROM pig_batches b
    LEFT JOIN LATERAL (
        SELECT date, closing_count FROM pig_daily_log
        WHERE batch_code = b.batch_code ORDER BY date DESC LIMIT 1
    ) lc ON true
    LEFT JOIN LATERAL (
        SELECT avg_weight_kg FROM pig_weights
        WHERE batch_code = b.batch_code ORDER BY date DESC LIMIT 1
    ) lw ON true
    WHERE b.batch_code = %(batch_code)s
"""

POULTRY_BATCH_SUMMARY_SQL = """
    SELECT b.batch_code, 'poultry' AS domain, b.house AS location, b.breed,
           b.status, b.placement_date AS start_date,
           b.target_off_date AS target_date,
           lc.date AS latest_date, lc.closing_birds AS headcount,
           lw.avg_weight_g AS avg_weight, 'g' AS weight_unit
    FROM poultry_batches b
    LEFT JOIN LATERAL (
        SELECT date, closing_birds FROM poultry_daily_log
        WHERE batch_code = b.batch_code ORDER BY date DESC LIMIT 1
    ) lc ON true
    LEFT JOIN LATERAL (
        SELECT avg_weight_g FROM poultry_weights
        WHERE batch_code = b.batch_code ORDER BY date DESC LIMIT 1
    ) lw ON true
    WHERE b.batch_code = %(batch_code)s
"""


def fetch_batch_summary(conn, batch_code):
    """Checks pig_batches first, then poultry_batches - a batch code
    belongs to exactly one domain in this schema, never both. Both queries
    return the same normalized column set (location/headcount/avg_weight/
    weight_unit) so the caller never needs to know which domain matched."""
    rows = _rows(conn, PIG_BATCH_SUMMARY_SQL, {"batch_code": batch_code})
    if rows:
        return rows[0]
    rows = _rows(conn, POULTRY_BATCH_SUMMARY_SQL, {"batch_code": batch_code})
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# Domain Lookup page - pick a domain, see its key metrics without typing a
# chat question. See .scratch/domain-summary-lookup/issues/
# 01-domain-summary-lookup-tab.md. Mostly reuses existing fetch_* functions'
# already domain-tagged/domain-split results; CROPS_SUMMARY_SQL below is the
# one genuinely new query, since no crops-domain summary existed anywhere
# in this module before this page.
# ---------------------------------------------------------------------------

_DOMAIN_MODULE_COLUMNS = {
    "piggery": "module_piggery_active",
    "poultry": "module_poultry_active",
    "crops": "module_crops_active",
}


def fetch_crops_summary(conn, date_from=None, date_to=None):
    """Crops-domain summary: registry metrics `crop_plantings` (area, plots, plantings - by planting date)
    and `harvest_yield` (total harvested - by harvest date, not the planting date)."""
    plantings = compute("crop_plantings", conn, _scope(date_from, date_to))
    harvest = compute("harvest_yield", conn, _scope(date_from, date_to))
    p = plantings.figures if plantings.ok else {}
    return {
        "total_area_ha": float(p.get("total_area_ha", 0)),
        "plot_count": p.get("plot_count", 0),
        "planting_count": p.get("planting_count", 0),
        "active_planting_count": p.get("active_planting_count", 0),
        "total_harvested_kg": float(harvest.figures["total_harvested_kg"]) if harvest.ok else 0.0,
    }


def fetch_domain_summary(conn, domain, date_from=None, date_to=None):
    """One domain's key metrics for the Domain Lookup page. `domain` is one
    of "piggery"/"poultry"/"crops". Returns {"module_active": False} if the
    farm has that module turned off - an honest state, not empty/misleading
    data, per this page's ticket."""
    profile = fetch_farm_profile(conn)
    if profile is None or not profile[_DOMAIN_MODULE_COLUMNS[domain]]:
        return {"module_active": False}

    if domain == "crops":
        summary = fetch_crops_summary(conn, date_from=date_from, date_to=date_to)
        debtors = [d for d in fetch_debtors(conn, date_from=date_from, date_to=date_to)
                   if d["domain"] == "crops"]
        summary["module_active"] = True
        summary["outstanding_debtor_count"] = len(debtors)
        summary["outstanding_amount"] = float(sum(d["total_amount"] for d in debtors))
        return summary

    # "Current headcount" reuses the same active-as-of-a-date methodology
    # the dashboard's stat card and the chatbot's tier-3 headcount tool
    # already use - not fetch_headcount_by_month's coarser monthly grain,
    # which would understate freshness for a single-domain lookup.
    cutoff = date_to or _latest_date(conn)
    headcount = headcount_asof(conn, domain, cutoff)

    total_deaths = sum(d for _, d in fetch_mortality_by_month(
        conn, date_from=date_from, date_to=date_to)[domain])
    # The registry's exact total for this domain - NOT a sum of the Feeding page's rounded monthly values, which can
    # differ from the Finance page by cents.
    feed = compute("feed_consumed_cost", conn, _scope(date_from, date_to, domains=(domain,)))
    total_feed_cost = feed.figures["total_cost"] if feed.ok else 0.0
    health = compute("health_events", conn, _scope(date_from, date_to, domains=(domain,)))
    health_figures = health.figures if health.ok else {"total_events": 0, "total_cost": 0.0}

    return {
        "module_active": True,
        "as_of": str(cutoff),
        "headcount": headcount,
        "total_deaths": total_deaths,
        "total_feed_cost": float(total_feed_cost),
        "total_health_cost": health_figures["total_cost"],
        "total_health_events": health_figures["total_events"],
    }
