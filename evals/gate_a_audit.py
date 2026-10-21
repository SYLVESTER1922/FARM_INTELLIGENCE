"""
Gate A audit (plan section 12): per launch metric, does it have a definition, a template, a parity test (or a recorded reason it has no
dashboard counterpart; tests/test_registry_oracle_agreement.py then checks every answerable dev case of the metric against the independent oracle) and eval cases? Prints a table and the verdict per item.

    python -m evals.gate_a_audit

The plan says "at least N eval cases (N set per group in the build)". Sylvester set N on 2026-10-20: 8 dev cases per zero-tolerance metric
(money, headcount), 4 per other metric, 5 per refusal class that is new in step 6 (held-out target later: about 16 per zero-tolerance
metric). Dev cases are Sylvester's to approve, so approved cases (evals/cases_dev.py, including evals/cases_dev_round2.py) are
never added by this script (the round-2 additions were approved 2026-10-20 and live in evals/cases_dev_round2.py).
"""

import collections
import re
from pathlib import Path

from evals.case_specs import SPECS
from evals.cases_dev import CASES
from registry import REGISTRY
from render.templates import TEMPLATES

N = {"zero_tolerance": 8, "other": 4, "refusal_class": 5}
NEW_REFUSAL_CLASSES = ("staff_info", "staff_pay", "crop_scouting", "field_operations")
REPO = Path(__file__).resolve().parent.parent


def audit():
    parity_text = (REPO / "tests" / "test_registry_parity.py").read_text()
    cases = collections.Counter(spec[0] for spec in SPECS.values())
    cases["sow_count"] += sum(c.id == "dsw05" for c in CASES)    # a refuse case (no gold spec) that belongs to the metric
    rows = []
    for m in REGISTRY.values():
        hooks_tested = all(re.search(rf"\b{re.escape(h)}\b", parity_text) for h in m.dashboard)
        rows.append({
            "metric": m.id, "zero_tolerance": m.zero_tolerance,
            "definition": bool(m.definition.strip()),
            "template": m.id in TEMPLATES,
            "parity": bool(m.dashboard) and hooks_tested,
            "parity_exempt": bool(m.parity_exempt) and not m.dashboard,
            "oracles": len(m.eval_oracles),
            "cases": cases.get(m.id, 0),
            "n_required": N["zero_tolerance" if m.zero_tolerance else "other"],
        })
    return rows


def refusal_classes():
    """{class: cases} for the refusal classes new in step 6."""
    n = collections.Counter(c.refusal for c in CASES if c.refusal)
    return {k: n.get(k, 0) for k in NEW_REFUSAL_CLASSES}


def main():
    rows = audit()
    print(f"{'metric':22} zt  def  tmpl parity        oracles cases / N")
    for r in rows:
        parity = "yes" if r["parity"] else ("exempt+oracle" if r["parity_exempt"] else "NO")
        flag = "" if r["cases"] >= r["n_required"] else "  <-- below N"
        print(f"{r['metric']:22} {'T' if r['zero_tolerance'] else 'F'}   {'y' if r['definition'] else 'N'}    {'y' if r['template'] else 'N'}    "
              f"{parity:13} {r['oracles']:<7} {r['cases']} / {r['n_required']}{flag}")
    n = len(rows)
    print(f"\ndefinition {sum(r['definition'] for r in rows)}/{n}; template {sum(r['template'] for r in rows)}/{n}; "
          f"parity test {sum(r['parity'] for r in rows)}/{n} + {sum(r['parity_exempt'] for r in rows)} exempt; "
          f"eval cases >= N: {sum(r['cases'] >= r['n_required'] for r in rows)}/{n}")
    print("\nnew refusal classes (cases / N):")
    for k, n_cases in refusal_classes().items():
        print(f"  {k:18} {n_cases} / {N['refusal_class']}")


if __name__ == "__main__":
    main()
