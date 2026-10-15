"""Parity: every dashboard figure that has a registry metric shows exactly what the registry computes, so the
chat and the dashboard cannot disagree (plan decision D1, section 4). One test per dashboard hook that a
registry entry declares; the last tests fail if a declared hook has no parity test, or a parity test is orphaned."""

import datetime as dt
import sys

import pytest

from registry import REGISTRY, Scope, compute
from ui import queries as q

D = dt.date
AUG = (D(2026, 8, 1), D(2026, 8, 31))
JAN = (D(2026, 1, 1), D(2026, 1, 31))
FILTERS = [pytest.param(None, None, id="all-time"), pytest.param(*AUG, id="aug-2026-filter")]


def reg(db, metric, **kw):
    r = compute(metric, db, Scope(**kw))
    assert r.ok, (metric, r.message)
    return r


# ----------------------------------------------------------------------------------- feed (Finance and Feeding pages)
@pytest.mark.parametrize("df,dt_", FILTERS)
def test_parity_fetch_feed_cost_by_domain(farm_db, df, dt_):
    page = {r["domain"]: (r["total_kg"], r["feed_cost"]) for r in q.fetch_feed_cost_by_domain(farm_db, df, dt_)}
    r = reg(farm_db, "feed_consumed_cost", start=df, end=dt_)
    assert page == {x["domain"]: (x["feed_kg"], x["feed_cost"]) for x in r.rows}


@pytest.mark.parametrize("df,dt_", FILTERS)
def test_parity_fetch_feed_cost_by_month(farm_db, df, dt_):
    page = q.fetch_feed_cost_by_month(farm_db, df, dt_)
    monthly = reg(farm_db, "feed_consumed_cost", start=df, end=dt_, grain="month")
    assert page == {d: [(x["month_start"], x["feed_cost"]) for x in monthly.rows if x["domain"] == d]
                    for d in ("piggery", "poultry")}


@pytest.mark.parametrize("df,dt_", FILTERS)
def test_feeding_page_and_finance_page_cannot_disagree(farm_db, df, dt_):
    """The live defect: the two pages showed different August feed costs (poultry ~35% apart)."""
    finance = {r["domain"]: r["feed_cost"] for r in q.fetch_feed_cost_by_domain(farm_db, df, dt_)}
    feeding = q.fetch_feed_cost_by_month(farm_db, df, dt_)
    for domain, months in feeding.items():
        # each month is rounded to the cent; the Finance total is exact, so allow half a cent per month
        assert abs(sum(c for _, c in months) - finance[domain]) <= 0.005 * max(len(months), 1) + 1e-9, domain


def test_august_poultry_feed_cost_is_one_number(farm_db):
    feeding = dict(q.fetch_feed_cost_by_month(farm_db, *AUG)["poultry"])[D(2026, 8, 1)]
    finance = next(r["feed_cost"] for r in q.fetch_feed_cost_by_domain(farm_db, *AUG) if r["domain"] == "poultry")
    assert feeding == finance == 642.7                                       # was 869.66 on the Feeding page


# ----------------------------------------------------------------------------------- expenses and revenue
def test_parity_fetch_expense_breakdown(farm_db):
    page = q.fetch_expense_breakdown(farm_db)
    r = reg(farm_db, "expenses", dimension="category")
    assert page == [{"category": x["key"], "total": x["total"]} for x in r.rows]
    assert round(sum(x["total"] for x in page), 2) == r.figures["total"]


@pytest.mark.parametrize("df,dt_", FILTERS)
def test_parity_fetch_expenses_vs_revenue(farm_db, df, dt_):
    page = q.fetch_expenses_vs_revenue(farm_db, df, dt_)
    assert abs(sum(v for _, v in page["expenses"]) - reg(farm_db, "expenses", start=df, end=dt_).figures["total"]) < 0.005
    assert abs(sum(v for _, v in page["revenue"]) - reg(farm_db, "revenue", start=df, end=dt_).figures["total"]) < 0.005


# ----------------------------------------------------------------------------------- receivables
def test_parity_fetch_debtors(farm_db):
    page = q.fetch_debtors(farm_db)
    r = reg(farm_db, "receivables")
    assert [(d["buyer"], d["total_amount"]) for d in page] == [(x["buyer"], x["total_amount"]) for x in r.rows]


def test_debtors_page_lists_every_domain(mutable_farm_db):
    mutable_farm_db.execute("UPDATE revenue SET payment_status='Owing' WHERE buyer='Colcom Abattoir' AND date='2026-08-17'")
    page = q.fetch_debtors(mutable_farm_db)
    assert {d["domain"] for d in page} == {"crops", "piggery"}
    assert round(sum(d["total_amount"] for d in page), 2) == reg(mutable_farm_db, "receivables").figures["total"]


# ----------------------------------------------------------------------------------- stat cards
def _card(cards, label_start):
    return next(c for c in cards if c["label"].startswith(label_start))


def test_parity_fetch_dashboard_stats_active_headcount(farm_db):
    r = reg(farm_db, "active_headcount")
    assert _card(q.fetch_dashboard_stats(farm_db), "Active Headcount")["value"] == f"{r.figures['total']:,}"


def test_active_headcount_card_follows_the_filter_end_date_like_the_registry(farm_db):
    page = _card(q.fetch_dashboard_stats(farm_db, D(2026, 3, 1), D(2026, 3, 31)), "Active Headcount")["value"]
    assert page == f"{reg(farm_db, 'active_headcount', as_of=D(2026, 3, 31)).figures['total']:,}"


@pytest.mark.parametrize("window", [JAN, (D(2026, 4, 1), D(2026, 4, 30)), (D(2026, 5, 1), D(2026, 5, 31))])
def test_parity_fetch_dashboard_stats_mortality(farm_db, window):
    card = _card(q.fetch_dashboard_stats(farm_db, *window), "Mortality Rate")
    r = reg(farm_db, "mortality", start=window[0], end=window[1])
    assert card["value"] == f"{r.figures['rate_pct']}%"


def test_mortality_card_counts_the_first_day_of_a_selected_range(mutable_farm_db):
    # a death logged on the range's first day used to be left out of the card
    first = D(2026, 4, 1)
    mutable_farm_db.execute("UPDATE pig_daily_log SET deaths = deaths + 5 WHERE batch_code='PIG-B02' AND date = %s", (first,))
    card = _card(q.fetch_dashboard_stats(mutable_farm_db, first, D(2026, 4, 30)), "Mortality Rate")
    assert card["value"] == f"{reg(mutable_farm_db, 'mortality', start=first, end=D(2026, 4, 30)).figures['rate_pct']}%"


@pytest.mark.parametrize("domain", ["piggery", "poultry"])
def test_parity_fetch_domain_summary(farm_db, domain):
    page = q.fetch_domain_summary(farm_db, domain)
    assert page["headcount"] == next(x["headcount"] for x in reg(farm_db, "active_headcount").rows if x["domain"] == domain)
    assert page["total_feed_cost"] == reg(farm_db, "feed_consumed_cost", domains=(domain,)).figures["total_cost"]
    assert page["total_deaths"] == reg(farm_db, "mortality", domains=(domain,)).figures["deaths"]
    health = reg(farm_db, "health_events", domains=(domain,))
    assert (page["total_health_events"], page["total_health_cost"]) == (health.figures["total_events"], health.figures["total_cost"])


def test_domain_lookup_feed_total_matches_the_finance_page_to_the_cent(farm_db):
    finance = {r["domain"]: r["feed_cost"] for r in q.fetch_feed_cost_by_domain(farm_db)}
    for domain in ("piggery", "poultry"):
        assert q.fetch_domain_summary(farm_db, domain)["total_feed_cost"] == finance[domain]


# ----------------------------------------------------------------------------------- mortality, findings, FCR
@pytest.mark.parametrize("df,dt_", FILTERS)
def test_parity_fetch_mortality_by_month(farm_db, df, dt_):
    page = q.fetch_mortality_by_month(farm_db, df, dt_)
    for d in ("piggery", "poultry"):
        total = reg(farm_db, "mortality", domains=(d,), start=df, end=dt_).figures["deaths"]
        assert sum(n for _, n in page[d]) == total


def test_parity_fetch_findings(farm_db):
    f = q.fetch_findings(farm_db)
    worst = reg(farm_db, "mortality", domains=("poultry",), dimension="batch")
    assert f["poultry_mortality_spike"]["batch_code"] == worst.figures["worst_batch"]
    assert float(f["poultry_mortality_spike"]["mortality_pct"]) == pytest.approx(worst.figures["worst_rate_pct"], abs=0.05)
    debtor = reg(farm_db, "receivables", domains=("crops",)).rows[0]
    assert (f["crop_debtor"]["buyer"], float(f["crop_debtor"]["total_amount"])) == (debtor["buyer"], debtor["total_amount"])


@pytest.mark.parametrize("df,dt_", FILTERS)
def test_parity_fetch_fcr_by_batch(farm_db, df, dt_):
    page = q.fetch_fcr_by_batch(farm_db, df, dt_)
    r = compute("fcr", farm_db, Scope(start=df, end=dt_))
    assert page == [{"batch_code": x["batch_code"], "domain": x["domain"], "fcr": x["fcr"]} for x in r.rows if x["fcr"] is not None]


# ----------------------------------------------------------------------------------- crops, health, breeding, batches
def test_parity_fetch_batch_summary(farm_db):
    for code, domain in (("PIG-B04", "piggery"), ("BRO-P04", "poultry")):
        page = q.fetch_batch_summary(farm_db, code)
        row = next(x for x in reg(farm_db, "weight", batch_code=code).rows)
        assert (float(page["avg_weight"]), page["weight_unit"]) == (row["avg_weight"], row["unit"])


def test_parity_fetch_crops_summary(farm_db):
    page = q.fetch_crops_summary(farm_db)
    assert page["total_area_ha"] == reg(farm_db, "crop_plantings").figures["total_area_ha"]
    assert page["total_harvested_kg"] == reg(farm_db, "harvest_yield").figures["total_harvested_kg"]


@pytest.mark.parametrize("df,dt_", FILTERS)
def test_parity_fetch_health_summary(farm_db, df, dt_):
    page = q.fetch_health_summary(farm_db, df, dt_)
    r = compute("health_events", farm_db, Scope(start=df, end=dt_))
    rows = r.rows if r.ok else []
    assert page == [{k: x[k] for k in ("domain", "event_type", "event_count", "total_cost")} for x in rows]


def test_parity_fetch_breeding_summary(farm_db):
    page = q.fetch_breeding_summary(farm_db)
    f = reg(farm_db, "breeding").figures
    assert (page["total_litters"], page["total_born_alive"], page["total_weaned"]) == (f["litters"], f["born_alive"], f["weaned"])


# ----------------------------------------------------------------------------------- the registry's own promise
def _declared_hooks():
    return {h for m in REGISTRY.values() for h in m.dashboard}


def test_every_declared_dashboard_hook_has_a_parity_test():
    module = sys.modules[__name__]
    missing = [h for h in _declared_hooks() if not any(n.startswith(f"test_parity_{h}") for n in dir(module))]
    assert not missing, f"declared in the registry but no parity test: {missing}"


def test_every_declared_dashboard_hook_exists_in_the_dashboard():
    assert all(callable(getattr(q, h, None)) for h in _declared_hooks())


def test_no_parity_test_is_orphaned():
    module = sys.modules[__name__]
    tested = {n[len("test_parity_"):] for n in dir(module) if n.startswith("test_parity_")}
    assert all(any(t == h or t.startswith(h + "_") for h in _declared_hooks()) for t in tested), tested


def test_the_dashboard_no_longer_imports_the_old_engines_definitions():
    import ast
    tree = ast.parse(open(q.__file__).read())
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "chatbot.catalog"
                for a in n.names}
    old = {"active_headcount_asof", "deaths_in_window", "fcr_by_batch", "farrowing_records", "health_by_event_type",
           "feed_cost_by_domain"}
    assert not (imported & old), f"ui/queries.py still imports the old definitions: {imported & old}"
