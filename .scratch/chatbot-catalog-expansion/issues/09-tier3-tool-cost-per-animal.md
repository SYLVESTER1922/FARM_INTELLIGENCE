# 09: Tier-3 tool - cost per animal

**What to build:** "What's the cost per pig?" and real phrasing variants resolve via a
new tier-3 tool that performs a real division (total domain expenses / current
headcount), instead of the previous behavior where `q_expenses_to_date` got matched
and the narrator claimed a calculation happened without ever dividing. Sourced from a
real bug found in a pre-deploy QA pass.

**Blocked by:** 03 (Tier-3 core - tool-calling dispatch)

**Status:** done

**Implementation note**: `domain` is a required argument (unlike the optional `domain`
on `q_headcount`/`q_expenses_to_date`) - "cost per animal" is meaningless without
knowing which animal. Validated explicitly in the function body rather than relying on
a bare `TypeError` for a missing argument, for a clearer failure mode.

- [x] "What's the cost per pig?" resolves to a real division result (verified against
      real production Supabase data: 14896.67 total piggery expenses / 12 headcount =
      1241.39 - independently cross-checked, exact match).
- [x] The division is always computed here, in Python, from two already-correct
      deterministic queries - never left for the LLM to claim it computed.
- [x] `domain` is required and validated; a missing or invalid domain fails cleanly as
      `invalid_tool_argument`, not a crash.
- [x] Module scoping applies (piggery/poultry), same static declaration rule as other
      tier-3 tools.
- [x] Tested at both seams: black-box final-answer content, direct argument-validation
      tests (missing and invalid domain), and tool-selection assertion for canonical
      phrasings including the exact real logged question.
