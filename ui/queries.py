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
    active_headcount_asof,
    date_filter_sql,
)

FEED_COST_BY_DOMAIN_SQL = """
    WITH domain_usage AS (
        SELECT date, 'piggery' AS domain, feed_type, feed_kg FROM pig_daily_log
        UNION ALL
        SELECT date, 'poultry' AS domain, feed_type, feed_kg FROM poultry_daily_log
    ),
    priced AS (
        SELECT u.domain, u.feed_kg,
            (SELECT fi.unit_cost_per_kg FROM feed_inventory fi
             WHERE fi.domain = u.domain AND fi.feed_type = u.feed_type
               AND fi.date <= u.date
             ORDER BY fi.date DESC LIMIT 1) AS unit_cost_per_kg
        FROM domain_usage u
        WHERE 1=1{date_filter}
    )
    SELECT domain, ROUND(SUM(feed_kg), 1) AS total_kg,
           ROUND(SUM(feed_kg * unit_cost_per_kg), 2) AS feed_cost
    FROM priced
    GROUP BY domain
    ORDER BY domain
"""

MONTHLY_MORTALITY_SQL = """
    SELECT date_trunc('month', date)::date AS month, SUM(deaths) AS deaths
    FROM {table}
    WHERE 1=1{date_filter}
    GROUP BY 1
    ORDER BY 1
"""

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

PIG_FCR_SQL = """
    WITH feed AS (
        SELECT batch_code, SUM(feed_kg) AS total_feed_kg
        FROM pig_daily_log WHERE 1=1{date_filter} GROUP BY batch_code
    ),
    latest_count AS (
        SELECT DISTINCT ON (batch_code) batch_code, closing_count
        FROM pig_daily_log WHERE 1=1{date_filter} ORDER BY batch_code, date DESC
    ),
    latest_weight AS (
        SELECT DISTINCT ON (batch_code) batch_code, avg_weight_kg
        FROM pig_weights WHERE 1=1{date_filter} ORDER BY batch_code, date DESC
    )
    SELECT b.batch_code,
           f.total_feed_kg,
           (lw.avg_weight_kg - b.start_avg_kg) * lc.closing_count AS weight_gain_kg,
           ROUND(f.total_feed_kg /
                 NULLIF((lw.avg_weight_kg - b.start_avg_kg) * lc.closing_count, 0), 2
           ) AS fcr
    FROM pig_batches b
    JOIN feed f ON f.batch_code = b.batch_code
    JOIN latest_count lc ON lc.batch_code = b.batch_code
    JOIN latest_weight lw ON lw.batch_code = b.batch_code
    ORDER BY b.batch_code
"""

POULTRY_FCR_SQL = """
    WITH feed AS (
        SELECT batch_code, SUM(feed_kg) AS total_feed_kg
        FROM poultry_daily_log WHERE 1=1{date_filter} GROUP BY batch_code
    ),
    latest_count AS (
        SELECT DISTINCT ON (batch_code) batch_code, closing_birds
        FROM poultry_daily_log WHERE 1=1{date_filter} ORDER BY batch_code, date DESC
    ),
    latest_weight AS (
        SELECT DISTINCT ON (batch_code) batch_code, avg_weight_g
        FROM poultry_weights WHERE 1=1{date_filter} ORDER BY batch_code, date DESC
    )
    SELECT b.batch_code,
           f.total_feed_kg,
           (lw.avg_weight_g / 1000.0) * lc.closing_birds AS weight_gain_kg,
           ROUND(f.total_feed_kg /
                 NULLIF((lw.avg_weight_g / 1000.0) * lc.closing_birds, 0), 2
           ) AS fcr
    FROM poultry_batches b
    JOIN feed f ON f.batch_code = b.batch_code
    JOIN latest_count lc ON lc.batch_code = b.batch_code
    JOIN latest_weight lw ON lw.batch_code = b.batch_code
    ORDER BY b.batch_code
"""

EXPENSES_BY_MONTH_SQL = """
    SELECT date_trunc('month', date)::date AS month, SUM(total_cost) AS total
    FROM expenses WHERE 1=1{date_filter} GROUP BY 1 ORDER BY 1
"""

REVENUE_BY_MONTH_SQL = """
    SELECT date_trunc('month', date)::date AS month, SUM(total_amount) AS total
    FROM revenue WHERE 1=1{date_filter} GROUP BY 1 ORDER BY 1
"""

DEBTORS_SQL = """
    SELECT date, domain, product, buyer, total_amount, batch_ref
    FROM revenue
    WHERE payment_status = 'Owing'{date_filter}
    ORDER BY date
"""


def _rows(conn, sql, params=None):
    cursor = conn.execute(sql, params or {})
    columns = [d.name for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def fetch_mortality_by_month(conn, date_from=None, date_to=None):
    """{'piggery': [(month, deaths), ...], 'poultry': [...]}"""
    params = {}
    date_filter = date_filter_sql("date", date_from, date_to, params)
    sql_pig = MONTHLY_MORTALITY_SQL.format(table="pig_daily_log", date_filter=date_filter)
    sql_poultry = MONTHLY_MORTALITY_SQL.format(table="poultry_daily_log", date_filter=date_filter)
    pig = _rows(conn, sql_pig, params)
    poultry = _rows(conn, sql_poultry, params)
    return {
        "piggery": [(r["month"], r["deaths"] or 0) for r in pig],
        "poultry": [(r["month"], r["deaths"] or 0) for r in poultry],
    }


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
    """[{'batch_code', 'domain', 'fcr'}, ...] across both pigs and poultry.
    When a date range is given, feed consumed and the latest weight/count
    samples are all bounded to that range - the batch's starting weight
    stays fixed (a batch-level constant, not a flow value), so FCR for a
    range that starts partway through a batch's life is an approximation,
    not an exact "gain within this window" figure."""
    params = {}
    date_filter = date_filter_sql("date", date_from, date_to, params)
    pig = _rows(conn, PIG_FCR_SQL.format(date_filter=date_filter), params)
    poultry = _rows(conn, POULTRY_FCR_SQL.format(date_filter=date_filter), params)
    return (
        [{"batch_code": r["batch_code"], "domain": "piggery", "fcr": r["fcr"]}
         for r in pig if r["fcr"] is not None] +
        [{"batch_code": r["batch_code"], "domain": "poultry", "fcr": r["fcr"]}
         for r in poultry if r["fcr"] is not None]
    )


def fetch_expenses_vs_revenue(conn, date_from=None, date_to=None):
    params = {}
    date_filter = date_filter_sql("date", date_from, date_to, params)
    expenses = _rows(conn, EXPENSES_BY_MONTH_SQL.format(date_filter=date_filter), params)
    revenue = _rows(conn, REVENUE_BY_MONTH_SQL.format(date_filter=date_filter), params)
    return {
        "expenses": [(r["month"], r["total"] or 0) for r in expenses],
        "revenue": [(r["month"], r["total"] or 0) for r in revenue],
    }


def fetch_feed_cost_by_domain(conn, date_from=None, date_to=None):
    params = {}
    date_filter = date_filter_sql("u.date", date_from, date_to, params)
    return _rows(conn, FEED_COST_BY_DOMAIN_SQL.format(date_filter=date_filter), params)


def fetch_debtors(conn, date_from=None, date_to=None):
    params = {}
    date_filter = date_filter_sql("date", date_from, date_to, params)
    return _rows(conn, DEBTORS_SQL.format(date_filter=date_filter), params)


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

DEATHS_IN_WINDOW_SQL = """
    SELECT COALESCE(SUM(deaths), 0) AS total
    FROM {table} WHERE date > %(start)s AND date <= %(end)s
"""

EXPENSE_BREAKDOWN_SQL = """
    SELECT category, SUM(total_cost) AS total
    FROM expenses GROUP BY category ORDER BY total DESC
"""


def _scalar(conn, sql, params):
    return _rows(conn, sql, params)[0]["total"]


def _active_headcount_asof(conn, cutoff):
    pig = active_headcount_asof(conn, cutoff, "pig_daily_log", "closing_count")
    poultry = active_headcount_asof(conn, cutoff, "poultry_daily_log", "closing_birds")
    return pig, poultry


def _pct_change(current, prior):
    """None when a meaningful percentage can't be computed (no prior-period
    baseline to compare against) - displayed as "New" rather than a
    fabricated or divide-by-zero number."""
    if not prior:
        return None
    return round((float(current) - float(prior)) / float(prior) * 100, 1)


def _sum(pair):
    return pair[0] + pair[1]


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

    deaths_window = (
        _scalar(conn, DEATHS_IN_WINDOW_SQL.format(table="pig_daily_log"),
                {"start": window_start, "end": window_end}) +
        _scalar(conn, DEATHS_IN_WINDOW_SQL.format(table="poultry_daily_log"),
                {"start": window_start, "end": window_end})
    )
    deaths_prior_window = (
        _scalar(conn, DEATHS_IN_WINDOW_SQL.format(table="pig_daily_log"),
                {"start": prior_window_start, "end": prior_window_end}) +
        _scalar(conn, DEATHS_IN_WINDOW_SQL.format(table="poultry_daily_log"),
                {"start": prior_window_start, "end": prior_window_end})
    )
    base_now = _sum(_active_headcount_asof(conn, window_end))
    base_prior = _sum(_active_headcount_asof(conn, prior_window_end))
    mortality_rate = round(deaths_window / base_now * 100, 2) if base_now else 0.0
    mortality_rate_prior = (
        round(deaths_prior_window / base_prior * 100, 2) if base_prior else 0.0
    )
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
    return _rows(conn, EXPENSE_BREAKDOWN_SQL)


# ---------------------------------------------------------------------------
# Feeding page
# ---------------------------------------------------------------------------

FEED_COST_BY_MONTH_SQL = """
    SELECT date_trunc('month', date)::date AS month, domain,
           SUM(used_kg * unit_cost_per_kg) AS cost
    FROM feed_inventory WHERE 1=1{date_filter} GROUP BY 1, 2 ORDER BY 1, 2
"""


def fetch_feed_cost_by_month(conn, date_from=None, date_to=None):
    params = {}
    date_filter = date_filter_sql("date", date_from, date_to, params)
    rows = _rows(conn, FEED_COST_BY_MONTH_SQL.format(date_filter=date_filter), params)
    return {
        "piggery": [(r["month"], float(r["cost"] or 0)) for r in rows if r["domain"] == "piggery"],
        "poultry": [(r["month"], float(r["cost"] or 0)) for r in rows if r["domain"] == "poultry"],
    }


# ---------------------------------------------------------------------------
# Health page
# ---------------------------------------------------------------------------

HEALTH_BY_EVENT_TYPE_SQL = """
    SELECT domain, event_type, COUNT(*) AS event_count, SUM(cost) AS total_cost
    FROM health_log WHERE 1=1{date_filter} GROUP BY domain, event_type ORDER BY domain, event_type
"""

RECENT_HEALTH_EVENTS_SQL = """
    SELECT date, domain, batch_ref, event_type, diagnosis, cost
    FROM health_log WHERE 1=1{date_filter} ORDER BY date DESC LIMIT 10
"""


def fetch_health_summary(conn, date_from=None, date_to=None):
    params = {}
    date_filter = date_filter_sql("date", date_from, date_to, params)
    return _rows(conn, HEALTH_BY_EVENT_TYPE_SQL.format(date_filter=date_filter), params)


def fetch_recent_health_events(conn, date_from=None, date_to=None):
    params = {}
    date_filter = date_filter_sql("date", date_from, date_to, params)
    return _rows(conn, RECENT_HEALTH_EVENTS_SQL.format(date_filter=date_filter), params)


# ---------------------------------------------------------------------------
# Breeding page
# ---------------------------------------------------------------------------

FARROWING_RECORDS_SQL = """
    SELECT sow_tag, service_date, farrow_date, born_alive, stillborn, weaned_count
    FROM breeding_farrowing WHERE 1=1{date_filter} ORDER BY service_date
"""


def fetch_breeding_summary(conn, date_from=None, date_to=None):
    params = {}
    date_filter = date_filter_sql("service_date", date_from, date_to, params)
    rows = _rows(conn, FARROWING_RECORDS_SQL.format(date_filter=date_filter), params)
    completed = [r for r in rows if r["farrow_date"] is not None]
    return {
        "records": rows,
        "total_litters": len(completed),
        "total_born_alive": sum(r["born_alive"] or 0 for r in completed),
        "total_weaned": sum(r["weaned_count"] or 0 for r in completed),
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

CROPS_PLANTINGS_SUMMARY_SQL = """
    SELECT
        COALESCE(SUM(area_ha), 0) AS total_area_ha,
        COUNT(DISTINCT plot_code) AS plot_count,
        COUNT(*) AS planting_count,
        COUNT(*) FILTER (WHERE status != 'Harvested') AS active_planting_count
    FROM plantings
    WHERE 1=1{date_filter}
"""

CROPS_HARVEST_SQL = """
    SELECT COALESCE(SUM(quantity_kg), 0) AS total_harvested_kg
    FROM harvest_log
    WHERE 1=1{date_filter}
"""


def fetch_crops_summary(conn, date_from=None, date_to=None):
    """Crops-domain summary: total area planted (filtered by
    planting_date), plot/planting counts, and total harvested (filtered by
    harvest_log.date - a real harvest date, not the planting date)."""
    plantings_params = {}
    plantings_filter = date_filter_sql("planting_date", date_from, date_to, plantings_params)
    plantings = _rows(
        conn, CROPS_PLANTINGS_SUMMARY_SQL.format(date_filter=plantings_filter), plantings_params
    )[0]

    harvest_params = {}
    harvest_filter = date_filter_sql("date", date_from, date_to, harvest_params)
    harvest = _rows(
        conn, CROPS_HARVEST_SQL.format(date_filter=harvest_filter), harvest_params
    )[0]

    return {
        "total_area_ha": float(plantings["total_area_ha"]),
        "plot_count": plantings["plot_count"],
        "planting_count": plantings["planting_count"],
        "active_planting_count": plantings["active_planting_count"],
        "total_harvested_kg": float(harvest["total_harvested_kg"]),
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

    table = "pig_daily_log" if domain == "piggery" else "poultry_daily_log"
    count_col = "closing_count" if domain == "piggery" else "closing_birds"
    # "Current headcount" reuses the same active-as-of-a-date methodology
    # the dashboard's stat card and the chatbot's tier-3 headcount tool
    # already use - not fetch_headcount_by_month's coarser monthly grain,
    # which would understate freshness for a single-domain lookup.
    cutoff = date_to or _latest_date(conn)
    headcount = active_headcount_asof(conn, cutoff, table, count_col)

    total_deaths = sum(d for _, d in fetch_mortality_by_month(
        conn, date_from=date_from, date_to=date_to)[domain])
    total_feed_cost = sum(c for _, c in fetch_feed_cost_by_month(
        conn, date_from=date_from, date_to=date_to)[domain])
    health_rows = [h for h in fetch_health_summary(conn, date_from=date_from, date_to=date_to)
                   if h["domain"] == domain]

    return {
        "module_active": True,
        "as_of": str(cutoff),
        "headcount": headcount,
        "total_deaths": total_deaths,
        "total_feed_cost": float(total_feed_cost),
        "total_health_cost": float(sum(h["total_cost"] or 0 for h in health_rows)),
        "total_health_events": sum(h["event_count"] for h in health_rows),
    }
