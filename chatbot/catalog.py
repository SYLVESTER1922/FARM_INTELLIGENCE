"""
The query catalog: a fixed, hand-written set of parameterized SQL queries.
Every possible arithmetic operation the chatbot can answer lives here -
never generated per-request, never delegated to an LLM. See
spec-chatbot-answer-engine.md's "Query catalog" decision.
"""

from dataclasses import dataclass, field


@dataclass
class CatalogQuery:
    query_id: str
    phrases: list         # example phrasings for the tier-1 matcher's cluster
    sql: str               # uses %(param)s placeholders for required_params
    domains: list           # piggery/poultry/crops this query touches - for module scoping
    required_params: list = field(default_factory=list)


def date_filter_sql(column, date_from, date_to, params, param_prefix=""):
    """A SQL fragment (possibly empty) restricting `column` to
    [date_from, date_to] - both bounds optional, empty/None means
    unbounded on that side. Mutates `params` with whichever bounds are
    actually used. Shared by ui/queries.py (the dashboard's own queries)
    and chatbot/engine.py (the global date filter applied to catalog
    queries) - lives here, not in ui/queries.py, so chatbot never has to
    depend on the ui package to reuse it."""
    clauses = []
    if date_from:
        key = f"{param_prefix}date_from"
        clauses.append(f"{column} >= %({key})s")
        params[key] = date_from
    if date_to:
        key = f"{param_prefix}date_to"
        clauses.append(f"{column} <= %({key})s")
        params[key] = date_to
    return (" AND " + " AND ".join(clauses)) if clauses else ""


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


def active_headcount_asof(conn, cutoff, table, count_col):
    """A batch is "active as of `cutoff`" if it has daily-log rows both
    on/before and on/after that date - there's no historical status log,
    so today's status column can't honestly answer "was this batch active
    on a past date" (see spec-chatbot-ui.md's dashboard methodology note).
    Shared by the dashboard's Active Headcount stat card (ui/queries.py)
    and the chatbot's tier-3 headcount tool (chatbot/tools.py) - lives
    here, not in ui/queries.py, so chatbot never has to depend on ui to
    reuse it, mirroring date_filter_sql's placement above."""
    sql = ACTIVE_HEADCOUNT_ASOF_SQL.format(table=table, count_col=count_col)
    return conn.execute(sql, {"cutoff": cutoff}).fetchone()[0]


DEATHS_IN_WINDOW_SQL = """
    SELECT COALESCE(SUM(deaths), 0) AS total
    FROM {table} WHERE date > %(start)s AND date <= %(end)s
"""


def deaths_in_window(conn, start, end, table):
    """Deaths strictly after `start` up to and including `end` - shared by
    the dashboard's Mortality Rate stat card (ui/queries.py) and the
    chatbot's tier-3 mortality-rate tool (chatbot/tools.py), same
    dependency-direction reason as active_headcount_asof above."""
    sql = DEATHS_IN_WINDOW_SQL.format(table=table)
    return conn.execute(sql, {"start": start, "end": end}).fetchone()[0]


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


def fcr_by_batch(conn, date_from=None, date_to=None):
    """[{'batch_code', 'domain', 'fcr'}, ...] across both pigs and poultry.
    When a date range is given, feed consumed and the latest weight/count
    samples are all bounded to that range - the batch's starting weight
    stays fixed (a batch-level constant, not a flow value), so FCR for a
    range that starts partway through a batch's life is an approximation,
    not an exact "gain within this window" figure. Shared by the
    dashboard's FCR chart (ui/queries.py) and the chatbot's tier-3 FCR
    ranking tool (chatbot/tools.py), same dependency-direction reason as
    active_headcount_asof above."""
    params = {}
    date_filter = date_filter_sql("date", date_from, date_to, params)
    pig_rows = conn.execute(PIG_FCR_SQL.format(date_filter=date_filter), params).fetchall()
    poultry_rows = conn.execute(POULTRY_FCR_SQL.format(date_filter=date_filter), params).fetchall()
    return (
        [{"batch_code": r[0], "domain": "piggery", "fcr": r[3]}
         for r in pig_rows if r[3] is not None] +
        [{"batch_code": r[0], "domain": "poultry", "fcr": r[3]}
         for r in poultry_rows if r[3] is not None]
    )


FEED_COST_SPLIT_SQL = """
    WITH domain_usage AS (
        SELECT date, 'piggery' AS domain, feed_type, feed_kg FROM pig_daily_log
        WHERE date >= %(period_start)s AND date < %(period_end)s
        UNION ALL
        SELECT date, 'poultry' AS domain, feed_type, feed_kg FROM poultry_daily_log
        WHERE date >= %(period_start)s AND date < %(period_end)s
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

# {date_filter} is a formatting placeholder (not a %()s SQL param) - see
# ui/queries.date_filter_sql / chatbot/engine.py's execution step, both of
# which fill it in with an optional "AND d.date >= %(date_from)s ..."
# fragment when a date range is in effect, or "" (no-op) when it isn't.
# FEED_COST_SPLIT_SQL doesn't need one: it already requires its own
# explicit period parameter, which already scopes it.
POULTRY_MORTALITY_SPIKE_SQL = """
    SELECT b.batch_code,
           ROUND(100.0 * SUM(d.deaths) / b.chicks_placed, 1) AS mortality_pct
    FROM poultry_batches b
    JOIN poultry_daily_log d ON d.batch_code = b.batch_code
    WHERE 1=1{date_filter}
    GROUP BY b.batch_code, b.chicks_placed
    ORDER BY mortality_pct DESC
    LIMIT 1
"""
POULTRY_MORTALITY_SPIKE_DATE_COLUMN = "d.date"

PIGGERY_DISEASE_OUTBREAK_SQL = """
    SELECT batch_ref, COUNT(*) AS treatment_count, SUM(cost) AS total_vet_cost
    FROM health_log
    WHERE domain = 'piggery' AND event_type = 'Treatment'{date_filter}
    GROUP BY batch_ref
    ORDER BY treatment_count DESC
    LIMIT 1
"""
PIGGERY_DISEASE_OUTBREAK_DATE_COLUMN = "date"

CROP_DEBTOR_SQL = """
    SELECT product, buyer, total_amount, batch_ref
    FROM revenue
    WHERE domain = 'crops' AND payment_status = 'Owing'{date_filter}
    ORDER BY date
"""
CROP_DEBTOR_DATE_COLUMN = "date"

CATALOG = [
    CatalogQuery(
        query_id="feed_cost_split",
        phrases=[
            "how does feed cost split between pigs and chickens",
            "feed cost split by domain",
            "how much are we spending on feed for pigs versus chickens",
            "compare feed cost between piggery and poultry",
        ],
        sql=FEED_COST_SPLIT_SQL,
        domains=["piggery", "poultry"],
        required_params=["period"],
    ),
    CatalogQuery(
        query_id="poultry_mortality_spike",
        phrases=[
            "which poultry batch has the worst mortality",
            "is there a mortality problem in the poultry house",
            "which broiler batch is dying the most",
            "poultry mortality rate by batch",
            "is something wrong with a batch",
        ],
        sql=POULTRY_MORTALITY_SPIKE_SQL,
        domains=["poultry"],
    ),
    CatalogQuery(
        query_id="piggery_disease_outbreak",
        phrases=[
            "is there a disease outbreak in the piggery",
            "which pig batch has health problems",
            "any pigs being treated for illness",
            "piggery disease treatment costs",
            "is something wrong with a batch",
        ],
        sql=PIGGERY_DISEASE_OUTBREAK_SQL,
        domains=["piggery"],
    ),
    CatalogQuery(
        query_id="crop_debtor",
        # "who owes us money for crops" listed first (not "which crop sales
        # are unpaid") - tier-2's extraction prompt only shows phrases[0] as
        # its example (see fallback.py's _catalog_summary), and a real,
        # reproducible confusion was found where "are we owing anyone" /
        # "do we owe X" got matched to this entry with the direction
        # inverted (this query tracks money owed TO the farm, not money the
        # farm owes others - a different, untracked concept). Leading with
        # the most direction-explicit phrase gives tier-2 the clearest
        # possible signal.
        phrases=[
            "who owes us money for crops",
            "which crop sales are unpaid",
            "any outstanding crop payments",
            "unpaid grain sales",
        ],
        sql=CROP_DEBTOR_SQL,
        domains=["crops"],
    ),
]
