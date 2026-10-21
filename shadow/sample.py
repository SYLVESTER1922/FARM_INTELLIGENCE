"""query_log sampling: a reviewable sample of the questions people really asked the OLD engine, with the ones the written eval set already covers
removed, so what is left is the cases the written set missed. Every question the old engine failed on, was scoped out of or asked about is included
first; the rest of the sample is a seeded random draw of the answered ones."""

import csv
import random
import re

_MISS = ("unresolved", "needs_clarification")


def normalise(q):
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", (q or "").lower())).strip()


def written_questions():
    """Normalised text of every written dev question and generated variant."""
    from evals.cases_dev import CASES
    out = {normalise(c.question) for c in CASES}
    try:
        import json
        from evals.variants import VARIANTS_JSON
        out |= {normalise(v["question"]) for v in json.loads(VARIANTS_JSON.read_text())}
    except Exception:
        pass
    return out


def sample_query_log(conn, farm_code, n=100, seed=20261020, since=None, covered=None):
    covered = written_questions() if covered is None else covered
    rows = conn.execute(
        """SELECT question_text, intent_source, failure_reason, scoped_out_reason, COUNT(*), MIN(logged_at)
           FROM query_log WHERE farm_code = %s AND (%s::timestamptz IS NULL OR logged_at >= %s)
           GROUP BY question_text, intent_source, failure_reason, scoped_out_reason ORDER BY MIN(logged_at)""", (farm_code, since, since)).fetchall()
    seen, items = set(), []
    for q, src, fail, scoped, n_asked, first in rows:
        key = normalise(q)
        if not key or key in seen or key in covered:
            continue
        seen.add(key)
        missed = bool(fail or scoped or src in _MISS)
        items.append({"question": q, "times_asked": n_asked, "old_intent_source": src, "old_failure_reason": fail, "old_scoped_out_reason": scoped,
                      "why": "old engine did not answer" if missed else "random answered question"})
    misses = [i for i in items if i["why"].startswith("old")]
    rest = [i for i in items if not i["why"].startswith("old")]
    random.Random(seed).shuffle(rest)
    return (misses + rest)[:n]


def export_sample(items, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["question", "times_asked", "old_intent_source", "old_failure_reason", "old_scoped_out_reason", "why_sampled",
                    "what_should_it_say", "add_to_dev_set (y/n)"])
        for i in items:
            w.writerow([i["question"], i["times_asked"], i["old_intent_source"], i["old_failure_reason"] or "", i["old_scoped_out_reason"] or "", i["why"], "", ""])
    return len(items)
