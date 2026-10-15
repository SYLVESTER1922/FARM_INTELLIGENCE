"""For every answerable dev case, the registry - given the case's gold spec (evals/case_specs.py) - returns the
figures the independent oracle (evals/oracle.py) expects. The two are written separately, so a disagreement is
a finding about one of them, not a test to patch."""

import datetime as dt
import decimal

import pytest

from evals.case_specs import SPECS
from evals.cases_dev import CASES
from evals.oracle import Oracle
from registry import compute

BY_ID = {c.id: c for c in CASES}
NO_RECORD_ORACLES = {"feed_cost_no_data", "no_record"}


def _flatten(result):
    nums, strs = [], []

    def walk(o):
        if isinstance(o, bool) or o is None:
            return
        if isinstance(o, (int, float, decimal.Decimal)):
            nums.append(float(o))
        elif isinstance(o, (dt.date, dt.datetime)):
            strs.append(str(o))
        elif isinstance(o, str):
            strs.append(o)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)

    walk(result.figures)
    walk(result.rows)
    strs += [result.message or ""] + list(result.notes)
    return nums, " | ".join(strs).lower()


def _has(nums, want, sign_agnostic=False):
    return any(abs((abs(n) if sign_agnostic else n) - (abs(want) if sign_agnostic else want)) <= 0.005 for n in nums)


@pytest.mark.parametrize("case_id", sorted(SPECS))
def test_registry_agrees_with_the_oracle(farm_db, case_id):
    case = BY_ID[case_id]
    metric, scope = SPECS[case_id]
    name, kwargs = case.oracle
    exp = getattr(Oracle(farm_db), name)(**kwargs)
    result = compute(metric, farm_db, scope)

    if name in NO_RECORD_ORACLES:
        assert result.status == "no_record", f"{case_id}: expected 'No ... recorded', got {result.status}"
        from render import _human_dates          # the registry message carries ISO dates; answers show 15 Sep 2026
        shown = _human_dates(result.message).lower()
        assert all(w.lower() in shown for w in exp.words), (exp.words, shown)
        return

    assert result.ok, f"{case_id}: {metric} returned {result.status}: {result.message}"
    nums, text = _flatten(result)
    for want in exp.required:
        assert _has(nums, want, exp.sign_agnostic), f"{case_id}: {want} not among the registry's figures"
    for group in exp.any_of:
        assert any(_has(nums, w) for w in group), f"{case_id}: none of {group} among the registry's figures"
    for word in exp.words:
        assert word.lower() in text, f"{case_id}: {word!r} missing from the registry result"
    for word in exp.forbidden_words:
        assert word.lower() not in text, f"{case_id}: {word!r} must not appear"
    for bad in exp.forbidden:
        assert not _has(nums, bad), f"{case_id}: forbidden figure {bad} appears"
