"""Templated answers (plan decision D5). The completeness test is the important one: every field of a structured result must
be read by its template, so a figure or a row can never be silently left out of an answer. Runs against the real generated
workbook (fixture `farm_db`) through the resolver and the registry, exactly the path a question will take."""

import datetime as dt
import pathlib
import re

import pytest

from evals.case_specs import REFUSAL_SPECS, SPECS
from evals.cases_dev import CASES
from evals.oracle import EVAL_TODAY, Oracle
from evals.score import Observed, score
from registry import REGISTRY, Scope, compute
from registry.core import WEEKDAYS, Coverage, Result
from render import (ALL_TIME_HINT, GREETING, RenderContext, render, render_refusal, render_traced)
from render import format as fmt
from render.templates import TEMPLATES, TITLES
from render.tracking import Touch
from resolver import all_time_scope, resolve

D = dt.date
BY_ID = {c.id: c for c in CASES}
SYNC_DATE = D(2026, 9, 15)
CTX = RenderContext(currency="USD", data_through=SYNC_DATE)


def answer(db, case_id, ctx=CTX):
    """The path a question takes: resolver for the period, the gold spec for the metric-specific parts, the registry for
    the figures, the template for the words. Returns (text, touch, result, resolution)."""
    case = BY_ID[case_id]
    metric_id, gold = SPECS[case_id]
    res = resolve(case.question, REGISTRY[metric_id], today=case.today or EVAL_TODAY, dashboard_filter=case.filter,
                  week_start=WEEKDAYS.index(case.week_start) if case.week_start else 0)
    assert res.ok, res.unresolved
    result = compute(metric_id, db, gold.with_(period_source=res.period_source))
    allt = compute(metric_id, db, all_time_scope(gold)) if res.offer_all_time_hint else None
    ctx = RenderContext(currency=ctx.currency, data_through=ctx.data_through, all_time_result=allt)
    text, touch = render_traced(res, result, ctx)
    return text, touch, result, res


# --------------------------------------------------------------------------------- completeness (the D5 test)
@pytest.mark.parametrize("case_id", sorted(SPECS))
def test_every_result_field_and_row_is_rendered(farm_db, case_id):
    text, touch, result, _ = answer(farm_db, case_id)
    assert touch.unrendered(result) == [], f"{case_id}: result fields no template read: {touch.unrendered(result)}"


@pytest.mark.parametrize("question,metric", [
    ("feed cost by month", "feed_consumed_cost"), ("monthly expenses", "expenses"), ("monthly revenue", "revenue"),
    ("deaths by month", "mortality"), ("weather in January 2026", "weather"), ("expenses by category", "expenses"),
])
def test_the_grain_and_dimension_variants_are_also_complete(farm_db, question, metric):
    res = resolve(question, REGISTRY[metric], today=EVAL_TODAY)
    scope = res.scope.with_(dimension="category") if "category" in question else res.scope
    result = compute(metric, farm_db, scope)
    text, touch = render_traced(res, result, CTX)
    assert touch.unrendered(result) == [], touch.unrendered(result)


def test_the_completeness_check_really_fails_when_a_field_is_dropped():
    """A template that ignores a field must be caught: add a field no template knows about and see it reported."""
    result = Result("profit", "ok", Scope(), "currency", {"revenue": 1.0, "expenses": 2.0, "profit": -1.0, "surprise": 7})
    _, touch = render_traced(resolve("profit", REGISTRY["profit"], today=EVAL_TODAY), result, CTX)
    assert touch.unrendered(result) == [("figures", "surprise")]


def test_an_unrendered_row_is_reported():
    touch = Touch()
    result = Result("feed_purchases", "ok", Scope(), "currency", {"total": 3.0},
                    [{"domain": "piggery", "label": "Piggery", "total": 1.0}, {"domain": "poultry", "label": "Poultry", "total": 2.0}])
    touch.figures(result.figures)["total"]
    touch.rows(result.rows)[0]["label"]                          # only touches the first row's label (and the counter)
    touch.rows_seen = 1
    assert any("never rendered" in k for _, k in touch.unrendered(result))


def test_every_registry_metric_has_a_template_and_a_title():
    assert set(TEMPLATES) == set(REGISTRY) == set(TITLES)


def test_a_figure_marked_rendered_by_a_note_must_really_be_in_the_note():
    from render.tracking import rendered_by_note
    result = Result("mortality", "ok", Scope(), "%", {"opening": 26}, [], notes=["Mortality = deaths ÷ animals at risk (26 at the start)."])
    rendered_by_note(result, Touch().figures(result.figures), "opening")
    with pytest.raises(AssertionError):
        rendered_by_note(Result("mortality", "ok", Scope(), "%", {"opening": 26}, [], notes=["nothing here"]),
                         Touch().figures({"opening": 26}), "opening")


# --------------------------------------------------------------------------------- fixed layout and hygiene
@pytest.mark.parametrize("case_id", sorted(SPECS))
def test_every_answer_has_the_fixed_layout_and_no_junk(farm_db, case_id):
    text, _, result, _ = answer(farm_db, case_id)
    lines = text.split("\n")
    assert lines[0] and not lines[0].startswith("-"), "line 1 is the echoed scope"
    assert TITLES[result.metric_id] in lines[0]
    if result.metric_id not in ("batch_count", "sow_count"):
        assert lines[-1].startswith(("Data through", "Say 'all time'")) or "Data through" in text
    for junk in (r"\bNone\b", r"\bnan\b", r"\bNaN\b", r"[{}]", r"Decimal", r"datetime", r"  "):
        assert not re.search(junk, text), f"{case_id}: {junk!r} leaked into the answer"
    assert not re.search(r"\b\d{4}-\d{2}-\d{2}\b", text), "dates are shown as 15 Sep 2026, never ISO"


def test_no_llm_anywhere_in_the_render_package():
    for path in pathlib.Path(__file__).parent.parent.joinpath("render").glob("*.py"):
        source = path.read_text().lower()
        assert "openai" not in source and "anthropic" not in source, path.name


def test_the_only_free_text_constants_are_the_greeting_and_the_sign_off():
    assert "farm" in GREETING and ALL_TIME_HINT == "Say 'all time' to ignore the dashboard filter."


# --------------------------------------------------------------------------------- exact answers
def test_golden_piggery_feed_cost_in_a_named_month(farm_db):
    assert answer(farm_db, "fc01")[0] == (
        "Feed consumed cost, Piggery, August 2026\n"
        "Total: $1,050.17 (1,830.9 kg)\n"
        "- Piggery: $1,050.17 (1,830.9 kg)\n"
        "Data through 15 Sep 2026.")


def test_golden_partly_covered_period_says_so(farm_db):
    assert answer(farm_db, "fc04")[0] == (
        "Feed consumed cost, all domains, last month (September 2026)\n"
        "Total: $833.21 (1,292.5 kg)\n"
        "- Poultry: $579.58 (860.7 kg)\n"
        "- Piggery: $253.64 (431.8 kg)\n"
        "Only 15 of the 30 days in this period have records (records run 10 Oct 2025 to 15 Sep 2026).\n"
        "Data through 15 Sep 2026.")


def test_golden_no_record_is_not_a_zero(farm_db):
    assert answer(farm_db, "fc05")[0] == (
        "Feed consumed cost, all domains, this month (October 2026)\n"
        "No feed consumption recorded for that period; latest record is 15 Sep 2026.\n"
        "Data through 15 Sep 2026.")
    assert answer(farm_db, "rv08")[0].split("\n")[1] == "No revenue recorded for that period; latest record is 18 Aug 2026."


def test_golden_dashboard_filter_is_named_and_the_hint_offered(farm_db):
    assert answer(farm_db, "sc01")[0] == (
        "Feed consumed cost, all domains, 1–31 Aug 2026 (dashboard date filter)\n"
        "Total: $1,692.88 (2,628.3 kg)\n"
        "- Piggery: $1,050.17 (1,830.9 kg)\n"
        "- Poultry: $642.70 (797.4 kg)\n"
        "Data through 15 Sep 2026.\n"
        "Say 'all time' to ignore the dashboard filter.")


def test_golden_headcount_states_per_domain_counts_and_the_date(farm_db):
    assert answer(farm_db, "hc03")[0] == (
        "Headcount, all domains, as of 15 Sep 2026\n"
        "Total: 521 animals\n"
        "- Poultry: 509\n"
        "- Piggery: 12\n"
        "Data through 15 Sep 2026.")


def test_golden_batch_count_gives_total_and_active(farm_db):
    text = answer(farm_db, "bc01")[0]
    assert "4 batches in total, 1 active (3 sold)" in text and text.startswith("Batches, Poultry, as they stand now")


def test_golden_mortality_states_its_denominator(farm_db):
    text = answer(farm_db, "mo09")[0]
    assert "BRO-P02: 8.08% (42 deaths of 520 placed)" in text and "Mortality = deaths ÷ animals placed (520)." in text
    text = answer(farm_db, "mo08")[0]
    assert "Mortality rate: 2.43% (51 deaths of 2,102 animals at risk)" in text
    assert "0 at the start of the period + 2,102 added = 2,102" in text


def test_golden_average_weekly_states_the_days_used(farm_db):
    text = answer(farm_db, "fc09")[0]
    assert "Average per week: $303.44" in text and "341 days covered" in text and "13,308" not in text


def test_golden_feed_purchases_for_pigs_is_13308_50(farm_db):
    assert "Total: $13,308.50" in answer(farm_db, "fp03")[0]


def test_golden_expenses_by_domain_show_shared_and_sum_to_the_total(farm_db):
    text, _, result, _ = answer(farm_db, "ex14")
    assert "- Shared (not allocated): $1,528.74" in text and "Total: $30,380.06" in text
    assert round(sum(r["total"] for r in result.rows), 2) == result.figures["total"]


def test_golden_a_loss_is_labelled_a_loss(farm_db):
    text = answer(farm_db, "pf02")[0]
    assert "Loss: -$5,563.50" in text and "- Revenue: $9,333.17" in text and "- Expenses: $14,896.67" in text


def test_golden_receivables_name_the_buyer_and_the_amount(farm_db):
    text = answer(farm_db, "rc01")[0]
    assert "Chikafu Grain Traders: $8,681.12" in text and text.startswith("Money owed to us, all domains")


def test_golden_nobody_owing_is_said_plainly(farm_db):
    assert "Nobody owes us money" in answer(farm_db, "rc07")[0]


def test_golden_only_active_batches_are_ready(farm_db):
    text = answer(farm_db, "mr01")[0]
    assert "PIG-B04" in text and "BRO-P04" in text and "PIG-B01" not in text and "due today" in text


def test_golden_health_says_sickness_is_not_recorded(farm_db):
    assert "whether an animal is sick right now is not recorded" in answer(farm_db, "he04")[0]


def test_golden_sows_give_the_status_split(farm_db):
    assert answer(farm_db, "hc08")[0].split("\n")[1] == "3 sows on the farm (1 lactating, 1 open, 1 pregnant)"


# --------------------------------------------------------------------------------- ordering
def test_breakdown_rows_are_largest_first(farm_db):
    for case_id, key in (("ex14", "total"), ("ex08", "total"), ("fc02", "feed_cost"), ("hc03", "headcount"), ("lb01", "labour_cost")):
        _, _, result, _ = answer(farm_db, case_id)
        values = [r[key] for r in result.rows]
        text = answer(farm_db, case_id)[0]
        positions = [text.index(r["label"]) for r in sorted(result.rows, key=lambda r: -r[key])] if "label" in result.rows[0] else []
        assert positions == sorted(positions), case_id
        assert values  # something to order


def test_a_monthly_series_is_chronological(farm_db):
    res = resolve("feed cost by month", REGISTRY["feed_consumed_cost"], today=EVAL_TODAY)
    result = compute("feed_consumed_cost", farm_db, res.scope)
    text = render(res, result, CTX)
    months = re.findall(r"^- (\d{4}-\d{2}) ", text, re.M)
    assert months == sorted(months) and len(set(months)) > 6


# --------------------------------------------------------------------------------- the filter hint
def test_the_hint_is_only_offered_when_the_filter_changed_the_answer(farm_db):
    case = BY_ID["sc01"]
    metric_id, gold = SPECS["sc01"]
    res = resolve(case.question, REGISTRY[metric_id], today=EVAL_TODAY, dashboard_filter=case.filter)
    result = compute(metric_id, farm_db, gold)
    same = RenderContext(all_time_result=result)                                  # "all time" gives the very same figures
    assert ALL_TIME_HINT not in render(res, result, same)
    assert ALL_TIME_HINT in render(res, result, RenderContext(all_time_result=compute(metric_id, farm_db, all_time_scope(gold))))
    assert ALL_TIME_HINT not in render(res, result, RenderContext())              # no all-time result supplied: no hint


# --------------------------------------------------------------------------------- formatting
def test_money_uses_the_farm_currency_with_thousand_separators_and_half_up():
    assert fmt.money(1692.88) == "$1,692.88" and fmt.money(4781.455) == "$4,781.46" and fmt.money(-5563.5) == "-$5,563.50"
    assert fmt.money(1234.5, "ZWG") == "ZWG 1,234.50"                           # an unknown code is shown, never dropped
    assert RenderContext(currency="GBP").money(10) == "£10.00"


def test_every_amount_in_an_answer_follows_the_currency_setting(farm_db):
    text = answer(farm_db, "ex14", RenderContext(currency="ZWG", data_through=SYNC_DATE))[0]
    assert "ZWG 30,380.06" in text and "$" not in text


def test_fixed_decimals_per_unit():
    assert fmt.num(2628.3, 1) == "2,628.3" and fmt.num(12) == "12" and fmt.pct(2.225) == "2.23%" and fmt.num(None) == "n/a"
    assert fmt.date("2026-09-15") == "15 Sep 2026" and fmt.plural(1, "sow") == "1 sow" and fmt.plural(3, "batch", "batches") == "3 batches"


def test_human_domain_names_never_codes(farm_db):
    text = answer(farm_db, "ex14")[0]
    assert "Piggery" in text and "piggery" not in text and "Shared (not allocated)" in text


# --------------------------------------------------------------------------------- refusals
def test_a_named_refusal_is_just_its_message():
    for case_id, (metric_id, code) in REFUSAL_SPECS.items():
        case = BY_ID[case_id]
        res = resolve(case.question, REGISTRY[metric_id], today=EVAL_TODAY)
        assert render_refusal(res) == res.unresolved.message and "compare two periods" in render_refusal(res)


# --------------------------------------------------------------------------------- the measurement for step 4
@pytest.mark.parametrize("case_id", sorted(SPECS))
def test_templated_answers_score_correct_with_perfect_routing(farm_db, case_id):
    """With the router given the gold spec, the resolver + registry + template give an answer the eval scorer marks CORRECT:
    no wrong number, no omitted figure or row, no raw dump. The remaining error budget is routing (step 5), nothing else."""
    case = BY_ID[case_id]
    text, _, _, _ = answer(farm_db, case_id)
    name, kwargs = case.oracle
    outcome, reason = score(case.kind, getattr(Oracle(farm_db), name)(**kwargs), Observed("answer", text))
    assert (outcome, reason) == ("correct", ""), f"{case_id}: {outcome}:{reason}\n{text}"
