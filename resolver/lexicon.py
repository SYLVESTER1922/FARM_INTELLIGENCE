"""
Domain words, farm vocabulary to domain. Used two ways (plan sections 5 and 6): to read the domain a question names, and
as a cross-check on the LLM's spec later, so a domain word the spec missed ("pigs") can never silently fall through to
"all domains". Pure: no LLM, no database.
"""

import difflib
import re

DOMAIN_WORDS = {
    "piggery": {"pig", "pigs", "piglet", "piglets", "piggery", "swine", "sow", "sows", "boar", "boars", "hog", "hogs",
                "pork", "porker", "porkers", "weaner", "weaners", "farrow", "farrowing", "litter", "litters",
                # Shona and Ndebele (added after the variants probe; to be confirmed by a Shona/Ndebele speaker)
                "nguruve", "dzenguruve", "ingulube", "izingulube"},
    "poultry": {"chicken", "chickens", "chick", "chicks", "poultry", "bird", "birds", "broiler", "broilers", "layer",
                "layers", "hen", "hens", "fowl", "egg", "eggs",
                "huku", "inkukhu", "izinkukhu"},
    "crops": {"crop", "crops", "maize", "soya", "soyabean", "soyabeans", "soybean", "soybeans", "groundnut", "groundnuts",
              "tomato", "tomatoes", "harvest", "harvests", "harvested", "plot", "plots", "hectare", "hectares", "planted",
              "planting", "plantings", "chibage", "ummbila", "madomasi"},
    "shared": {"shared", "unallocated", "overhead", "overheads"},
}
WORD_TO_DOMAIN = {w: d for d, ws in DOMAIN_WORDS.items() for w in ws}
_FUZZY_CANDIDATES = [w for w in WORD_TO_DOMAIN if len(w) >= 5]

# A batch code looks like PIG-B04 or BRO-P03. Masked out before reading domain words: the "PIG" in a code is not
# the word "pigs".
BATCH_CODE_RE = re.compile(r"\b[a-z]{2,4}-[a-z]?\d{2,3}\b", re.I)

# Roots that stay recognisable under a prefix (ne-, ye-, dze-, ku-, ...). Confirmed by a Shona/Ndebele speaker before this is relied on.
_BANTU_ROOTS = {"nguruve": "piggery", "huku": "poultry", "ingulube": "piggery", "inkukhu": "poultry"}

_NOT_A_DOMAIN = {"plotted", "plotting", "layered", "chickpea", "chickpeas"}


def find_batch_code(text: str):
    m = BATCH_CODE_RE.search(text)
    return m.group(0).upper() if m else None


def domain_words_in(text: str):
    """(domains, words): the domains a question names, in a stable order, and the words that named them. A close
    misspelling of a longer farm word ("pigss", "chikens") counts; a short word must match exactly."""
    t = BATCH_CODE_RE.sub(" ", text.lower())
    tokens = re.findall(r"[a-z]+", t)
    found, words = set(), []
    for tok in tokens:
        if tok in _NOT_A_DOMAIN:
            continue
        domain = WORD_TO_DOMAIN.get(tok)
        if domain is None:                                   # Shona and Ndebele attach prefixes: "nehuku" = "and chickens"
            domain = next((d for root, d in _BANTU_ROOTS.items() if tok.endswith(root) and len(tok) - len(root) <= 4), None)
        if domain is None and len(tok) >= 5:
            close = difflib.get_close_matches(tok, _FUZZY_CANDIDATES, n=1, cutoff=0.85)
            domain = WORD_TO_DOMAIN[close[0]] if close else None
        if domain is None and len(tok) == 5 and tok.endswith("s") and tok[:-1] in WORD_TO_DOMAIN:
            domain = WORD_TO_DOMAIN[tok[:-1]]
        if domain:
            found.add(domain)
            words.append(tok)
    order = ("piggery", "poultry", "crops", "shared")
    return tuple(d for d in order if d in found), tuple(words)
