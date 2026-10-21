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


def test_every_metric_and_new_refusal_class_meets_the_approved_minimums():
    from evals.gate_a_audit import N, refusal_classes
    short = [r["metric"] for r in audit() if r["cases"] < r["n_required"]]
    assert not short, short
    assert all(n >= N["refusal_class"] for n in refusal_classes().values()), refusal_classes()
