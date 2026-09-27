"""
A deterministic check for whether a question has any real content word at
all - checked before tier-3's LLM tool-calling is ever attempted.

Real bug found via a QA pass: "How's it doing?" and "How many?" (bare
pronoun/quantifier questions with no subject, domain, or metric named at
all) got a confidently guessed answer (weather, headcount) instead of a
clarifying question - the same shape as this project's worst bugs
(a confident answer on ambiguous input).

The first fix attempt tried an LLM-selectable "ask_for_clarification"
pseudo-tool with an explicit system prompt telling GPT-4o-mini when (and
when not) to use it. That was found unreliable in testing: the model
over-applied it to cases explicitly excluded in the prompt (a question
ambiguous between two specific domains, and a question genuinely out of
scope), regressing real, previously-passing behavior. Matching this
project's broader preference for deterministic, testable logic over
trusting LLM judgment wherever a reliable non-LLM check exists (the same
reasoning behind tier-1's phrase-matcher and tier-0's greeting check),
this is a plain Python check instead - zero LLM calls, zero
non-determinism, and directly testable.

The check itself is deliberately narrow: it only catches questions with
NO real content word anywhere (after stripping a small, curated set of
question-words/pronouns/auxiliary verbs) - not general domain ambiguity
("is something wrong with a batch" - has "batch") and not out-of-scope
questions ("who owns the company?" - has "company"), both of which
correctly continue past this check into tier-3's normal tool-calling (and
from there, decline normally if nothing real applies).
"""

import re

_STOPWORDS = {
    "how", "what", "why", "when", "where", "who", "which",
    "is", "are", "was", "were", "do", "does", "did", "doing", "done",
    "it", "its", "this", "that", "these", "those",
    "the", "a", "an", "to", "of", "for", "with", "on", "in", "at", "about",
    "many", "much", "any", "some", "we", "us", "our", "you", "your",
    "have", "has", "had", "going", "happening", "like", "and", "s",
}


def has_no_real_subject(question: str) -> bool:
    """True only for a question with no content word at all once question-
    words/pronouns/auxiliary verbs are stripped - a bare "how's it doing"
    or "how many", not a question that names any real (even ambiguous or
    out-of-scope) subject."""
    tokens = set(re.findall(r"[a-z0-9]+", question.lower()))
    return not (tokens - _STOPWORDS)
