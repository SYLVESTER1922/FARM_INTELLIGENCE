"""
Eval harness runner.

    export DATABASE_URL=postgresql://$USER@localhost/farm_intelligence_test
    python -m evals.run --engine-root <repo-or-worktree> --label <name>
    python -m evals.run --dump-review          # write the reviewer's case sheet, no engine

Refuses to run unless DATABASE_URL names the local farm_intelligence_test
database (evals/guard.py). Rebuilds the fixture from the workbook (read-only)
at the start of each run, then calls chatbot.engine.answer_question from the
given engine root N times per case and scores every answer against the
independent oracle. Wrong if ANY repeat is wrong.
"""

import argparse
import collections
import concurrent.futures as cf
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from evals import build_fixture
from evals.guard import checked_database_url, connect_guarded
from evals.oracle import Oracle
from evals.score import Observed, combine, is_raw_dump, score

REPO = Path(__file__).resolve().parent.parent
FARM = build_fixture.FARM_CODE


def _load_openai_key():
    path = Path.home() / ".openai_api_key"
    if "OPENAI_API_KEY" not in os.environ and path.exists():
        os.environ["OPENAI_API_KEY"] = path.read_text().strip()


def load_cases(include_locked: bool):
    from evals.cases_dev import CASES
    cases = list(CASES)
    locked = [c for c in cases if c.split != "dev"]
    if locked and not include_locked:
        raise SystemExit(f"REFUSING: {len(locked)} non-dev case(s) present; pass --include-locked "
                         "only at a release gate.")
    return cases


def build_expectations(cases):
    conn = connect_guarded()
    oracle = Oracle(conn)
    out = {}
    for c in cases:
        name, kwargs = c.oracle
        try:
            out[c.id] = getattr(oracle, name)(**kwargs)
        except Exception as e:  # an oracle bug must stop the run, not skew it
            raise SystemExit(f"oracle failed for {c.id} ({name}): {type(e).__name__}: {e}")
    conn.close()
    return out


def _fmt_expect(e):
    parts = []
    if e.required:
        parts.append("figures " + ", ".join(f"{x:,.2f}".rstrip("0").rstrip(".") for x in e.required))
    for g in e.any_of:
        parts.append("any of " + " / ".join(f"{x:,.2f}".rstrip("0").rstrip(".") for x in g))
    if e.words:
        parts.append("mentions " + ", ".join(e.words))
    if e.words_any:
        parts.append("one of " + ", ".join(repr(w) for w in e.words_any))
    if e.forbidden:
        parts.append("must NOT show " + ", ".join(f"{x:,.2f}".rstrip("0").rstrip(".") for x in e.forbidden))
    if e.forbidden_words:
        parts.append("must NOT list " + ", ".join(e.forbidden_words))
    if e.not_claims:
        parts.append("must NOT claim data is untracked")
    if not e.scored:
        parts.append("NOT SCORED (definition pending)")
    return "; ".join(parts) or "-"


def dump_review(cases, expectations, path: Path):
    lines = ["# Dev case sheet (DRAFT, for review by Sylvester and Tadiwanashe Dzimbanete)\n",
             "All cases are `dev`. Nothing is locked. Expected figures are computed from the fixture "
             "database by the independent oracle (`evals/oracle.py`), not copied from any engine.\n",
             f"Eval clock: today = 2026-10-15 (Africa/Harare); latest data in the fixture = 2026-09-15.\n",
             "`v1` = a v1-style engine could be expected to get it right; `v2_only` = depends on a v2 decision "
             "(calendar periods, clarification, filter precedence).\n",
             "| id | source | group | zt | fair | kind | question | expected | filter | review note |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for c in cases:
        e = expectations[c.id]
        note = "; ".join(x for x in (c.review, e.note) if x).replace("|", "/")
        flt = f"{c.filter[0]}..{c.filter[1]}" if c.filter else ""
        lines.append(f"| {c.id} | {c.source} | {c.group} | {'Y' if c.zt else ''} | {c.fair} | {c.kind} | "
                     f"{c.question.replace('|', '/')} | {_fmt_expect(e).replace('|', '/')} | {flt} | {note} |")
    path.write_text("\n".join(lines) + "\n")


def observe(engine, ans) -> Observed:
    if ans.intent_source == "needs_clarification" or ans.failure_reason == "missing_parameter":
        return Observed("clarify", ans.text)
    if ans.scoped_out_reason:
        return Observed("scoped_out", ans.text)
    if ans.intent_source == "unresolved":
        if ans.failure_reason in ("invalid_tool_argument", "unresolvable_period") \
                or ans.text.strip() == engine.UNRESOLVED_TEMPLATE:
            return Observed("refusal_generic", ans.text)
        return Observed("refusal_claim", ans.text)
    return Observed("answer", ans.text)


def git_info(root: Path):
    def g(*args):
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True).stdout.strip()
    return {"commit": g("rev-parse", "--short", "HEAD"), "dirty_files": g("status", "--short").splitlines()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine-root", default=str(REPO))
    ap.add_argument("--label", default="run")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--only", default="")
    ap.add_argument("--include-locked", action="store_true")
    ap.add_argument("--no-rebuild", action="store_true")
    ap.add_argument("--dump-review", action="store_true")
    args = ap.parse_args()

    checked_database_url()                      # refuse before anything else happens
    cases = load_cases(args.include_locked)
    if args.only:
        wanted = set(args.only.split(","))
        cases = [c for c in cases if c.id in wanted]

    if not args.no_rebuild:
        build_fixture.build()
    expectations = build_expectations(cases)

    if args.dump_review:
        out = REPO / "evals" / "REVIEW_dev_cases.md"
        dump_review(cases, expectations, out)
        print(f"wrote {out} ({len(cases)} cases)")
        return

    root = Path(args.engine_root).resolve()
    sys.path.insert(0, str(root))
    _load_openai_key()
    from chatbot import engine
    if not Path(engine.__file__).resolve().is_relative_to(root):
        raise SystemExit(f"REFUSING: chatbot.engine imported from {engine.__file__}, not {root}")
    url = checked_database_url()

    # The engine runs CREATE TABLE IF NOT EXISTS / ALTER TABLE on query_log for
    # every question; with parallel workers on a fresh database those race
    # (UniqueViolation on pg_class). Create it once up front, using the
    # engine's own DDL, so the race cannot occur. Engine code is not touched.
    warm = connect_guarded()
    engine._ensure_query_log_table(warm)
    warm.close()

    def run_one(case, rep):
        df, dt_ = case.filter if case.filter else (None, None)
        t0 = time.time()
        try:
            ans = engine.answer_question(case.question, FARM, url, df, dt_)
            obs = observe(engine, ans)
            extra = {"intent_source": ans.intent_source, "tool": ans.tool_name, "query_id": ans.query_id}
        except Exception as e:
            obs, extra = Observed("error", f"{type(e).__name__}: {e}"), {}
        outcome, reason = score(case.kind, expectations[case.id], obs, case.denial_topics)
        return case.id, {"rep": rep, "outcome": outcome, "reason": reason, "observed": obs.kind,
                         "text": obs.text, "secs": round(time.time() - t0, 2), **extra}

    runs = collections.defaultdict(list)
    jobs = [(c, r) for c in cases for r in range(args.repeats)]
    print(f"[{args.label}] engine={root} {git_info(root)['commit']}  cases={len(cases)} "
          f"repeats={args.repeats}  calls={len(jobs)}", flush=True)
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_one, c, r) for c, r in jobs]
        for i, f in enumerate(cf.as_completed(futures), 1):
            cid, rec = f.result()
            runs[cid].append(rec)
            if i % 50 == 0:
                print(f"  {i}/{len(jobs)}", flush=True)

    results = []
    for c in cases:
        rs = sorted(runs[c.id], key=lambda r: r["rep"])
        outcome, reason, flaky = combine([(r["outcome"], r["reason"]) for r in rs])
        shown = next((r for r in rs if r["outcome"] == outcome and (r["reason"] == reason)), rs[0])
        results.append({"id": c.id, "question": c.question, "group": c.group, "fair": c.fair, "zt": c.zt,
                        "source": c.source, "kind": c.kind, "outcome": outcome, "reason": reason, "flaky": flaky,
                        "expected": _fmt_expect(expectations[c.id]), "answer": shown["text"], "runs": rs})

    summary = summarise(results)
    outdir = REPO / "evals" / "results"
    outdir.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = outdir / f"{args.label}-{stamp}.json"
    path.write_text(json.dumps({"label": args.label, "engine_root": str(root), "git": git_info(root),
                                "repeats": args.repeats, "summary": summary, "results": results},
                               indent=2, default=str))
    print_report(args.label, results, summary)
    print(f"\nresults written to {path}")


def _rates(rs):
    scored = [r for r in rs if r["outcome"] != "unscored"]
    n = len(scored)
    cnt = collections.Counter(r["outcome"] for r in scored)
    pct = lambda k: round(100.0 * cnt[k] / n, 1) if n else 0.0
    return {"n_scored": n, "correct": cnt["correct"], "wrong": cnt["wrong"], "refused": cnt["refused"],
            "clarified": cnt["clarified"], "review": cnt["review"], "error": cnt["error"],
            "wrong_pct": pct("wrong"), "refused_pct": pct("refused"), "clarified_pct": pct("clarified"),
            "correct_pct": pct("correct"), "unscored": len(rs) - n}


def summarise(results):
    out = {"all": _rates(results),
           "zero_tolerance": _rates([r for r in results if r["zt"]]),
           "v1_fair_only": _rates([r for r in results if r["fair"] == "v1"]),
           "v2_only": _rates([r for r in results if r["fair"] == "v2_only"]),
           "live_failures": _rates([r for r in results if r["source"] == "live"]),
           "by_group": {g: _rates([r for r in results if r["group"] == g])
                        for g in sorted({r["group"] for r in results})},
           "wrong_reasons": dict(collections.Counter(r["reason"] for r in results if r["outcome"] == "wrong")),
           "raw_dump_any": sorted({r["id"] for r in results for run in r["runs"] if is_raw_dump(run["text"])}),
           "flaky_cases": [r["id"] for r in results if r["flaky"]]}
    return out


def print_report(label, results, s):
    def line(name, r):
        return (f"  {name:<16} n={r['n_scored']:<4} wrong {r['wrong']:>3} ({r['wrong_pct']:>5}%)  "
                f"refused {r['refused']:>3} ({r['refused_pct']:>5}%)  clarified {r['clarified']:>3} "
                f"({r['clarified_pct']:>5}%)  correct {r['correct']:>3} ({r['correct_pct']:>5}%)"
                f"  review {r['review']}  error {r['error']}")
    print(f"\n=== {label} ===")
    for k in ("all", "zero_tolerance", "v1_fair_only", "v2_only", "live_failures"):
        print(line(k, s[k]))
    print(f"  unscored (pending definitions): {s['all']['unscored']}")
    print("  by group:")
    for g, r in s["by_group"].items():
        print(line(g, r))
    print(f"  wrong reasons: {s['wrong_reasons']}")
    print(f"  raw dumps shown to the user (any reason): {len(s['raw_dump_any'])} -> {s['raw_dump_any']}")
    print(f"  flaky (repeats disagreed): {len(s['flaky_cases'])} -> {s['flaky_cases']}")
    print("\n  WRONG / REVIEW / ERROR cases:")
    for r in results:
        if r["outcome"] in ("wrong", "review", "error"):
            ans = r["answer"].replace("\n", " ")[:150]
            print(f"   {r['id']:<6} {r['outcome']}:{r['reason']:<28} Q: {r['question'][:55]!r}\n"
                  f"          expected: {r['expected'][:90]}\n          got: {ans}")


if __name__ == "__main__":
    main()
