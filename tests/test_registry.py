"""Registry unit tests: the six agreed definitions, the no-record rule, exact rounding, and the integrity of
every metric entry. Runs against the real generated workbook (fixture `farm_db`)."""

import datetime as dt
from collections import Counter

import pytest

from registry import REGISTRY, Scope, compute
from registry.core import rnd

D = dt.date
AUG = (D(2026, 8, 1), D(2026, 8, 31))
SEP = (D(2026, 9, 1), D(2026, 9, 30))
OCT = (D(2026, 10, 1), D(2026, 10, 31))


def run(db, metric, **kw):
    return compute(metric, db, Scope(**kw))


# ------------------------------------------------------------------ integrity of the registry itself
def test_every_metric_entry_is_complete():
    assert len(REGISTRY) == 21
    for m in REGISTRY.values():
        assert m.definition and m.sources and m.unit and m.answers and m.does_not_answer, m.id
        assert callable(m.compute), m.id
        assert m.dashboard or m.parity_exempt, f"{m.id}: needs a dashboard parity hook or an exemption reason"
        assert m.period in ("range", "snapshot", "none"), m.id
        if m.group in ("money", "headcount"):
            assert m.zero_tolerance, f"{m.id}: money and headcount metrics are zero-tolerance"


def test_every_metric_has_enough_eval_cases():
    """Plan section 4: each entry carries at least N eval cases (3 for zero-tolerance, 2 otherwise)."""
    from evals.cases_dev import CASES
    by_oracle = Counter(c.oracle[0] for c in CASES)
    for m in REGISTRY.values():
        n = sum(by_oracle[o] for o in m.eval_oracles)
        need = 3 if m.zero_tolerance else 2
        assert n >= need, f"{m.id}: {n} eval cases, needs {need} (oracles {m.eval_oracles})"


# ------------------------------------------------------------------ decision 1: mortality
def test_mortality_period_denominator_is_opening_plus_additions(farm_db):
    r = run(farm_db, "mortality", domains=("piggery",), start=D(2026, 4, 1), end=D(2026, 4, 30))
    f = r.figures
    assert (f["deaths"], f["opening"], f["additions"], f["at_risk"], f["rate_pct"]) == (3, 26, 0, 26, 11.54)
    assert "26 at the start of the period + 0 added = 26" in r.notes[0]       # the denominator is stated


def test_mortality_all_time_is_deaths_over_everything_placed(farm_db):
    f = run(farm_db, "mortality").figures
    assert (f["deaths"], f["additions"], f["at_risk"], f["rate_pct"]) == (51, 2102, 2102, 2.43)


def test_mortality_for_a_batch_is_deaths_over_placed(farm_db):
    r = run(farm_db, "mortality", batch_code="BRO-P02")
    assert (r.figures["deaths"], r.figures["at_risk"], r.figures["rate_pct"]) == (42, 520, 8.08)
    assert "placed (520)" in r.notes[0]


def test_mortality_by_batch_ranks_by_rate(farm_db):
    r = run(farm_db, "mortality", domains=("poultry",), dimension="batch")
    assert r.figures["worst_batch"] == "BRO-P02"
    assert [x["rate_pct"] for x in r.rows] == sorted((x["rate_pct"] for x in r.rows), reverse=True)


def test_mortality_unknown_batch_is_a_named_refusal(farm_db):
    r = run(farm_db, "mortality", batch_code="NOPE-1")
    assert r.status == "not_available" and "NOPE-1" in r.message


# ------------------------------------------------------------------ decision 2: feed
def test_feed_purchases_for_pigs_is_13308_50(farm_db):                     # eval case fp03
    assert run(farm_db, "feed_purchases", domains=("piggery",)).figures["total"] == 13308.5


def test_feed_consumed_and_purchased_are_different_numbers(farm_db):
    consumed = run(farm_db, "feed_consumed_cost").figures["total_cost"]
    purchased = run(farm_db, "feed_purchases").figures["total"]
    assert (consumed, purchased) == (14781.92, 19281.0)


def test_average_weekly_feed_cost_is_total_over_days_covered_times_seven(farm_db):
    r = run(farm_db, "feed_consumed_cost", aggregation="avg_per_week")
    f = r.figures
    assert f["days_covered"] == 341 and f["total_cost"] == 14781.92
    assert f["avg_weekly_cost"] == rnd(14781.92 / 341 * 7)
    assert "341 days" in r.notes[0]                                         # the days used are stated


def test_average_weekly_uses_only_the_days_inside_the_records(farm_db):
    r = run(farm_db, "feed_consumed_cost", aggregation="avg_per_week", start=SEP[0], end=SEP[1])
    assert r.figures["days_covered"] == 15 and r.coverage.partial          # September has data to the 15th


# ------------------------------------------------------------------ decision 3: feed cost per animal, FCR
def test_feed_cost_per_animal_states_its_denominator(farm_db):
    r = run(farm_db, "feed_cost_per_animal", domains=("piggery",))
    assert r.figures["cost_per_animal"] == 316.06
    assert "average headcount" in r.notes[0]
    assert r.rows[0]["days_logged"] > 0 and r.rows[0]["avg_headcount"] > 0


def test_fcr_is_feed_over_weight_gained_between_first_and_latest_sample(farm_db):
    r = run(farm_db, "fcr", batch_code="PIG-B04")
    row = r.rows[0]
    assert row["fcr"] == 2.26 and row["samples"] >= 2
    assert row["fcr"] == rnd(row["feed_kg"] / row["gain_kg"])


def test_fcr_without_weight_samples_is_a_named_refusal(mutable_farm_db):
    mutable_farm_db.execute("DELETE FROM pig_weights WHERE batch_code = 'PIG-B04'")
    mutable_farm_db.execute("UPDATE pig_batches SET start_avg_kg = NULL WHERE batch_code = 'PIG-B04'")
    r = run(mutable_farm_db, "fcr", batch_code="PIG-B04")
    assert r.status == "not_available" and "two weight samples" in r.message
    assert r.rows[0]["fcr"] is None and r.rows[0]["reason"]


# ------------------------------------------------------------------ decision 4: no record is not zero
def test_period_after_last_record_says_no_record_with_the_latest_date(farm_db):
    r = run(farm_db, "revenue", start=SEP[0], end=SEP[1])
    assert r.status == "no_record"
    assert r.message == "No revenue recorded for that period; latest record is 2026-08-18."
    assert not r.figures                                                     # no fabricated 0


@pytest.mark.parametrize("metric,expected", [
    ("expenses", "No expenses recorded for that period; latest record is 2026-09-14."),
    ("feed_consumed_cost", "No feed consumption recorded for that period; latest record is 2026-09-15."),
    ("health_events", "No health events recorded for that period; latest record is 2026-08-11."),
])
def test_no_record_message_names_the_metric_and_latest_record(farm_db, metric, expected):
    assert run(farm_db, metric, start=D(2026, 10, 1), end=D(2026, 10, 31)).message == expected


def test_zero_inside_coverage_is_a_real_zero(farm_db):
    # Poultry fed nothing in June 2026 (between batches) - inside the log's coverage, so 0 is true.
    r = run(farm_db, "feed_consumed_cost", domains=("poultry",), start=D(2026, 6, 1), end=D(2026, 6, 30))
    assert r.status == "ok" and r.figures["total_cost"] == 0.0 and not r.coverage.partial


def test_period_before_the_first_record_says_earliest(farm_db):
    r = run(farm_db, "revenue", start=D(2020, 1, 1), end=D(2020, 12, 31))
    assert r.status == "no_record" and "earliest record is 2025-11-21" in r.message


def test_partly_covered_period_is_answered_and_flagged(farm_db):
    r = run(farm_db, "feed_consumed_cost", start=SEP[0], end=SEP[1])
    assert r.status == "ok" and r.coverage.partial and r.coverage.days_covered == 15
    assert r.figures["total_cost"] == 833.21


def test_profit_needs_both_sides_to_have_records(farm_db):
    r = run(farm_db, "profit", start=SEP[0], end=SEP[1])
    assert r.status == "no_record" and "revenue" in r.message and "Profit needs both" in r.message


# ------------------------------------------------------------------ decision 5: shared costs
def test_expense_rows_by_domain_include_shared_and_sum_to_the_total(farm_db):
    r = run(farm_db, "expenses", dimension="domain")
    labels = {x["label"]: x["total"] for x in r.rows}
    assert labels["Shared (not allocated)"] == 1528.74
    assert round(sum(x["total"] for x in r.rows), 2) == r.figures["total"] == 30380.06


def test_expense_rows_by_category_also_sum_to_the_total(farm_db):
    r = run(farm_db, "expenses", dimension="category")
    assert round(sum(x["total"] for x in r.rows), 2) == r.figures["total"]


def test_unassigned_labour_is_treated_as_shared(mutable_farm_db):
    # labour_log.domain is nullable (expenses.domain is NOT NULL): an empty domain means unallocated too.
    mutable_farm_db.execute("UPDATE labour_log SET domain = NULL WHERE domain = 'shared'")
    r = run(mutable_farm_db, "labour")
    assert {x["label"]: x["labour_cost"] for x in r.rows}["Shared (not allocated)"] == 783900.0
    assert round(sum(x["labour_cost"] for x in r.rows), 2) == r.figures["labour_cost"]


def test_single_domain_profit_says_shared_costs_are_excluded(farm_db):
    assert "not part of a single domain's profit" in run(farm_db, "profit", domains=("piggery",)).notes[0]
    assert "includes 'Shared (not allocated)'" in run(farm_db, "profit").notes[0]


# ------------------------------------------------------------------ decision 6: batches
def test_batch_count_gives_total_and_active(farm_db):
    r = run(farm_db, "batch_count", domains=("poultry",))
    assert (r.figures["total"], r.figures["active"], r.figures["sold"]) == (4, 1, 3)


def test_only_active_batches_can_be_ready_or_overdue(farm_db):
    r = run(farm_db, "market_readiness")
    codes = {x["batch_code"] for x in r.rows}
    assert codes == {"PIG-B04", "BRO-P04"}                                  # eval cases mr01, mr02, mr04
    assert r.figures["overdue"] == 0 and r.figures["due_soon"] == 2


def test_a_closed_batch_is_not_active(mutable_farm_db):
    mutable_farm_db.execute("UPDATE pig_batches SET status = 'Closed' WHERE batch_code = 'PIG-B04'")
    assert run(mutable_farm_db, "batch_count", domains=("piggery",)).figures["active"] == 0
    assert "PIG-B04" not in {x["batch_code"] for x in run(mutable_farm_db, "market_readiness").rows}


# ------------------------------------------------------------------ receivables
def test_receivables_span_every_domain_not_just_crops(mutable_farm_db):
    mutable_farm_db.execute("UPDATE revenue SET payment_status = 'Owing' WHERE buyer = 'Colcom Abattoir' AND date = '2026-08-17'")
    r = run(mutable_farm_db, "receivables")
    assert {x["domain"] for x in r.rows} == {"crops", "piggery"}            # the old catalog filtered domain='crops'


def test_partly_paid_sales_are_flagged_not_counted(mutable_farm_db):
    mutable_farm_db.execute("UPDATE revenue SET payment_status = 'Partial' WHERE buyer = 'Colcom Abattoir' AND date = '2026-02-18'")
    r = run(mutable_farm_db, "receivables")
    assert r.figures["total"] == 8681.12 and "partly-paid" in r.notes[0]


def test_nobody_owing_in_a_domain_is_an_ok_empty_answer(farm_db):
    r = run(farm_db, "receivables", domains=("poultry",))
    assert r.status == "ok" and r.rows == [] and r.figures["total"] == 0.0


# ------------------------------------------------------------------ exact rounding
def test_money_rounds_half_up_on_the_exact_decimal():
    assert rnd(4781.455) == 4781.46                      # a binary float rounds this DOWN to 4781.45
    assert rnd(2.225, 2) == 2.23 and rnd(0.125, 2) == 0.13
    assert rnd(None) == 0.0


def test_finance_page_total_keeps_its_cent(farm_db):
    rows = {r["domain"]: r["feed_cost"] for r in run(farm_db, "feed_consumed_cost").rows}
    assert rows["poultry"] == 4781.46


# ------------------------------------------------------------------ data anomaly retained as a sync-gate fixture
def test_shared_labour_anomaly_is_retained_as_a_sync_gate_fixture(farm_db):
    """'Shared' labour costs ~450 an hour against ~8-12 for every other domain: a mixed unit/currency
    anomaly the sync gate (plan section 9) must catch. It is deliberately left in the data."""
    r = run(farm_db, "labour")
    rate = {x["domain"]: x["labour_cost"] / x["hours"] for x in r.rows}
    assert rate["shared"] > 10 * max(v for d, v in rate.items() if d != "shared")
    assert next(x for x in r.rows if x["domain"] == "shared")["labour_cost"] == 783900.0


# ------------------------------------------------------------------ sow count
def test_sow_count_gives_the_status_split(farm_db):
    r = run(farm_db, "sow_count")
    assert r.figures["total"] == 3 and r.figures["by_status"] == {"Lactating": 1, "Open": 1, "Pregnant": 1}
    assert "current status" in r.notes[0]


def test_culled_sows_are_not_on_the_farm(mutable_farm_db):
    mutable_farm_db.execute("UPDATE sow_register SET status = 'Culled' WHERE sow_tag = 'SOW-01'")
    r = run(mutable_farm_db, "sow_count")
    assert r.figures["total"] == 2 and r.figures["culled"] == 1 and "Open" not in r.figures["by_status"]


def test_sow_count_with_an_empty_register_is_a_named_refusal(mutable_farm_db):
    mutable_farm_db.execute("DELETE FROM breeding_farrowing")
    mutable_farm_db.execute("DELETE FROM sow_register")
    r = run(mutable_farm_db, "sow_count")
    assert r.status == "not_available" and "sow register" in r.message
