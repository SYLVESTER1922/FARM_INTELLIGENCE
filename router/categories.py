"""Match the words a user used for an expense category to the farm's real categories (code, not the LLM; the LLM never sees farm data)."""

import difflib
import re


def _key(s):
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s.replace("-", " "))
    return re.sub(r"\s+", " ", s).strip()


def farm_categories(conn):
    return [r[0] for r in conn.execute("SELECT DISTINCT category FROM expenses WHERE category IS NOT NULL ORDER BY 1").fetchall()]


def match_category(text, categories):
    """The real category for the words used, or None. Exact, then containment of whole words, then a close misspelling."""
    if not text:
        return None
    want = _key(text)
    keys = {_key(c): c for c in categories}
    if want in keys:
        return keys[want]
    wanted_words = set(want.split())
    for k, original in keys.items():
        words = set(k.split())
        if words <= wanted_words or wanted_words <= words:
            return original
    close = difflib.get_close_matches(want, list(keys), n=1, cutoff=0.78)
    if close:
        return keys[close[0]]
    # a close misspelling of one word ("fertlizer") inside a longer phrase
    for k, original in keys.items():
        for w in wanted_words:
            if len(w) >= 5 and difflib.get_close_matches(w, k.split(), n=1, cutoff=0.8):
                return original
    return None
