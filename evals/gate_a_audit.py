"""
Gate A audit (plan section 12): per launch metric, does it have a definition, a template, a parity test (or a recorded reason it has no
dashboard counterpart; tests/test_registry_oracle_agreement.py then checks every answerable dev case of the metric against the independent oracle) and eval cases? Prints a table and the verdict per item.

    python -m evals.gate_a_audit

The plan says "at least N eval cases (N set per group in the build)" and N was never set. The thresholds below are PROPOSED and marked as
such in the output; the dev cases are Sylvester's to approve, so this script reports shortfalls and never adds cases.
"""

import collections
import re
from pathlib import Path

from evals.case_specs import SPECS
from registry import REGISTRY
from render.templates import TEMPLATES

PROPOSED_N = {"zero_tolerance": 5, "other": 3}
REPO = Path(__file__).resolve().parent.parent


def audit():
    parity_text = (REPO / "tests" / "test_registry_parity.py").read_text()
    cases = collections.Counter(spec[0] for spec in SPECS.values())
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
            "n_required": PROPOSED_N["zero_tolerance" if m.zero_tolerance else "other"],
        })
    return rows


def main():
    rows = audit()
    print(f"{'metric':22} zt  def  tmpl parity        oracles cases/N")
    for r in rows:
        parity = "yes" if r["parity"] else ("exempt+oracle" if r["parity_exempt"] else "NO")
        flag = "" if r["cases"] >= r["n_required"] else "  <-- below proposed N"
        print(f"{r['metric']:22} {'T' if r['zero_tolerance'] else 'F'}   {'y' if r['definition'] else 'N'}    {'y' if r['template'] else 'N'}    "
              f"{parity:13} {r['oracles']:<7} {r['cases']}/{r['n_required']}{flag}")
    n = len(rows)
    print(f"\ndefinition {sum(r['definition'] for r in rows)}/{n}; template {sum(r['template'] for r in rows)}/{n}; "
          f"parity test {sum(r['parity'] for r in rows)}/{n} + {sum(r['parity_exempt'] for r in rows)} exempt; "
          f"eval cases >= proposed N: {sum(r['cases'] >= r['n_required'] for r in rows)}/{n}")


if __name__ == "__main__":
    main()
