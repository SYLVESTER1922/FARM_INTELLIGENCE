"""The objective part of the Gate A audit: every metric has a definition, a template, a parity test or a recorded exemption, and
an independent oracle with at least one dev case. The proposed per-group case counts are reported by evals/gate_a_audit.py, not enforced."""

from evals.gate_a_audit import audit


def test_every_metric_has_a_definition_a_template_and_parity_or_a_recorded_exemption():
    for r in audit():
        assert r["definition"] and r["template"], r["metric"]
        assert r["parity"] or r["parity_exempt"], r["metric"]


def test_every_metric_has_an_oracle_and_at_least_one_dev_case():
    for r in audit():
        assert r["oracles"] >= 1 and r["cases"] >= 1, r["metric"]


def test_drafts_reach_the_minimums_so_gate_a_can_be_judged_once_they_are_approved():
    from evals.gate_a_audit import N, refusal_classes
    assert all(r["cases"] + r["drafts"] >= r["n_required"] for r in audit()), [r["metric"] for r in audit()
                                                                                if r["cases"] + r["drafts"] < r["n_required"]]
    assert all(a + d >= N["refusal_class"] for a, d in refusal_classes().values())


def test_no_draft_has_leaked_into_the_dev_set():
    from evals.cases_dev import CASES
    from evals.cases_dev_drafts import DRAFTS
    assert not {c.id for c in CASES} & {c.id for c in DRAFTS}
