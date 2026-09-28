# 25: Narration-grounding check

**What to build:** a deterministic safety net on the narration half of the user's
accuracy/hallucination request (ticket 24 covers the tool-selection half). After
`_phrase()` narrates a tool's or catalog query's computed data, verify every number the
narration mentions traces back to a real number in that data - if not, discard the
narration and use a plain, mechanically-generated sentence built directly from the data
instead.

**Blocked by:** 03 (Tier-3 core - tool-calling dispatch), 24 (tool-selection eval)

**Status:** done

**Implementation note**: `chatbot/grounding.py` walks `computed` (the same list-of-dicts
`_phrase()` already receives) for every numeric leaf value, and separately for every
string leaf value *and* dict key (batch codes, buyer names, ISO dates, domain labels).
Before scanning the narration text for numbers, every known string is erased from it -
so a digit embedded in an identifier ("PIG-B01", "2026-09-15") is never misread as a
freestanding, checkable number. A real bug was found and fixed while wiring this in:
the first version only erased string *values*, not dict *keys* - several tools
(`q_batch_weight`, `q_fcr_ranking`) key a per-batch breakdown by batch code directly
(`{"PIG-B01": 28.5}`), so the code only ever appeared as a key, never a value, and its
embedded "01" got read as a fabricated number, wrongly triggering the fallback on a
correct answer. Caught by the full test suite (not the eval - a different, direct
regression), fixed by also walking dict keys, plus a stricter number regex (a match
must not be directly adjacent to a letter or digit) as defense in depth.

Deliberately biased toward false positives over false negatives: a legitimate number
reformatted in a way the check doesn't recognize (a date spelled out in prose, say)
would trigger the fallback unnecessarily rather than let a genuinely fabricated number
through - the fallback is duller, never wrong.

- [x] `is_grounded`/`numbers_in_data`/`numbers_in_text`/`fallback_narration` unit-tested
      directly and deterministically (no LLM calls) - nested dicts/lists, booleans
      excluded, comma-formatted numbers, digits embedded in known identifiers (both as
      values and as dict keys).
- [x] Integration-tested by injecting a fabricated wrong number at the exact seam
      `_phrase()` calls (a monkeypatched OpenAI client, the same
      inject-a-failure-at-the-boundary pattern `tests/test_ui_app.py` already uses) -
      verifies the real `_run_tool_call` -> `_phrase()` path falls back correctly, and a
      second test verifies a genuinely correct narration passes through unchanged.
- [x] Verified against 12 real production questions across a range of tools (nested
      per-batch breakdowns, buyer names with spaces, dates, percentages, decimals) -
      zero false positives, every real answer passed through unmodified.
- [x] 176 tests passing (up from 163 - ticket 24's 50-case eval plus this ticket's 12 new
      unit/integration tests), run twice for stability - zero regressions either time
      after the dict-key fix.
