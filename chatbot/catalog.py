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
    required_params: list = field(default_factory=list)


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
        required_params=["period"],
    ),
]
