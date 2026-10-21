"""
Generated variants of the dev questions: an UNTUNED probe (plan section 11 asks for typo, paraphrase and voice-style variants).

    python -m evals.variants generate [--model gpt-4.1]     # writes evals/variants/dev_variants.json and spot_check.csv
    python -m evals.run_v2 --variants evals/variants/dev_variants.json --models gpt-4.1 ...

Per dev question, three variants:
    typo         code only (seeded): one or two keyboard-style slips in content words; numbers, dates and batch codes untouched
    paraphrase   an LLM rewrites the question in different words, same meaning
    mixed        an LLM rewrites it as a Zimbabwean farm manager might type it, English mixed with Shona (even source ids) or Ndebele
                 (odd) words; numbers, dates and batch codes unchanged

Every variant is marked `generated: true` and inherits its source's gold answer, so it is only as good as the rewrite: a rewrite that
changes the meaning would score a correct answer as wrong. That is why 20% of them (stratified by kind, fixed seed) are written to
spot_check.csv for a person to confirm "same meaning" before any figure from this probe is quoted. The variants of one source form a
cluster and are counted as one question for any statistical claim. The generating model also sits in the routing comparison, so a
variant it wrote may be easier for it to read than a real farmer's text; the probe is optimistic by that amount.
"""

import argparse
import csv
import json
import os
import random
import re
from pathlib import Path

from evals.cases_dev import CASES

OUT_DIR = Path(__file__).resolve().parent / "variants"
VARIANTS_JSON = OUT_DIR / "dev_variants.json"
SPOT_CSV = OUT_DIR / "spot_check.csv"
SEED = 20261019
SPOT_FRACTION = 0.20
# Rewrites whose meaning drifted from the dev question (found by reading the wrong answers of the first untuned run; Sylvester's decision
# to remove them). They stay out of any regenerated set and out of the loaded one.
REMOVED = {
    "fc06-pa": "'spend feeding the chickens' became 'pay for chicken feed' (feed eaten became feed bought)",
    "fp03-pa": "'spend buying feed for the pigs' became 'total expenditure on pig feed' (lost the word buying; reads as eaten or bought)",
    "pf06-mx": "'net income' became 'our income' in Ndebele (net became gross)",
}
KINDS = ("typo", "paraphrase", "mixed")
SUFFIX = {"typo": "ty", "paraphrase": "pa", "mixed": "mx"}
OPENAI_KEY_FILE = Path.home() / ".openai_api_key"

_KEEP = re.compile(r"^(?:[A-Za-z]{2,4}-[A-Za-z]?\d{2,3}|\d.*)$")           # batch codes and anything starting with a digit
_NEIGHBOURS = {"a": "s", "e": "r", "i": "o", "o": "p", "u": "i", "n": "m", "m": "n", "t": "r", "r": "t", "s": "a", "l": "k", "d": "s"}


def typo(question: str, rng: random.Random) -> str:
    """One or two slips (swap, drop, double, neighbouring key) in different content words of 5+ letters."""
    words = list(re.finditer(r"[A-Za-z][A-Za-z'-]*", question))
    cands = [w for w in words if len(w.group()) >= 5 and not _KEEP.match(w.group())]
    if not cands:
        cands = [w for w in words if len(w.group()) >= 4 and not _KEEP.match(w.group())]
    if not cands:
        return question.lower()
    picks = rng.sample(cands, k=min(len(cands), 2 if len(question) > 35 else 1))
    out = question
    for w in sorted(picks, key=lambda m: -m.start()):
        t = w.group()
        i = rng.randrange(1, len(t) - 1)
        op = rng.choice(("swap", "drop", "double", "key"))
        if op == "swap":
            new = t[:i] + t[i + 1] + t[i] + t[i + 2:]
        elif op == "drop":
            new = t[:i] + t[i + 1:]
        elif op == "double":
            new = t[:i] + t[i] + t[i:]
        else:
            new = t[:i] + _NEIGHBOURS.get(t[i].lower(), t[i]) + t[i + 1:]
        if new == t:
            new = t[:i] + t[i + 1:]
        out = out[:w.start()] + new + out[w.end():]
    return out


PROMPTS = {
    "paraphrase": ("Rewrite this farm-management question in different words, keeping exactly the same meaning and the same scope. Keep any "
                   "number, date, month, year, batch code and name exactly as written. Do not answer it, do not add or drop anything. "
                   "Reply with the rewritten question only."),
    "mixed": ("Rewrite this farm-management question the way a farm manager in Zimbabwe might type it on a phone: English with a few "
              "{lang} words mixed in. Use ONLY words from this glossary for the {lang} words, and only where they fit; every other word "
              "stays English, so the meaning cannot drift.\n{glossary}\n"
              "Keep exactly the same meaning and scope. Keep any number, date, month, year, batch code and name exactly as written. "
              "Do not answer it. Reply with the rewritten question only."),
}


GLOSSARY = {
    "Shona": "pigs = nguruve; chickens/birds = huku; money = mari; how much money = marii; how many = mangani; feed (food) = chikafu; "
             "farm = purazi; died = dzakafa; please = ndapota; do we have = tine here; what about = zvakadii",
    "Ndebele": "pigs = izingulube; chickens/birds = inkukhu; money = imali; how much = malini; how many = zingaki; feed (food) = ukudla; "
               "farm = ifama; died = zafa; please = ngiyacela; do we have = sinayo yini",
}


def _client():
    import openai
    if not os.environ.get("OPENAI_API_KEY") and OPENAI_KEY_FILE.is_file():
        os.environ["OPENAI_API_KEY"] = OPENAI_KEY_FILE.read_text().strip()
    return openai.OpenAI(timeout=30, max_retries=3)


def _rewrite(client, model, kind, question, lang):
    system = PROMPTS[kind].format(lang=lang, glossary=f"Glossary ({lang}): {GLOSSARY.get(lang, '')}") if kind == "mixed" else PROMPTS[kind]
    r = client.chat.completions.create(model=model, temperature=0.3, max_tokens=120,
                                       messages=[{"role": "system", "content": system}, {"role": "user", "content": question}])
    return r.choices[0].message.content.strip().strip('"')


def generate(model="gpt-4.1", workers=4):
    import concurrent.futures as cf
    rng = random.Random(SEED)
    client = _client()
    jobs = []
    for n, c in enumerate(CASES):
        lang = "Shona" if n % 2 == 0 else "Ndebele"
        jobs.append((c, "typo", None))
        jobs.append((c, "paraphrase", None))
        jobs.append((c, "mixed", lang))
    typos = {c.id: typo(c.question, random.Random(f"{SEED}-{c.id}")) for c in CASES}

    def one(job):
        c, kind, lang = job
        if kind == "typo":
            return c, kind, typos[c.id], "code", None
        return c, kind, _rewrite(client, model, kind, c.question, lang), model, lang

    with cf.ThreadPoolExecutor(workers) as pool:
        done = list(pool.map(one, jobs))
    variants = [{"id": f"{c.id}-{SUFFIX[kind]}", "source_id": c.id, "kind": kind, "question": text, "source_question": c.question,
                 "generated": True, "generator": gen, "language": lang, "seed": SEED}
                for c, kind, text, gen, lang in done]
    # Drop a rewrite that is empty, unchanged, or the model answering/refusing instead of rewriting (e.g. for the prompt-injection case).
    refusal = re.compile(r"^\s*(sorry|i'?m sorry|i can'?t|i cannot|i am unable|as an ai)", re.I)
    variants = [v for v in variants if v["question"] and v["question"] != v["source_question"] and not refusal.match(v["question"])
                and v["id"] not in REMOVED]
    OUT_DIR.mkdir(exist_ok=True)
    VARIANTS_JSON.write_text(json.dumps(variants, indent=1, ensure_ascii=False))
    spot = spot_check_sample(variants)
    with open(SPOT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "source_id", "kind", "language", "source_question", "variant_question", "same_meaning (y/n)", "natural_wording (y/n)", "notes"])
        for v in spot:
            w.writerow([v["id"], v["source_id"], v["kind"], v["language"] or "", v["source_question"], v["question"], "", "", ""])
    return variants, spot


def spot_check_sample(variants, fraction=SPOT_FRACTION, seed=SEED):
    """20% of the variants, stratified by kind, in a fixed order (the same sample every time for the same variants file)."""
    rng = random.Random(seed)
    out = []
    for kind in KINDS:
        group = sorted((v for v in variants if v["kind"] == kind), key=lambda v: v["id"])
        out += rng.sample(group, k=max(1, round(len(group) * fraction))) if group else []
    return sorted(out, key=lambda v: (v["kind"], v["id"]))


def load(path=VARIANTS_JSON, kinds=KINDS):
    return [v for v in json.loads(Path(path).read_text()) if v["kind"] in kinds and v["id"] not in REMOVED]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["generate"])
    ap.add_argument("--model", default="gpt-4.1")
    a = ap.parse_args()
    v, s = generate(a.model)
    print(f"{len(v)} variants written to {VARIANTS_JSON}; {len(s)} in {SPOT_CSV} for human spot-check")
