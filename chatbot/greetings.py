"""
Tier-0: bare greetings and "what can you ask" questions, checked before tier-1's
real catalog matching runs. Exact normalized-token-set matching against a small,
curated list - not the fuzzy recall-based scoring tier-1 uses for its longer,
descriptive catalog phrases, because that scoring is recall-only (overlap divided
by phrase length) and would happily "match" a short phrase like "hi" against any
longer question that merely contains the word "hi" somewhere in it. A real
question ("hi, how many pigs do we have") must never be hijacked into a canned
greeting response, so tier-0 requires the whole question to reduce to one of the
known phrases, not just overlap with one.
"""

import re

GREETING_RESPONSE = (
    "Hi! Ask me about your farm's piggery, poultry, or crops data - for example, "
    "\"is there a disease outbreak in the piggery?\" or \"who owes us money for "
    "crops?\"."
)

HELP_RESPONSE = (
    "I can answer questions about your farm's piggery, poultry, and crops data - "
    "things like mortality and disease outbreaks, feed cost splits, and who owes "
    "you money. Try asking something like \"how does feed cost split between pigs "
    "and chickens in <month> <year>?\" or \"is there a disease outbreak in the "
    "piggery?\"."
)

_GREETING_PHRASES = [
    "hi", "hello", "hey", "hie", "yo",
    "hi there", "hello there", "hey there",
    "good morning", "good afternoon", "good evening",
]

_HELP_PHRASES = [
    "what can you ask", "what can i ask you", "what can i ask",
    "what questions can i ask", "what do you do", "help",
    "how does this work", "what are you able to answer",
]


def _normalize_tokens(text: str) -> frozenset:
    return frozenset(re.findall(r"[a-z0-9]+", text.lower()))


_GREETING_TOKEN_SETS = {_normalize_tokens(p) for p in _GREETING_PHRASES}
_HELP_TOKEN_SETS = {_normalize_tokens(p) for p in _HELP_PHRASES}


def match_tier0(question: str) -> str | None:
    """Returns "greeting", "help", or None. Only matches when the ENTIRE question
    (once normalized) equals a known phrase - a real data question that merely
    contains a greeting word is never matched."""
    tokens = _normalize_tokens(question)
    if not tokens:
        return None
    if tokens in _GREETING_TOKEN_SETS:
        return "greeting"
    if tokens in _HELP_TOKEN_SETS:
        return "help"
    return None
