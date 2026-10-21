"""A question that names one entity (a batch) is answered with THAT entity's figure, never a ranking of everything, and never labelled with an entity
the figure is not about. Found in shadow_log: "How many deaths were there in batch BRO-P02?" came back as a ranking of all eight batches led by PIG-B02."""

import datetime as dt

import pytest

from registry import REGISTRY, Scope, compute
from render import RenderContext, render
from resolver import resolve
from router import answer_question_v2
from router.llm_fake import FakeRouter, spec as S

TODAY = dt.date(2026, 10, 15)


def ask(db, question, spec):
    return answer_question_v2(question, db, FakeRouter(script={question: spec}), today=TODAY)


# --------------------------------------------------------------------------------------------------------------- mortality
@pytest.mark.parametrize("extra", [{}, {"dimension": "batch"}, {"dimension": "batch", "domains": ["poultry"]}])
def test_mortality_for_a_named_batch_leads_with_that_batch_whatever_the_model_added(farm_db, extra):
    a = ask(farm_db, "How many deaths were there in batch BRO-P02?", S("mortality", **extra))
    assert a.kind == "answer"
    first, *rest = a.text.splitlines()
    assert first.startswith("Mortality, batch BRO-P02")
    assert rest[0].startswith("BRO-P02: 8.08% (42 deaths of 520 placed)")
    assert "Highest" not in a.text and "PIG-B02" not in a.text and "by batch" not in a.text


def test_mortality_ranks_batches_when_the_question_asks_for_a_ranking(farm_db):
    a = ask(farm_db, "Which batch has the worst mortality?", S("mortality", dimension="batch"))
    assert "Highest: PIG-B02 at 15.38%" in a.text and "BRO-P02" in a.text and "PIG-B04" in a.text


def test_mortality_by_month_for_a_named_batch_is_that_batchs_months_only(farm_db):
    named = compute("mortality", farm_db, Scope(grain="month", batch_code="BRO-P02"))
    every = compute("mortality", farm_db, Scope(grain="month"))
    assert 0 < named.figures["deaths"] == 42 < every.figures["deaths"]


# ------------------------------------------------------------------------------------------------------------------- fcr
def test_fcr_for_a_named_batch_is_its_figure_not_a_best_and_worst_of_one(farm_db):
    a = ask(farm_db, "What is the FCR for PIG-B04?", S("fcr"))
    assert a.text.splitlines()[1].startswith("PIG-B04: FCR ")
    assert "Best:" not in a.text and "worst" not in a.text.lower()


def test_fcr_without_a_batch_still_ranks(farm_db):
    a = ask(farm_db, "Which batch has the worst feed conversion ratio?", S("fcr"))
    assert a.text.splitlines()[1].startswith("Best: ") and "worst: " in a.text.splitlines()[1]


# ---------------------------------------------------------------------------------------------------------------- weight
def test_weight_for_a_named_batch_leads_with_the_batch_then_the_date(farm_db):
    a = ask(farm_db, "What's the average weight of batch PIG-B04?", S("weight"))
    lines = a.text.splitlines()
    assert lines[1].startswith("- PIG-B04 (Piggery): ") and lines[2].startswith("Latest sample on or before ")


def test_weight_without_a_batch_keeps_its_header_first(farm_db):
    a = ask(farm_db, "What do the pigs weigh?", S("weight", domains=["piggery"]))
    assert a.text.splitlines()[1].startswith("Latest sample on or before ")


# ------------------------------------------------------------------------- a filter is applied or refused, never printed and ignored
NO_BATCH = [m.id for m in REGISTRY.values() if not m.batch_filter]


@pytest.mark.parametrize("metric_id", NO_BATCH)
def test_a_metric_that_cannot_filter_by_batch_refuses_instead_of_labelling_a_farm_wide_figure(farm_db, metric_id):
    res = resolve("What about batch PIG-B02?", REGISTRY[metric_id], today=TODAY)
    assert not res.ok and res.unresolved.code == "batch_filter_unsupported" and "single batch" in res.unresolved.message


@pytest.mark.parametrize("question,metric", [("How much feed did batch PIG-B02 eat?", "feed_consumed_cost"),
                                             ("How many pigs are in PIG-B02?", "active_headcount"),
                                             ("What did BRO-P03 cost us in expenses?", "expenses")])
def test_the_chat_says_so_and_shows_no_figure(farm_db, question, metric):
    a = ask(farm_db, question, S(metric))
    assert (a.kind, a.code) == ("refusal", "batch_filter_unsupported") and "$" not in a.text and "batch" in a.text


def test_two_batches_in_one_question_is_a_question_not_a_silent_pick(farm_db):
    a = ask(farm_db, "Compare mortality of PIG-B02 and PIG-B03", S("mortality", dimension="batch"))
    assert (a.kind, a.code) == ("clarify", "multiple_batches") and "PIG-B02, PIG-B03" in a.text


def test_every_metric_that_filters_by_batch_returns_only_that_batch_in_every_view(farm_db):
    for m in (m for m in REGISTRY.values() if m.batch_filter):
        views = [{}] + [{"dimension": d} for d in m.dimensions] + [{"grain": g} for g in m.grains]
        for view in views:
            r = compute(m.id, farm_db, Scope(batch_code="PIG-B04", **view))
            if not r.ok:
                continue
            assert {row["batch_code"] for row in r.rows if "batch_code" in row} <= {"PIG-B04"}, (m.id, view)
            assert not {"worst_batch", "best_batch"} & set(r.figures), (m.id, view)
