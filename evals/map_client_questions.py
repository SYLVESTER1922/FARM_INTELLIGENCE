"""
Plan step 0.5: map the client's own top questions to registry metrics, before the registry is locked.

    python -m evals.map_client_questions evals/client_questions/questions.csv [--model gpt-4o-mini]

Reads a CSV with a `question` column (see evals/client_questions/README.md). For each question it asks the router for its spec (the one
LLM call of the real path) and classifies the outcome:

    matched    one registry metric, and the deterministic wording cues agree with it
    ambiguous  the model could not choose between metrics, or the wording cues point at a different metric than the model chose
    no_metric  the model found no metric (the refusal class is shown: out_of_scope, accounts_payable, ...)
    unreadable the model's reply was not a valid spec, or the call failed

No database, no answers are computed, nothing is sent except the question text. Writes mapping-<timestamp>.md and .csv beside the input.
"""

import argparse
import collections
import csv
import datetime as dt
import os
from pathlib import Path

from registry import REGISTRY
from router import crosscheck
from router.llm import PINNED_MODEL, make_client
from router.prompt import PROMPT_VERSION, system_prompt, user_prompt
from router.spec import json_schema, parse

OPENAI_KEY_FILE = Path.home() / ".openai_api_key"


def read_questions(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("question") or "").strip()]
    if not rows:
        raise SystemExit(f"{path}: no questions found (a `question` column with at least one row is needed).")
    for i, r in enumerate(rows, 1):
        r["id"] = (r.get("id") or "").strip() or f"q{i:02d}"
    return rows


def classify(question, llm):
    """(status, metric_or_none, detail) for one question."""
    res = llm.route(system_prompt(), user_prompt(question), json_schema())
    if not res.ok:
        return "unreadable", None, f"call failed: {res.error}"
    spec = parse(res.data, question)
    if not spec.valid:
        return "unreadable", None, "invalid spec: " + "; ".join(spec.problems)
    if spec.ambiguous_between:
        return "ambiguous", None, "between " + " / ".join(spec.ambiguous_between)
    if spec.metric is None:
        return "no_metric", None, spec.refusal or "out_of_scope"
    bad = crosscheck.metric_disagreement(question, spec)
    if bad:
        return "ambiguous", spec.metric, f"model chose {spec.metric}; the wording also fits " + " / ".join(bad.values[1:])
    return "matched", spec.metric, ""


def run(rows, llm):
    out = []
    for r in rows:
        status, metric, detail = classify(r["question"], llm)
        out.append({**r, "status": status, "metric": metric or "", "detail": detail})
    return out


def report(results, model):
    counts = collections.Counter(r["status"] for r in results)
    hit = collections.Counter(r["metric"] for r in results if r["status"] == "matched")
    lines = [f"# Client questions mapped to the registry", "",
             f"Model `{model}`, prompt {PROMPT_VERSION}, {len(results)} questions, {dt.date.today().isoformat()}.", "",
             "| Status | Questions |", "|---|---|"]
    lines += [f"| {s} | {counts.get(s, 0)} |" for s in ("matched", "ambiguous", "no_metric", "unreadable")]
    lines += ["", "## Per question", "", "| id | question | status | metric | detail |", "|---|---|---|---|---|"]
    for r in results:
        q = r["question"].replace("|", "\\|")
        lines.append(f"| {r['id']} | {q} | {r['status']} | {r['metric']} | {r['detail']} |")
    lines += ["", "## Registry metrics no question matched", ""]
    unused = sorted(set(REGISTRY) - set(hit))
    lines.append(", ".join(unused) if unused else "none")
    lines += ["", "## Metrics reached", ""] + [f"- {m}: {n}" for m, n in hit.most_common()]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("questions", help="CSV with a `question` column")
    ap.add_argument("--model", default=PINNED_MODEL)
    args = ap.parse_args(argv)
    if not os.environ.get("OPENAI_API_KEY") and OPENAI_KEY_FILE.is_file() and not args.model.startswith("claude"):
        os.environ["OPENAI_API_KEY"] = OPENAI_KEY_FILE.read_text().strip()
    rows = read_questions(args.questions)
    results = run(rows, make_client(args.model))
    base = Path(args.questions).resolve().parent / f"mapping-{dt.datetime.now():%Y%m%d-%H%M%S}"
    base.with_suffix(".md").write_text(report(results, args.model))
    with open(base.with_suffix(".csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "question", "status", "metric", "detail"], extrasaction="ignore")
        w.writeheader()
        w.writerows(results)
    counts = collections.Counter(r["status"] for r in results)
    print(f"{len(results)} questions: " + ", ".join(f"{counts.get(s, 0)} {s}" for s in ("matched", "ambiguous", "no_metric", "unreadable")))
    print(f"written: {base.with_suffix('.md')} and {base.with_suffix('.csv')}")
    return results


if __name__ == "__main__":
    main()
