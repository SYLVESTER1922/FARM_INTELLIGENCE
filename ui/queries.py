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
