# 02: Targeted clarifying response for missing_parameter

**What to build:** When tier-1 or tier-2 determines a question matches a known query
type but is missing a required detail (e.g. `feed_cost_split` without a month), the
chatbot responds with a message naming specifically what's missing, instead of the
generic unresolved template - and this result does not fall through to any further
tier.

**Blocked by:** None (can start immediately)

**Status:** done

**Implementation note**: `matcher.py`'s `MatchResult` deliberately doesn't carry which
catalog entry or which specific parameter was missing (by original design). Since
`required_params` has exactly one type in the whole catalog today ("period", used only
by `feed_cost_split`), the clarifying message is worded specifically for a month/year
rather than built as a generic per-parameter-type templating system - documented in
`chatbot/engine.py` as a deliberate simplification that needs revisiting if a second
required-parameter type is ever added.

- [x] A `missing_parameter` result produces a response distinct from the generic
      unresolved wording, naming the specific missing detail (which month/year).
- [x] This applies whether `missing_parameter` was determined by tier-1's deterministic
      matcher or tier-2's LLM-validated fallback (the check happens after both tiers
      have run, on the final result).
- [x] A `missing_parameter` result is final for that question - it is not passed to any
      further resolution attempt (tier-3 doesn't exist yet as of this ticket; ticket 03
      must preserve this ordering).
- [x] Verified against the real logged failure: "How does feed cost split between pigs
      and chickens?" (no month given) now gets the targeted clarifying response, not the
      generic message.
- [x] `no_match`, `ambiguous`, `scoped_out`, and successfully-resolved questions are all
      unaffected - only `missing_parameter`'s response text and terminal handling
      changes (76 tests passing, no regressions).
