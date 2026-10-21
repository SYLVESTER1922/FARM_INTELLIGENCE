"""
End-to-end eval of the v2 answer path (router -> resolver -> registry -> templates) on the DEV set only, per model.

    export DATABASE_URL=postgresql://$USER@localhost/farm_intelligence_test
    export OPENAI_API_KEY=...            # or put it in ~/.openai_api_key (the file is read when the variable is unset); never stored in the repo
    export ANTHROPIC_API_KEY=...         # optional: a candidate whose key is missing is skipped, and the report says so
    python -m evals.run_v2 --models gpt-4o-mini,gpt-4.1,claude-haiku-5-5 --repeats 3

Same guard as every harness (local farm_intelligence_test only), same independent oracle and scorer as the v1 baselines. Each question runs
N times; a case is wrong if ANY repeat is wrong. Reports, per model: the five-way split (correct, wrong split by cause, refused, clarified),
cost per question, median and p95 latency, and every wrong case with its cause. NOT a held-out figure: dev cases only.
"""

import argparse
import collections
import dataclasses
import concurrent.futures as cf
import datetime as dt
import json
import os
import statistics
import threading
import time
from pathlib import Path

from evals import build_fixture
from evals.case_specs import SPECS
from evals.guard import checked_database_url, connect_guarded
from evals.oracle import EVAL_TODAY
from evals.run import FARM, build_expectations, load_cases, _fmt_expect
from evals.score import Observed, combine, score
from registry.core import WEEKDAYS
from router import answer_question_v2
from router.llm import Unavailable, make_client
from router.prompt import PROMPT_VERSION

REPO = Path(__file__).resolve().parent.parent
OPENAI_KEY_FILE = Path.home() / ".openai_api_key"

# What the plan asks of the routing step (spec-chatbot-v2-plan.md sections 6 and 12, Gate A; decision D11).
TARGET = {"wrong_pct": 2.0, "clarified_pct": 5.0, "median_s": 3.0, "p95_s": 6.0, "cost_usd": 0.01}


def _pct(vals, p):
    vals = sorted(vals)
    if not vals:
        return 0.0
    k = (len(vals) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)


def _scope_fields(scope):
    return {"domains": scope.domains, "period": (scope.start, scope.end, scope.as_of),
            "aggregation": (scope.aggregation, scope.grain), "dimension": scope.dimension,
            "category": scope.category, "batch_code": scope.batch_code}


def cause_of(case, ans, outcome, reason):
    """Why a wrong answer was wrong: which stage first departs from the gold spec. 'pipeline:*' means routing matched the gold spec and
    something after it (resolver, registry, template) was wrong - which should never happen."""
    if outcome == "error":
        return "harness:error"
    if outcome != "wrong":
        return None
    if case.kind == "answer" and ans.kind == "answer":
        gold = SPECS.get(case.id)
        if gold is None or ans.scope is None:
            return f"unknown:{reason}"
        gold_metric, gold_scope = gold
        if ans.metric_id != gold_metric:
            return "routing:metric"
        got, want = _scope_fields(ans.scope), _scope_fields(gold_scope)
        for name in ("domains", "period", "aggregation", "dimension", "category", "batch_code"):
            if got[name] != want[name]:
                return f"routing:{name}"
        return f"pipeline:{reason}"
    if case.kind == "answer" and ans.kind == "refusal":
        return f"refusal_text:{reason}"
    if case.kind == "refuse" and ans.kind == "answer":
        return "routing:should_refuse"
    if case.kind == "refuse":
        return f"refusal_text:{reason}"
    if case.kind == "clarify" and ans.kind == "answer":
        return "routing:should_clarify"
    return f"other:{reason}"


class Pacer:
    """Spaces out the START of calls (not their duration) so a tokens-per-minute limit is not hit. The wait happens before the timed
    section, so it never shows up in the latency figures; a call that still fails is reported as an LLM failure, never retried."""

    def __init__(self, seconds):
        self.seconds, self.next, self.lock = seconds, 0.0, threading.Lock()

    def wait(self):
        if not self.seconds:
            return
        with self.lock:
            now = time.monotonic()
            start = max(now, self.next)
            self.next = start + self.seconds
        time.sleep(max(0.0, start - now))


def run_model(model, cases, expectations, repeats, workers, pace=0.0, mode=None):
    llm = make_client(model, **({"mode": mode} if mode and not model.startswith("claude") else {}))                                   # raises Unavailable if the key or SDK is missing
    pacer = Pacer(pace)

    def one(case, rep):
        pacer.wait()
        conn = connect_guarded()
        try:
            week = WEEKDAYS.index(case.week_start) if case.week_start else 0
            ans = answer_question_v2(case.question, conn, llm, farm_code=FARM, today=case.today or EVAL_TODAY,
                                     dashboard_filter=case.filter, week_start=week)
            obs = Observed(ans.observed_kind, ans.text)
            outcome, reason = score(case.kind, expectations[case.id], obs, case.denial_topics)
            return case.id, {"rep": rep, "outcome": outcome, "reason": reason, "cause": cause_of(case, ans, outcome, reason),
                             "kind": ans.kind, "code": ans.code, "metric": ans.metric_id, "text": ans.text,
                             "seconds": ans.seconds, "llm_seconds": ans.llm.latency_s if ans.llm else 0.0,
                             "cost": ans.llm.cost_usd if ans.llm else 0.0,
                             "tokens_in": ans.llm.input_tokens if ans.llm else 0, "tokens_out": ans.llm.output_tokens if ans.llm else 0,
                             "spec": ans.spec.__dict__ if ans.spec else None, "notes": ans.notes,
                             "llm_error": ans.llm.error if ans.llm else None, "attempts": ans.llm.attempts if ans.llm else 0}
        except Exception as e:
            return case.id, {"rep": rep, "outcome": "error", "reason": f"{type(e).__name__}: {e}"[:160], "cause": "harness:error",
                             "kind": "error", "code": "error", "text": "", "seconds": 0.0, "llm_seconds": 0.0, "cost": 0.0,
                             "tokens_in": 0, "tokens_out": 0, "spec": None, "notes": [], "llm_error": None, "metric": None}
        finally:
            conn.close()

    runs = collections.defaultdict(list)
    jobs = [(c, r) for c in cases for r in range(repeats)]
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        for i, f in enumerate(cf.as_completed([pool.submit(one, c, r) for c, r in jobs]), 1):
            cid, rec = f.result()
            runs[cid].append(rec)
            if i % 100 == 0:
                print(f"    {i}/{len(jobs)}", flush=True)
    results = []
    for c in cases:
        rs = sorted(runs[c.id], key=lambda r: r["rep"])
        outcome, reason, flaky = combine([(r["outcome"], r["reason"]) for r in rs])
        shown = next((r for r in rs if (r["outcome"], r["reason"]) == (outcome, reason)), rs[0])
        results.append({"id": c.id, "question": c.question, "kind": c.kind, "group": c.group, "zt": c.zt, "fair": c.fair,
                        "outcome": outcome, "reason": reason, "cause": shown["cause"], "flaky": flaky,
                        "expected": _fmt_expect(expectations[c.id]), "answer": shown["text"], "code": shown["code"],
                        "metric": shown["metric"], "spec": shown["spec"], "runs": rs})
    return results, time.time() - t0


def summarise(results):
    n = len(results)
    cnt = collections.Counter(r["outcome"] for r in results)
    wrong_causes = collections.Counter(r["cause"] for r in results if r["outcome"] == "wrong")
    runs = [run for r in results for run in r["runs"]]
    e2e = [x["seconds"] for x in runs]
    llm_s = [x["llm_seconds"] for x in runs if x["llm_seconds"]]
    costs = [x["cost"] for x in runs]
    answerable = [r for r in results if r["id"] in SPECS]
    clarified_answerable = [r for r in answerable if r["outcome"] == "clarified"]
    zt = [r for r in results if r["zt"]]
    return {
        "n_cases": n, "n_runs": len(runs),
        "correct": cnt["correct"], "wrong": cnt["wrong"], "refused": cnt["refused"], "clarified": cnt["clarified"],
        "review": cnt["review"], "unscored": cnt["unscored"], "error": cnt["error"],
        "wrong_pct": round(100 * cnt["wrong"] / n, 1), "refused_pct": round(100 * cnt["refused"] / n, 1),
        "clarified_pct": round(100 * cnt["clarified"] / n, 1), "correct_pct": round(100 * cnt["correct"] / n, 1),
        "wrong_causes": dict(wrong_causes),
        "zero_tolerance": {"n": len(zt), "wrong": sum(r["outcome"] == "wrong" for r in zt)},
        "answerable": {"n": len(answerable), "correct": sum(r["outcome"] == "correct" for r in answerable),
                       "clarified": len(clarified_answerable),
                       "refused": sum(r["outcome"] == "refused" for r in answerable),
                       "wrong": sum(r["outcome"] == "wrong" for r in answerable)},
        "clarified_codes_on_answerable": dict(collections.Counter(r["code"] for r in clarified_answerable)),
        "cost_per_question_usd": round(statistics.mean(costs), 6) if costs else 0.0,
        "max_cost_usd": round(max(costs), 6) if costs else 0.0,
        "latency_e2e_median_s": round(statistics.median(e2e), 2) if e2e else 0.0,
        "latency_e2e_p95_s": round(_pct(e2e, 95), 2),
        "latency_llm_median_s": round(statistics.median(llm_s), 2) if llm_s else 0.0,
        "latency_llm_p95_s": round(_pct(llm_s, 95), 2),
        "llm_failures": sum(1 for x in runs if x["llm_error"]),
        "llm_retried": sum(1 for x in runs if x.get("attempts", 1) > 1),
        "flaky": sum(r["flaky"] for r in results),
        "tokens_in_mean": round(statistics.mean([x["tokens_in"] for x in runs if x["tokens_in"]] or [0])),
    }


def meets_target(s):
    return {"wrong<=2%": s["wrong_pct"] <= TARGET["wrong_pct"], "clarified<=5%": s["clarified_pct"] <= TARGET["clarified_pct"],
            "median<=3s": s["latency_e2e_median_s"] <= TARGET["median_s"], "p95<=6s": s["latency_e2e_p95_s"] <= TARGET["p95_s"],
            "cost<=1c": s["max_cost_usd"] <= TARGET["cost_usd"]}


def print_report(model, s, results, elapsed):
    print(f"\n=== {model}   prompt {PROMPT_VERSION}   (DEV set, {s['n_cases']} cases x repeats, {elapsed:.0f}s) ===")
    print(f"  correct {s['correct']} ({s['correct_pct']}%)   wrong {s['wrong']} ({s['wrong_pct']}%)   refused {s['refused']} "
          f"({s['refused_pct']}%)   clarified {s['clarified']} ({s['clarified_pct']}%)   review {s['review']}   error {s['error']}")
    print(f"  wrong by cause: {s['wrong_causes'] or 'none'}")
    print(f"  money+headcount: {s['zero_tolerance']['wrong']} wrong of {s['zero_tolerance']['n']}   |   answerable cases: "
          f"{s['answerable']['correct']}/{s['answerable']['n']} correct, {s['answerable']['clarified']} clarified, "
          f"{s['answerable']['refused']} refused, {s['answerable']['wrong']} wrong")
    print(f"  clarified on answerable questions, by reason: {s['clarified_codes_on_answerable'] or 'none'}")
    print(f"  cost/question ${s['cost_per_question_usd']:.5f} (max ${s['max_cost_usd']:.5f})   latency e2e median {s['latency_e2e_median_s']}s "
          f"p95 {s['latency_e2e_p95_s']}s   (LLM only: median {s['latency_llm_median_s']}s p95 {s['latency_llm_p95_s']}s)   "
          f"LLM failures {s['llm_failures']} (retried calls {s['llm_retried']})   flaky {s['flaky']}   prompt ~{s['tokens_in_mean']} tokens")
    print(f"  target check: {meets_target(s)}")


def variant_breakdown(results, kind_of):
    """Rates per variant kind, and per cluster (all variants of one source question count once; a cluster is wrong if any variant is)."""
    out = {}
    for kind in sorted(set(kind_of.values())):
        rs = [r for r in results if kind_of.get(r["id"]) == kind]
        n = len(rs)
        c = collections.Counter(r["outcome"] for r in rs)
        out[kind] = {"n": n, **{k: c[k] for k in ("correct", "wrong", "refused", "clarified", "error")},
                     **{f"{k}_pct": round(100 * c[k] / n, 1) for k in ("correct", "wrong", "refused", "clarified")}}
    return out


def print_variant_report(results, kind_of, source_of, baseline):
    bd = variant_breakdown(results, kind_of)
    print("\n  VARIANTS BY KIND (generated, untuned):")
    for kind, b in bd.items():
        print(f"   {kind:<11} n={b['n']:<4} correct {b['correct_pct']:>5}%  wrong {b['wrong']} ({b['wrong_pct']}%)  "
              f"refused {b['refused_pct']:>5}%  clarified {b['clarified_pct']:>5}%")
    clusters = collections.defaultdict(list)
    for r in results:
        clusters[source_of[r["id"]]].append(r["outcome"])
    wrong_clusters = sorted(k for k, v in clusters.items() if "wrong" in v)
    print(f"   clusters (one per source question): {len(clusters)}; with a wrong variant: {len(wrong_clusters)} {wrong_clusters}")
    if baseline:
        b = baseline["summary"]
        print(f"   tuned dev set, same model: correct {b['correct_pct']}%  wrong {b['wrong_pct']}%  refused {b['refused_pct']}%  clarified {b['clarified_pct']}%")
    return bd, wrong_clusters


def print_wrong(results):
    wrong = [r for r in results if r["outcome"] == "wrong"]
    print(f"\n  WRONG CASES ({len(wrong)}):")
    for r in wrong:
        print(f"   {r['id']:<6} cause={r['cause']:<28} {r['reason']}\n          Q: {r['question']!r}\n          expected: {r['expected'][:100]}\n"
              f"          got ({r['code']}, {r['metric']}): {r['answer'].replace(chr(10), ' | ')[:200]}")


def load_openai_key():
    """OPENAI_API_KEY from the environment, else from ~/.openai_api_key (the same file tests/conftest.py reads). The key is only
    ever placed in this process's environment: never printed, never written anywhere."""
    if not os.environ.get("OPENAI_API_KEY") and OPENAI_KEY_FILE.is_file():
        os.environ["OPENAI_API_KEY"] = OPENAI_KEY_FILE.read_text().strip()
    return bool(os.environ.get("OPENAI_API_KEY"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="gpt-4o-mini,gpt-4.1,claude-haiku-5-5")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--mode", default=None, choices=["json_schema", "tool"], help="OpenAI structured-output mode (default: the adapter's)")
    ap.add_argument("--pace", type=float, default=0.0, help="minimum seconds between call starts (for tokens-per-minute limits)")
    ap.add_argument("--only", default="")
    ap.add_argument("--variants", default="", help="run the generated variants in this JSON file instead of the dev questions")
    ap.add_argument("--kinds", default="typo,paraphrase,mixed")
    ap.add_argument("--baseline", default="", help="a tuned dev-run JSON of the same model, to print beside the variants")
    ap.add_argument("--drafts", action="store_true", help="run the draft cases (evals/cases_dev_drafts.py, not yet reviewed) instead of the dev set")
    ap.add_argument("--no-rebuild", action="store_true")
    ap.add_argument("--wrong", action="store_true", help="print every wrong case")
    args = ap.parse_args()

    checked_database_url()
    load_openai_key()
    cases = load_cases(include_locked=False)                    # dev only; a locked case is refused
    kind_of = source_of = None
    if args.drafts:
        from evals.cases_dev_drafts import DRAFTS
        cases = list(DRAFTS)
    if args.variants:
        from evals import variants as V
        from evals.case_specs import SPECS as _SPECS
        base = {c.id: c for c in cases}
        vs = V.load(args.variants, tuple(args.kinds.split(",")))
        cases = [dataclasses.replace(base[v["source_id"]], id=v["id"], question=v["question"], source="generated") for v in vs]
        for v in vs:
            if v["source_id"] in _SPECS:
                _SPECS[v["id"]] = _SPECS[v["source_id"]]
        kind_of = {v["id"]: v["kind"] for v in vs}
        source_of = {v["id"]: v["source_id"] for v in vs}
    if args.only:
        keep = set(args.only.split(","))
        cases = [c for c in cases if c.id in keep]
    if not args.no_rebuild:
        build_fixture.build()
    expectations = build_expectations(cases)

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = REPO / "evals" / "results"
    outdir.mkdir(exist_ok=True)
    skipped, summaries = [], {}
    for model in args.models.split(","):
        try:
            print(f"\n[{model}] running {len(cases)} cases x {args.repeats} ...", flush=True)
            results, elapsed = run_model(model, cases, expectations, args.repeats, args.workers, args.pace, args.mode)
        except Unavailable as e:
            print(f"[{model}] SKIPPED: {e}")
            skipped.append((model, str(e)))
            continue
        s = summarise(results)
        summaries[model] = s
        label = "variants-" if args.variants else ("drafts-" if args.drafts else "")
        extra = {}
        if args.variants:
            baseline = json.loads(Path(args.baseline).read_text()) if args.baseline else None
            bd, wc = print_variant_report(results, kind_of, source_of, baseline)
            extra = {"by_kind": bd, "wrong_clusters": wc, "generated": True}
        (outdir / f"v2-{label}{model}-{PROMPT_VERSION}{'-' + args.mode if args.mode else ''}-{stamp}.json").write_text(
            json.dumps({"model": model, "prompt_version": PROMPT_VERSION, "mode": args.mode or "default", "summary": s, **extra,
                        "results": results}, indent=2, default=str))
        print_report(model, s, results, elapsed)
        if args.wrong:
            print_wrong(results)
    if skipped:
        print("\nSKIPPED models (no credentials / SDK):", skipped)
    return summaries


if __name__ == "__main__":
    main()
