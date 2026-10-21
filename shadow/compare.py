"""How the old and new engine's answers to one question relate. The old engine returns prose, so figures are compared by the numbers in the text; a
person labels anything this cannot settle. Pure functions, no database."""

import re

_DATE = re.compile(r"\b\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4}\b|\b\d{4}-\d{2}-\d{2}\b")
_BATCH = re.compile(r"\b[A-Za-z]{2,4}-[A-Za-z]?\d{1,3}\b")
_YEAR = re.compile(r"\b20\d{2}\b")
_NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")

# What the old engine's intent_source and reasons mean, as an outcome.
_OLD_ANSWERS = {"deterministic", "llm_fallback", "tool_fallback", "tier0_greeting", "tier0_help"}

NEEDS_LABEL = {"disagree", "new_asks", "new_refuses", "old_misses", "unclear", "new_error"}
CLASSES = ("agree", "disagree", "new_asks", "new_refuses", "old_misses", "both_decline", "unclear", "new_error")


def old_outcome(old):
    """(kind, reason) for an old-engine Answer: kind is answer | clarify | refuse."""
    src = getattr(old, "intent_source", None)
    if getattr(old, "scoped_out_reason", None) or getattr(old, "failure_reason", None) or src == "unresolved":
        return "refuse", getattr(old, "scoped_out_reason", None) or getattr(old, "failure_reason", None) or src
    if src == "needs_clarification":
        return "clarify", src
    return "answer", src


def numbers(text):
    """The figures in an answer: dates, batch codes and the 'Data through' line removed, commas and signs normalised, rounded to the cent."""
    t = _YEAR.sub(" ", _BATCH.sub(" ", _DATE.sub(" ", text or "")))
    out = set()
    for m in _NUMBER.findall(t):
        try:
            out.add(round(abs(float(m.replace(",", ""))), 2))
        except ValueError:
            pass
    return out


def classify(old_kind, old_text, new_kind, new_text, new_error=None):
    """One of CLASSES. new_kind is answer | clarify | refusal | error."""
    if new_kind == "error":
        return "new_error"
    new_declines = new_kind in ("clarify", "refusal")
    if old_kind == "answer":
        if new_kind == "clarify":
            return "new_asks"
        if new_kind == "refusal":
            return "new_refuses"
        a, b = numbers(old_text), numbers(new_text)
        if not a or not b:
            return "unclear"
        if a <= b or b <= a:
            return "agree"
        return "disagree"
    # the old engine declined or asked
    return "both_decline" if new_declines else "old_misses"


def needs_label(classification):
    return classification in NEEDS_LABEL
