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
    CROP_DEBTOR_SQL,
    PIGGERY_DISEASE_OUTBREAK_SQL,
    POULTRY_MORTALITY_SPIKE_SQL,
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
    GROUP BY 1
    ORDER BY 1
"""

MONTHLY_HEADCOUNT_SQL = """
    SELECT month, SUM(headcount) AS headcount FROM (
        SELECT DISTINCT ON (date_trunc('month', date), batch_code)
            date_trunc('month', date)::date AS month,
            batch_code, {count_col} AS headcount
        FROM {table}
        ORDER BY date_trunc('month', date), batch_code, date DESC
    ) latest_per_batch_per_month
    GROUP BY month
    ORDER BY month
"""

PIG_FCR_SQL = """
    WITH feed AS (
        SELECT batch_code, SUM(feed_kg) AS total_feed_kg
        FROM pig_daily_log GROUP BY batch_code
    ),
    latest_count AS (
        SELECT DISTINCT ON (batch_code) batch_code, closing_count
        FROM pig_daily_log ORDER BY batch_code, date DESC
    ),
    latest_weight AS (
        SELECT DISTINCT ON (batch_code) batch_code, avg_weight_kg
        FROM pig_weights ORDER BY batch_code, date DESC
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
        FROM poultry_daily_log GROUP BY batch_code
    ),
    latest_count AS (
        SELECT DISTINCT ON (batch_code) batch_code, closing_birds
        FROM poultry_daily_log ORDER BY batch_code, date DESC
    ),
    latest_weight AS (
        SELECT DISTINCT ON (batch_code) batch_code, avg_weight_g
        FROM poultry_weights ORDER BY batch_code, date DESC
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
    FROM expenses GROUP BY 1 ORDER BY 1
"""

REVENUE_BY_MONTH_SQL = """
    SELECT date_trunc('month', date)::date AS month, SUM(total_amount) AS total
    FROM revenue GROUP BY 1 ORDER BY 1
"""

DEBTORS_SQL = """
    SELECT date, domain, product, buyer, total_amount, batch_ref
    FROM revenue
    WHERE payment_status = 'Owing'
    ORDER BY date
"""


def _rows(conn, sql, params=None):
    cursor = conn.execute(sql, params or {})
    columns = [d.name for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def fetch_mortality_by_month(conn):
    """{'piggery': [(month, deaths), ...], 'poultry': [...]}"""
    pig = _rows(conn, MONTHLY_MORTALITY_SQL.format(table="pig_daily_log"))
    poultry = _rows(conn, MONTHLY_MORTALITY_SQL.format(table="poultry_daily_log"))
    return {
        "piggery": [(r["month"], r["deaths"] or 0) for r in pig],
        "poultry": [(r["month"], r["deaths"] or 0) for r in poultry],
    }


def fetch_headcount_by_month(conn):
    """{'piggery': [(month, headcount), ...], 'poultry': [...]}"""
    pig = _rows(conn, MONTHLY_HEADCOUNT_SQL.format(
        table="pig_daily_log", count_col="closing_count"))
    poultry = _rows(conn, MONTHLY_HEADCOUNT_SQL.format(
        table="poultry_daily_log", count_col="closing_birds"))
    return {
        "piggery": [(r["month"], r["headcount"]) for r in pig],
        "poultry": [(r["month"], r["headcount"]) for r in poultry],
    }


def fetch_fcr_by_batch(conn):
    """[{'batch_code', 'domain', 'fcr'}, ...] across both pigs and poultry."""
    pig = _rows(conn, PIG_FCR_SQL)
    poultry = _rows(conn, POULTRY_FCR_SQL)
    return (
        [{"batch_code": r["batch_code"], "domain": "piggery", "fcr": r["fcr"]}
         for r in pig if r["fcr"] is not None] +
        [{"batch_code": r["batch_code"], "domain": "poultry", "fcr": r["fcr"]}
         for r in poultry if r["fcr"] is not None]
    )


def fetch_expenses_vs_revenue(conn):
    expenses = _rows(conn, EXPENSES_BY_MONTH_SQL)
    revenue = _rows(conn, REVENUE_BY_MONTH_SQL)
    return {
        "expenses": [(r["month"], r["total"] or 0) for r in expenses],
        "revenue": [(r["month"], r["total"] or 0) for r in revenue],
    }


def fetch_feed_cost_by_domain(conn):
    return _rows(conn, FEED_COST_BY_DOMAIN_SQL)


def fetch_debtors(conn):
    return _rows(conn, DEBTORS_SQL)


def fetch_findings(conn):
    """The three planted findings, using the exact same catalog SQL the
    chatbot itself answers from - real numbers, not hand-typed ones."""
    poultry_rows = _rows(conn, POULTRY_MORTALITY_SPIKE_SQL)
    piggery_rows = _rows(conn, PIGGERY_DISEASE_OUTBREAK_SQL)
    debtor_rows = _rows(conn, CROP_DEBTOR_SQL)
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

ACTIVE_HEADCOUNT_ASOF_SQL = """
    WITH batch_range AS (
        SELECT batch_code, MIN(date) AS first_date, MAX(date) AS last_date
        FROM {table} GROUP BY batch_code
    ),
    active_batches AS (
        SELECT batch_code FROM batch_range
        WHERE first_date <= %(cutoff)s AND last_date >= %(cutoff)s
    ),
    latest_count AS (
        SELECT DISTINCT ON (batch_code) batch_code, {count_col} AS headcount
        FROM {table} WHERE date <= %(cutoff)s
        ORDER BY batch_code, date DESC
    )
    SELECT COALESCE(SUM(lc.headcount), 0) AS total
    FROM active_batches ab JOIN latest_count lc ON lc.batch_code = ab.batch_code
"""

TOTAL_BORN_ASOF_SQL = """
    SELECT COALESCE(SUM(born_alive), 0) AS total
    FROM breeding_farrowing
    WHERE farrow_date IS NOT NULL AND farrow_date <= %(cutoff)s
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
    pig = _scalar(conn, ACTIVE_HEADCOUNT_ASOF_SQL.format(
        table="pig_daily_log", count_col="closing_count"), {"cutoff": cutoff})
    poultry = _scalar(conn, ACTIVE_HEADCOUNT_ASOF_SQL.format(
        table="poultry_daily_log", count_col="closing_birds"), {"cutoff": cutoff})
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


def fetch_dashboard_stats(conn):
    """Four headline stat cards, each as a (value as-of the latest real
    data date) vs (the same computation as-of 30 days earlier) comparison -
    entirely derived from real timestamped rows, never a fabricated
    baseline. Returns a list of dicts: label, icon, value, unit, pct_change."""
    ref_date = _latest_date(conn)
    prior_date = ref_date - datetime.timedelta(days=30)
    window_start = ref_date - datetime.timedelta(days=30)
    prior_window_start = ref_date - datetime.timedelta(days=60)

    total_now = (_scalar(conn, TOTAL_PLACED_ASOF_SQL, {"cutoff": ref_date}) +
                 _scalar(conn, TOTAL_CHICKS_ASOF_SQL, {"cutoff": ref_date}))
    total_prior = (_scalar(conn, TOTAL_PLACED_ASOF_SQL, {"cutoff": prior_date}) +
                   _scalar(conn, TOTAL_CHICKS_ASOF_SQL, {"cutoff": prior_date}))

    active_pig_now, active_poultry_now = _active_headcount_asof(conn, ref_date)
    active_pig_prior, active_poultry_prior = _active_headcount_asof(conn, prior_date)
    active_now = active_pig_now + active_poultry_now
    active_prior = active_pig_prior + active_poultry_prior

    born_now = _scalar(conn, TOTAL_BORN_ASOF_SQL, {"cutoff": ref_date})
    born_prior = _scalar(conn, TOTAL_BORN_ASOF_SQL, {"cutoff": prior_date})

    deaths_window = (
        _scalar(conn, DEATHS_IN_WINDOW_SQL.format(table="pig_daily_log"),
                {"start": window_start, "end": ref_date}) +
        _scalar(conn, DEATHS_IN_WINDOW_SQL.format(table="poultry_daily_log"),
                {"start": window_start, "end": ref_date})
    )
    deaths_prior_window = (
        _scalar(conn, DEATHS_IN_WINDOW_SQL.format(table="pig_daily_log"),
                {"start": prior_window_start, "end": prior_date}) +
        _scalar(conn, DEATHS_IN_WINDOW_SQL.format(table="poultry_daily_log"),
                {"start": prior_window_start, "end": prior_date})
    )
    base_now = _sum(_active_headcount_asof(conn, window_start))
    base_prior = _sum(_active_headcount_asof(conn, prior_window_start))
    mortality_rate = round(deaths_window / base_now * 100, 2) if base_now else 0.0
    mortality_rate_prior = (
        round(deaths_prior_window / base_prior * 100, 2) if base_prior else 0.0
    )

    return [
        {"label": "Total Livestock Placed", "icon": "🐖", "value": f"{total_now:,}",
         "pct_change": _pct_change(total_now, total_prior)},
        {"label": "Active Headcount", "icon": "✅", "value": f"{active_now:,}",
         "pct_change": _pct_change(active_now, active_prior)},
        {"label": "Piglets Born (cumulative)", "icon": "🐷", "value": f"{born_now:,}",
         "pct_change": _pct_change(born_now, born_prior)},
        {"label": "Mortality Rate (30 days)", "icon": "⚠️", "value": f"{mortality_rate}%",
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
    FROM feed_inventory GROUP BY 1, 2 ORDER BY 1, 2
"""


def fetch_feed_cost_by_month(conn):
    rows = _rows(conn, FEED_COST_BY_MONTH_SQL)
    return {
        "piggery": [(r["month"], float(r["cost"] or 0)) for r in rows if r["domain"] == "piggery"],
        "poultry": [(r["month"], float(r["cost"] or 0)) for r in rows if r["domain"] == "poultry"],
    }


# ---------------------------------------------------------------------------
# Health page
# ---------------------------------------------------------------------------

HEALTH_BY_EVENT_TYPE_SQL = """
    SELECT domain, event_type, COUNT(*) AS event_count, SUM(cost) AS total_cost
    FROM health_log GROUP BY domain, event_type ORDER BY domain, event_type
"""

RECENT_HEALTH_EVENTS_SQL = """
    SELECT date, domain, batch_ref, event_type, diagnosis, cost
    FROM health_log ORDER BY date DESC LIMIT 10
"""


def fetch_health_summary(conn):
    return _rows(conn, HEALTH_BY_EVENT_TYPE_SQL)


def fetch_recent_health_events(conn):
    return _rows(conn, RECENT_HEALTH_EVENTS_SQL)


# ---------------------------------------------------------------------------
# Breeding page
# ---------------------------------------------------------------------------

FARROWING_RECORDS_SQL = """
    SELECT sow_tag, service_date, farrow_date, born_alive, stillborn, weaned_count
    FROM breeding_farrowing ORDER BY service_date
"""


def fetch_breeding_summary(conn):
    rows = _rows(conn, FARROWING_RECORDS_SQL)
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
