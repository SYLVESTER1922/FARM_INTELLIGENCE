# 15: Narration overreach fix + deterministic clarification for subject-less questions

**What to build:** Two cross-cutting hardening fixes, both sourced from a
security/edge-case QA pass, neither a new tool:

1. The shared `_phrase` narration prompt (used by every tier, not just one tool) added
   an unsupported causal claim ("conditions are stable and likely not directly
   affecting feed consumption") that wasn't present in the underlying query's data.
2. Genuinely subject-less questions ("How's it doing?", "How many?") were getting a
   confidently guessed answer (weather, headcount) instead of a clarifying question -
   the same shape as this project's worst bugs.

**Blocked by:** 03 (Tier-3 core - tool-calling dispatch), for item 2

**Status:** done

**Implementation note - a real design pivot worth recording**: item 2's first
implementation attempt was an LLM-selectable `ask_for_clarification` pseudo-tool with an
explicit system prompt telling GPT-4o-mini when (and when not) to use it. Testing found
this unreliable: the model over-applied it to cases the prompt explicitly excluded (a
question ambiguous between two specific domains - "is something wrong with a batch" -
and a question genuinely out of scope - "who owns the company?"), regressing real,
previously-passing tests. Replaced with a deterministic Python check
(`chatbot/ambiguity.py`'s `has_no_real_subject`) run *before* tier-3's LLM is ever
called - zero LLM calls for this check, zero non-determinism, directly unit-testable.
This matches this project's broader preference for deterministic, testable logic over
trusting LLM judgment wherever a reliable non-LLM check exists (the same reasoning
behind tier-1's phrase-matcher and tier-0's greeting check).

A second real side effect was found and fixed while hardening item 1: the added
"don't guess a missing part" instruction initially caused the narrator to also drop
*fields that were actually present* in the data (a combined-headcount answer stopped
mentioning the individual pig/poultry counts, giving only the total) - reworded the
prompt so "mention every field present" is unambiguously dominant over "don't guess a
topic missing entirely," which are different things.

- [x] The weather narration no longer claims unsupported causation - verified with the
      exact real rambling multi-topic question from the QA pass, stable across 4
      repeated runs (a best-effort check on LLM narration, not a deterministic
      guarantee, documented honestly as such).
- [x] "How's it doing?" and "How many?" get a fixed clarifying response
      (`intent_source="needs_clarification"`), verified against real production data.
- [x] "is something wrong with a batch" (domain-ambiguous) and "who owns the company?"
      (out of scope) are both confirmed unaffected - still reach their original,
      correct handling.
- [x] The field-omission side effect is fixed and covered by a regression test
      (`test_combined_headcount_answer_includes_both_domains`).
- [x] 134 tests passing, run twice for stability given how much LLM-narration-dependent
      behavior this ticket touches - zero regressions both times.
