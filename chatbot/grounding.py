"""
A deterministic safety net on the other end of the pipeline from
chatbot/ambiguity.py: that module catches a bad *question* before an LLM
ever runs; this one catches a bad *answer* after one already has - the
narration half of "less than 5% wrong-response risk" (chatbot/tools.py's
tool-selection half is covered by tests/test_chatbot_tool_selection_eval.py
instead).

_phrase()'s prompt (chatbot/engine.py) already instructs the model never to
round, recompute, or invent a number - but a prompt instruction is not a
guarantee (the same lesson chatbot/ambiguity.py's docstring already draws
about negative instructions, applied here to numeric fidelity instead of
tool choice). This module checks the instruction actually held: every
number the narration mentions must trace back, verbatim (allowing for
comma-formatting and floating-point noise), to a number really present in
the computed data. If it doesn't, the narration is discarded in favor of a
plain, mechanically-generated sentence built directly from the data - never
pretty, but always grounded, because there is no LLM in that path to invent
anything.

Deliberately biased toward false positives over false negatives: a
legitimate number reformatted in a way this check doesn't recognize (a date
spelled out in prose instead of echoed verbatim, say) triggers the
fallback unnecessarily sometimes - a duller sentence, never a wrong one.
That asymmetry is the whole point of a safety net; the alternative
(a check lenient enough to never misfire) would also let a real fabricated
number through.
"""

import re

# A number match must not be directly glued to a letter/digit on either
# side - excludes a digit run embedded in an identifier (the "01" in
# "PIG-B01") while still matching a real number followed by punctuation, a
# unit with a space before it ("67.9 kg"), a % sign, or nothing at all.
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9])\d[\d,]*\.?\d*(?![A-Za-z0-9])")


def _walk_leaves(obj):
    """Yields every leaf VALUE, recursing through dicts (values only) and
    lists."""
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_leaves(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_leaves(v)
    else:
        yield obj


def _walk_keys_and_string_leaves(obj):
    """Every string that could legitimately appear in narration as an
    identifier, not a number: string leaf values AND dict keys. Dict keys
    matter here because several tools key a breakdown by identifier
    directly - e.g. q_batch_weight's `{"PIG-B01": 28.5}` - so a batch code
    can appear in the data only as a key, never as a value; a real bug
    found while wiring this in initially missed keys entirely, letting the
    "01" in "PIG-B01" get read as a fabricated standalone number."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                yield k
            yield from _walk_keys_and_string_leaves(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_keys_and_string_leaves(v)
    elif isinstance(obj, str):
        yield obj


def numbers_in_data(computed: list) -> set:
    """Every numeric leaf value anywhere in `computed` (nested dicts/lists
    included - e.g. a tool's per-batch or per-buyer breakdown), rounded to
    tame floating-point noise. Booleans excluded (Python's bool is an int
    subtype, but "true"/"false" narration was never a numeric claim)."""
    numbers = set()
    for leaf in _walk_leaves(computed):
        if isinstance(leaf, bool):
            continue
        if isinstance(leaf, (int, float)):
            numbers.add(round(float(leaf), 6))
    return numbers


def _string_leaves(computed: list) -> set:
    return set(_walk_keys_and_string_leaves(computed))


def _erase_known_strings(text: str, known_strings: set) -> str:
    """Blanks out every literal occurrence of a known string leaf (a batch
    code, a buyer name, an ISO date, a domain label, ...) before scanning
    for numbers - so a digit that's really part of an identifier ("PIG-B01",
    "2026-09-15") is never mistaken for a freestanding, checkable number.
    Longest strings first, so a short identifier that happens to be a
    substring of a longer one doesn't erase it only partially."""
    for s in sorted(known_strings, key=len, reverse=True):
        if s:
            text = text.replace(s, " ")
    return text


def numbers_in_text(text: str, computed: list) -> set:
    """Freestanding numeric tokens in `text`, after erasing every known
    string value from `computed` (see _erase_known_strings) so identifiers
    and dates don't get misread as bare numbers."""
    erased = _erase_known_strings(text, _string_leaves(computed))
    numbers = set()
    for match in _NUMBER_RE.findall(erased):
        cleaned = match.replace(",", "").strip(".")
        if not cleaned:
            continue
        try:
            numbers.add(round(float(cleaned), 6))
        except ValueError:
            continue
    return numbers


def is_grounded(text: str, computed: list, tolerance: float = 0.01) -> bool:
    """True only if every number the narration mentions is within
    `tolerance` of some real number in the computed data - i.e. the
    narration invented nothing numeric."""
    data_numbers = numbers_in_data(computed)
    for n in numbers_in_text(text, computed):
        if not any(abs(n - d) <= tolerance for d in data_numbers):
            return False
    return True


def fallback_narration(computed: list) -> str:
    """A plain, mechanically-generated sentence straight from the data -
    used only when is_grounded() rejects the LLM's narration. Top-level
    scalar fields only (nested breakdowns are skipped) - correctness over
    completeness in a path that should rarely trigger."""
    if not computed:
        return "No matching data was found."

    rows = []
    for row in computed:
        if not isinstance(row, dict):
            continue
        pairs = [
            f"{key.replace('_', ' ')}: {value}"
            for key, value in row.items()
            if not isinstance(value, (dict, list))
        ]
        if pairs:
            rows.append(", ".join(pairs))

    if not rows:
        return "No matching data was found."
    return "Here's the data: " + "; ".join(rows) + "."
