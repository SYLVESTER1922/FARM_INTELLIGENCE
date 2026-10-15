"""
Scoring for the eval harness. Pure functions: an `Observed` (what the engine
returned, normalised) and an `Expect` (from the oracle) go in, an outcome
comes out. No engine, database or network access here, so it is unit-testable.

Outcomes
  correct    the answer (or the refusal / clarification) was what was wanted
  wrong      a confident-but-wrong answer; `reason` says which kind
  refused    an answerable question was honestly declined (own budget)
  clarified  the bot asked a question (own budget, neither right nor wrong)
  review     a refuse-kind question got text with no figures; needs a human
  unscored   definition still pending, or no positive check possible
  error      the engine raised

Wrong reasons: wrong_number, omission, wrong_scope, raw_dump,
false_not_tracked, confident_answer_unanswerable, should_have_clarified.

Not scored in this baseline (they are v2 behaviours, not v1 ones): the echoed
scope line, the "data through" note, and the period_source label.
"""

import re
from dataclasses import dataclass

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_MONTH_YEAR = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
    r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{4}\b", re.I)
_NUMBER = re.compile(r"(?<![A-Za-z0-9])-?\d[\d,]*\.?\d*(?!\d)")
_RAW_DUMP = re.compile(r"found:\s*(true|false)|here's the data:", re.I)
_ZERO_WORDS = ("no ", "none", "nothing", "zero")


@dataclass
class Observed:
    kind: str      # answer | refusal_generic | refusal_claim | clarify | scoped_out | error
    text: str = ""


def numbers_in(text: str) -> list:
    cleaned = _MONTH_YEAR.sub(" ", _ISO_DATE.sub(" ", text))
    out = []
    for m in _NUMBER.findall(cleaned):
        s = m.replace(",", "").rstrip(".")
        try:
            out.append(float(s))
        except ValueError:
            pass
    return out


def _match(n: float, e: float, sign_agnostic: bool = False) -> bool:
    if sign_agnostic:
        n, e = abs(n), abs(e)
    return abs(n - e) <= 0.01 or n == round(e) or abs(n - round(e, 1)) < 1e-9


def _has(nums, e, sign_agnostic=False, text=""):
    if any(_match(n, e, sign_agnostic) for n in nums):
        return True
    return e == 0 and any(w in text.lower() for w in _ZERO_WORDS)


def check_answer(exp, text: str):
    """(outcome, reason) for an observed *answer* against what was expected."""
    dump = bool(_RAW_DUMP.search(text))
    outcome, reason = _check_content(exp, text)
    if outcome == "wrong":
        return outcome, reason          # the substantive failure outranks the format failure
    if dump:
        return "wrong", "raw_dump"
    return outcome, reason


def is_raw_dump(text: str) -> bool:
    return bool(_RAW_DUMP.search(text))


def _check_content(exp, text: str):
    nums = numbers_in(text)
    low = text.lower()

    for f in exp.forbidden:
        if _has(nums, f, exp.sign_agnostic) and not _has_required_equal(exp, f):
            return "wrong", "wrong_scope"
    for w in exp.forbidden_words:
        if w.lower() in low:
            return "wrong", "wrong_scope"

    positive = bool(exp.required or exp.any_of or exp.words or exp.words_any)
    if exp.required:
        missing = [e for e in exp.required if not _has(nums, e, exp.sign_agnostic, text)]
        if missing:
            return "wrong", ("wrong_number" if len(missing) == len(exp.required) else "omission")
    for group in exp.any_of:
        if not any(_has(nums, e, exp.sign_agnostic, text) for e in group):
            return "wrong", "wrong_number"
    if any(w.lower() not in low for w in exp.words):
        return "wrong", "omission"
    if exp.words_any and not any(w.lower() in low for w in exp.words_any):
        return "wrong", "omission"
    if not positive:
        return "unscored", "no_positive_check"
    return "correct", ""


def _has_required_equal(exp, f):
    """A forbidden figure that is also a required one is not a violation."""
    return any(abs(f - r) <= 0.01 for r in exp.required)


def denies_topic(text: str, topics) -> bool:
    """True if the text explicitly denies tracking one of `topics` ("does not
    track ... <topic>"), without a "but/however" in between that turns it into
    an affirmation of something else."""
    for t in topics:
        rx = (r"(?:\bnot\b|n't)\s+(?:track|record|log)(?:(?!\b(?:but|however)\b)[^.;]){0,80}" + re.escape(t))
        if re.search(rx, text, re.I):
            return True
    return False


def score(kind: str, exp, obs: Observed, topics=()):
    """kind: 'answer' | 'refuse' | 'clarify' (what the case wants). `topics`:
    words naming the data an answerable question asked about, used to tell a
    false 'we don't track X' from a misframed-but-not-false refusal."""
    if obs.kind == "error":
        return "error", obs.text[:120]

    if not exp.scored:
        if obs.kind == "answer":
            nums = numbers_in(obs.text)
            if any(_has(nums, f) for f in exp.forbidden):
                return "wrong", "wrong_scope"
        return "unscored", "pending_definition"

    if kind == "answer":
        if obs.kind == "clarify":
            return "clarified", ""
        if obs.kind in ("refusal_generic", "scoped_out"):
            return "refused", ""
        if obs.kind == "refusal_claim":
            if denies_topic(obs.text, topics):
                return "wrong", "false_not_tracked"
            return "refused", "refusal_claim_without_denial"
        return check_answer(exp, obs.text)

    if kind == "refuse":
        if obs.kind == "clarify":
            return "clarified", ""
        if obs.kind in ("refusal_generic", "refusal_claim"):
            if _false_claim(exp, obs.text):
                return "wrong", "false_not_tracked"
            return "correct", ""
        if obs.kind == "scoped_out":
            return "refused", ""
        nums = numbers_in(obs.text)
        if nums or _RAW_DUMP.search(obs.text):
            return "wrong", "confident_answer_unanswerable"
        return "review", "answer_without_figures"

    if kind == "clarify":
        if obs.kind == "clarify":
            return "correct", ""
        if obs.kind in ("refusal_generic", "refusal_claim", "scoped_out"):
            return "refused", ""
        return "wrong", "should_have_clarified"

    raise ValueError(f"unknown case kind {kind!r}")


def _false_claim(exp, text: str) -> bool:
    """A 'not tracked' claim is false only if it denies the data without
    acknowledging what IS tracked (any exempt word present clears it)."""
    low = text.lower()
    if any(w.lower() in low for w in exp.claim_exempt_words):
        return False
    return any(re.search(rx, text, re.I | re.S) for rx in exp.not_claims)


_SEVERITY = ["review", "refused", "clarified", "unscored"]


def combine(outcomes: list):
    """Combine repeats of one case: wrong if any run is wrong. Returns
    (outcome, reason, flaky)."""
    runs = [o for o, _ in outcomes]
    flaky = len(set(runs)) > 1
    for o, r in outcomes:
        if o == "wrong":
            return "wrong", r, flaky
    for o, r in outcomes:
        if o == "error":
            return "error", r, flaky
    if len(set(runs)) == 1:
        return runs[0], outcomes[0][1], False
    for sev in _SEVERITY:
        if sev in runs:
            return sev, next(r for o, r in outcomes if o == sev), True
    return runs[0], "", flaky
