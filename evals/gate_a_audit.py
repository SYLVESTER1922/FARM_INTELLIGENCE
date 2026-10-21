"""
Gate A audit (plan section 12): per launch metric, does it have a definition, a template, a parity test (or a recorded reason it has no
dashboard counterpart; tests/test_registry_oracle_agreement.py then checks every answerable dev case of the metric against the independent oracle) and eval cases? Prints a table and the verdict per item.

    python -m evals.gate_a_audit

The plan says "at least N eval cases (N set per group in the build)". Sylvester set N on 2026-10-20: 8 dev cases per zero-tolerance metric
(money, headcount), 4 per other metric, 5 per refusal class that is new in step 6 (held-out target later: about 16 per zero-tolerance
metric). Dev cases are Sylvester's to approve, so approved cases (evals/cases_dev.py) and unreviewed drafts (evals/cases_dev_drafts.py) are
counted separately and this script never adds cases.
"""

import collections
import re
from pathlib import Path

from evals.case_specs import SPECS
from evals.cases_dev import CASES
from evals.cases_dev_drafts import DRAFT_SPECS, DRAFTS
from registry import REGISTRY
from render.templates import TEMPLATES

N = {"zero_tolerance": 8, "other": 4, "refusal_class": 5}
NEW_REFUSAL_CLASSES = ("staff_info", "staff_pay", "crop_scouting", "field_operations")
REPO = Path(__file__).resolve().parent.parent


def audit():
    parity_text = (REPO / "tests" / "test_registry_parity.py").read_text()
    cases = collections.Counter(spec[0] for spec in SPECS.values())
    drafts = collections.Counter(spec[0] for spec in DRAFT_SPECS.values())
    for c in DRAFTS:                                              # a draft refuse/clarify case counts for the metric it belongs to
        if c.id in {"dca05", "dsw05"}:
            drafts[{"dca05": "feed_cost_per_animal", "dsw05": "sow_count"}[c.id]] += 1
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
            "cases": cases.get(m.id, 0), "drafts": drafts.get(m.id, 0),
            "n_required": N["zero_tolerance" if m.zero_tolerance else "other"],
        })
    return rows


def refusal_classes():
    """{class: (approved cases, drafts)} for the refusal classes new in step 6."""
    approved = collections.Counter(c.refusal for c in CASES if c.refusal)
    draft = collections.Counter(c.refusal for c in DRAFTS if c.refusal)
    return {k: (approved.get(k, 0), draft.get(k, 0)) for k in NEW_REFUSAL_CLASSES}


def main():
    rows = audit()
    print(f"{'metric':22} zt  def  tmpl parity        oracles approved+drafts / N")
    for r in rows:
        parity = "yes" if r["parity"] else ("exempt+oracle" if r["parity_exempt"] else "NO")
        flag = ("" if r["cases"] >= r["n_required"] else
                ("  <-- below N; met once the drafts are approved" if r["cases"] + r["drafts"] >= r["n_required"] else "  <-- below N"))
        print(f"{r['metric']:22} {'T' if r['zero_tolerance'] else 'F'}   {'y' if r['definition'] else 'N'}    {'y' if r['template'] else 'N'}    "
              f"{parity:13} {r['oracles']:<7} {r['cases']}+{r['drafts']} / {r['n_required']}{flag}")
    n = len(rows)
    print(f"\ndefinition {sum(r['definition'] for r in rows)}/{n}; template {sum(r['template'] for r in rows)}/{n}; "
          f"parity test {sum(r['parity'] for r in rows)}/{n} + {sum(r['parity_exempt'] for r in rows)} exempt; "
          f"eval cases >= N (approved only): {sum(r['cases'] >= r['n_required'] for r in rows)}/{n}; "
          f"with drafts: {sum(r['cases'] + r['drafts'] >= r['n_required'] for r in rows)}/{n}")
    print("\nnew refusal classes (approved + drafts / N):")
    for k, (a, d) in refusal_classes().items():
        print(f"  {k:18} {a}+{d} / {N['refusal_class']}")


if __name__ == "__main__":
    main()
