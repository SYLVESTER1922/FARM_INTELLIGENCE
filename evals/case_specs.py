"""
Gold spec for every answerable dev case: the registry metric and typed Scope the
question SHOULD resolve to. Two uses:
  - now: tests/test_registry_oracle_agreement.py checks the registry returns what the
    independent oracle expects for each case (registry and oracle agree);
  - step 5: the routing eval scores the LLM's question-to-spec mapping against these.

Cases that are refusals or clarifications have no spec (None). DRAFT, like the cases:
reviewed with them.
"""

from evals.cases_dev import APR, AUG, JAN, JUN, MAR, MAY, OCT, Q2, SEP, YEAR_2026, YTD
from registry import Scope

P, C_, CR = ("piggery",), ("poultry",), ("crops",)


def S(metric, **kw):
    return metric, Scope(**kw)


def _rng(r):
    return {"start": r[0], "end": r[1]}


SPECS = {
    # headcount
    "hc01": S("active_headcount", domains=P), "hc02": S("active_headcount", domains=C_),
    "hc03": S("active_headcount"), "hc04": S("active_headcount"), "hc05": S("active_headcount", domains=C_),
    "hc06": S("active_headcount", domains=P), "hc07": S("active_headcount"),
    "hc08": S("sow_count"), "hc09": S("sow_count"), "hc10": S("sow_count"),
    "bc01": S("batch_count", domains=C_), "bc02": S("batch_count", domains=P), "bc03": S("batch_count"),
    "bc04": S("batch_count"), "bc05": S("batch_count", domains=C_), "bc06": S("batch_count", domains=P),
    "mo01": S("mortality", domains=P, **_rng(APR)), "mo02": S("mortality", domains=C_, **_rng(JAN)),
    "mo03": S("mortality", domains=C_), "mo04": S("mortality", domains=P), "mo05": S("mortality", **_rng(MAY)),
    "mo06": S("mortality"), "mo07": S("mortality", **_rng(YEAR_2026)), "mo08": S("mortality"),
    "mo09": S("mortality", batch_code="BRO-P02"), "mo10": S("mortality", domains=C_, dimension="batch"),
    # feed consumed
    "fc01": S("feed_consumed_cost", domains=P, **_rng(AUG)), "fc02": S("feed_consumed_cost", **_rng(AUG)),
    "fc03": S("feed_consumed_cost", **_rng(MAR)), "fc04": S("feed_consumed_cost", **_rng(SEP)),
    "fc05": S("feed_consumed_cost", **_rng(OCT)), "fc06": S("feed_consumed_cost", domains=C_, **_rng(APR)),
    "fc07": S("feed_consumed_cost", domains=P, **_rng(MAY)), "fc08": S("feed_consumed_cost"),
    "fc09": S("feed_consumed_cost", aggregation="avg_per_week"),
    "fc10": S("feed_consumed_cost", domains=C_, **_rng(SEP)), "fc11": S("feed_consumed_cost", **_rng(AUG)),
    "fc12": S("feed_consumed_cost", **_rng(Q2)), "fc13": S("feed_consumed_cost", **_rng(JAN)),
    "fc14": S("feed_consumed_cost", **_rng(YTD)),
    # feed purchases
    "fp01": S("feed_purchases", **_rng(AUG)), "fp02": S("feed_purchases"), "fp03": S("feed_purchases", domains=P),
    "fp04": S("feed_purchases", domains=C_, **_rng(YEAR_2026)), "fp05": S("feed_purchases", **_rng(MAR)),
    "fp06": S("feed_purchases", **_rng(SEP)),
    # expenses
    "ex01": S("expenses"), "ex02": S("expenses", domains=P), "ex03": S("expenses", domains=C_),
    "ex04": S("expenses", domains=CR), "ex05": S("expenses", domains=P + C_, dimension="domain"),
    "ex06": S("expenses", dimension="category"), "ex07": S("expenses", category="Electricity"),
    "ex08": S("expenses", dimension="category"), "ex09": S("expenses", category="Vet & Meds"),
    "ex10": S("expenses", **_rng(AUG)), "ex11": S("expenses", category="Fertiliser"),
    "ex12": S("expenses", domains=C_, category="Day-old chicks"), "ex13": S("expenses", category="Seed"),
    "ex14": S("expenses", dimension="domain"), "ex15": S("expenses", **_rng(SEP)),
    "ex16": S("expenses", category="Chemicals"), "ex17": S("expenses", category="Fuel"),
    # revenue / profit
    "rv01": S("revenue"), "rv02": S("revenue", domains=P), "rv03": S("revenue", domains=CR),
    "rv04": S("revenue", dimension="buyer"), "rv05": S("revenue", dimension="product"),
    "rv06": S("revenue", **_rng(AUG)), "rv07": S("revenue", domains=C_), "rv08": S("revenue", **_rng(SEP)),
    "pf01": S("profit"), "pf02": S("profit", domains=P), "pf03": S("profit", domains=C_),
    "pf04": S("profit", domains=CR), "pf05": S("profit", **_rng(AUG)), "pf06": S("profit"),
    # feed cost per animal, receivables, labour
    "ca01": S("feed_cost_per_animal", domains=P), "ca02": S("feed_cost_per_animal", domains=C_),
    "ca03": S("feed_cost_per_animal"),
    "rc01": S("receivables"), "rc02": S("receivables"), "rc03": S("receivables"), "rc04": S("receivables"),
    "rc05": S("receivables"), "rc06": S("receivables"), "rc07": S("receivables", domains=P),
    "lb01": S("labour"), "lb02": S("labour", **_rng(AUG)), "lb03": S("labour", domains=P),
    "lb04": S("labour", domains=C_, **_rng(JUN)), "lb05": S("labour"), "lb06": S("labour", **_rng(SEP)),
    # performance
    "fcr1": S("fcr"), "fcr2": S("fcr"), "fcr3": S("fcr", batch_code="PIG-B04"),
    "wt01": S("weight", batch_code="PIG-B04"), "wt02": S("weight", domains=P), "wt03": S("weight", domains=C_),
    "wt04": S("weight", batch_code="BRO-P03"),
    "hy01": S("harvest_yield"), "hy02": S("harvest_yield"), "hy03": S("harvest_yield"), "hy04": S("harvest_yield"),
    "cr01": S("crop_plantings"), "cr02": S("crop_plantings"), "cr03": S("crop_plantings"),
    "br01": S("breeding"), "br02": S("breeding"), "br03": S("breeding"), "br04": S("breeding"),
    "br05": S("breeding"),
    # operations
    "fs01": S("feed_stock"), "fs02": S("feed_stock", domains=P), "fs03": S("feed_stock", domains=C_),
    "mr01": S("market_readiness"), "mr02": S("market_readiness", domains=P),
    "mr03": S("market_readiness", domains=C_), "mr04": S("market_readiness"),
    "he01": S("health_events", domains=P), "he02": S("health_events"), "he03": S("health_events"),
    "he04": S("health_events"), "he05": S("health_events", domains=C_), "he06": S("health_events", domains=P),
    "wx01": S("weather"), "wx02": S("weather", **_rng(JAN)),
    # dashboard-filter rules: the scope the resolver should produce
    "sc01": S("feed_consumed_cost", **_rng(AUG)), "sc02": S("feed_consumed_cost", **_rng(MAR)),
    "sc03": S("feed_consumed_cost"), "sc04": S("active_headcount", domains=P),
    "sc05": S("feed_consumed_cost"), "sc06": S("expenses"), "sc07": S("feed_consumed_cost"),
    # noisy
    "nz01": S("active_headcount", domains=P), "nz02": S("feed_consumed_cost", domains=P, **_rng(AUG)),
    "nz03": S("active_headcount", domains=C_), "nz04": S("expenses"), "nz05": S("expenses", category="Fertiliser"),
    "nz06": S("active_headcount", domains=P), "nz07": S("receivables"),
    "nz08": S("feed_consumed_cost", domains=P, **_rng(AUG)),
}
