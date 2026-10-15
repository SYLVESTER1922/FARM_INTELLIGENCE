"""Scope accuracy as a pure function: for every answerable dev case, the resolver - given only the question text, the
metric, the dashboard filter and the eval clock - produces exactly the scope in the case's gold spec. No LLM, no database.
(The gold specs are evals/case_specs.py; the eval clock is 2026-10-15 in Africa/Harare.)"""

import pytest

from evals.case_specs import REFUSAL_SPECS, SPECS
from evals.cases_dev import CASES
from evals.oracle import EVAL_TODAY
from registry import REGISTRY
from registry.core import WEEKDAYS
from resolver import resolve

BY_ID = {c.id: c for c in CASES}
FIELDS = ("domains", "start", "end", "as_of", "aggregation", "grain", "batch_code")


def _resolve(case, metric_id):
    """Each case carries its own clock and week start when the question depends on them."""
    week_start = WEEKDAYS.index(case.week_start) if case.week_start else 0
    return resolve(case.question, REGISTRY[metric_id], today=case.today or EVAL_TODAY,
                   dashboard_filter=case.filter, week_start=week_start)


@pytest.mark.parametrize("case_id", sorted(SPECS))
def test_the_resolver_produces_the_gold_scope(case_id):
    case = BY_ID[case_id]
    metric_id, gold = SPECS[case_id]
    r = _resolve(case, metric_id)
    assert r.ok, f"{case_id}: {r.unresolved}"
    got = {f: getattr(r.scope, f) for f in FIELDS}
    want = {f: getattr(gold, f) for f in FIELDS}
    assert got == want, f"{case_id} {case.question!r}: resolver gave {got}, gold is {want}"


def test_every_filter_case_names_the_rule_that_fired():
    rule = {c.id: _resolve(c, SPECS[c.id][0]).period_source for c in CASES if c.id.startswith("sc")}
    assert rule == {"sc01": "filter", "sc02": "question", "sc03": "all_time", "sc04": "snapshot",
                    "sc05": "all_time", "sc06": "all_time", "sc07": "all_time"}


def test_refusal_and_clarification_cases_never_resolve_to_a_confident_period_by_accident():
    """Questions with no spec must not crash the resolver, whatever metric they get routed to."""
    for c in CASES:
        if c.id in SPECS:
            continue
        for metric in (REGISTRY["expenses"], REGISTRY["active_headcount"]):
            resolve(c.question, metric, today=EVAL_TODAY, dashboard_filter=c.filter)


@pytest.mark.parametrize("case_id", sorted(REFUSAL_SPECS))
def test_comparison_questions_are_a_named_refusal(case_id):
    metric_id, code = REFUSAL_SPECS[case_id]
    r = _resolve(BY_ID[case_id], metric_id)
    assert r.unresolved is not None and r.unresolved.code == code
    assert "compare two periods" in r.unresolved.message and "separately" in r.unresolved.message


def test_the_clock_and_week_start_overrides_are_what_make_those_cases_differ():
    lw01, lw02 = BY_ID["lw01"], BY_ID["lw02"]
    assert lw01.question == lw02.question and lw01.today == lw02.today and lw01.week_start != lw02.week_start
