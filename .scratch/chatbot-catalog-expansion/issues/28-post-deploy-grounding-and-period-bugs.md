# 28: Post-deploy bug fixes - grounding check false positives and feed_cost_split's relative period

**What to build:** fix three real, independently-confirmed production bugs surfaced by a
real chat transcript, reported and root-caused before any fix was attempted (per the
user's explicit instruction).

**Blocked by:** 24 (tool-selection accuracy eval), 25 (narration-grounding check)

**Status:** done

**Root causes, all confirmed by direct reproduction against production data before
fixing, not assumed:**

1. **Grounding check couldn't handle negative numbers.** `chatbot/grounding.py`'s number
   regex stripped a leading "-", so a real loss (e.g. `q_profit`'s `-5563.5`) never
   matched its own value in the data, wrongly discarding a correct narration into the
   raw-dump fallback. Fixed: the regex now optionally captures a leading "-", with the
   lookbehind still checked *before* that sign so a hyphenated identifier suffix
   ("PL2-25A") still correctly fails to match.
2. **Grounding check didn't recognize `decimal.Decimal`.** Tier-1 catalog queries
   (`feed_cost_split`, `crop_debtor`, etc.) return raw `Decimal` columns straight from
   psycopg, unlike tier-3 tools which explicitly `float()`-cast everything -
   `numbers_in_data` only checked `(int, float)`, so it came back empty for *any*
   tier-1 catalog answer with a numeric field, meaning every number the narration then
   mentioned was flagged "ungrounded" and fell back unconditionally. This was systemic,
   not a one-off - it affected every tier-1 catalog query with a number, not just the
   one reported question. Fixed: `numbers_in_data` now also accepts `decimal.Decimal`.
3. **Grounding check misread a reformatted date as a fabricated number - the single
   most frequently-triggered false positive, found via repeated real trials (~1 in 5-6),
   not a rare edge case.** A known ISO date value ("2026-06-17") reformatted by the LLM
   as prose ("June 17, 2026") never matched the literal-substring erasure, so its digits
   leaked through as apparently-invented numbers. Fixed with
   `_erase_reformatted_known_dates`: detects a Month-DD-YYYY or DD-Month-YYYY span,
   converts it to ISO, and erases it only if it matches a real known date from the data
   - never a blanket "date-shaped numbers are always fine" allowance, which would also
   wave through a genuinely fabricated number that happens to coincide with a
   day-of-month or a year. Verified: 15/15 real trials of the same question that
   previously failed ~1-in-6 now pass with zero fallbacks.
4. **`feed_cost_split`'s relative period extraction was unreliable and unrelated to
   today's other three bugs - pre-existing, not introduced this session.** Tier-2's
   LLM-extraction prompt asked the model to freely state a "period" as a bare Month/Year
   string with no anchor to real data; for "this month" it produced "October 2023" - its
   own training-era guess at "now" - which then passed straight through
   `extract_period`'s Month-Year regex as if it were a real, explicit date, querying a
   period with no real rows and correctly (but unhelpfully) narrating "no data
   available." Fixed with `chatbot/matcher.py`'s new `extract_relative_period` /
   `mentions_relative_period` - the same "the LLM never computes a relative date itself"
   principle already applied to `q_mortality_rate`'s symbolic period enum, extended to
   tier-1/2's free-text period parameter. The real anchor date (`latest_daily_log_date`,
   relocated from `chatbot/tools.py`'s private `_latest_headcount_date` to
   `chatbot/catalog.py` so both share one source of truth) is looked up only when a
   question mentions "this month"/"last month" at all, and the lookup itself is wrapped
   defensively (`except psycopg.errors.UndefinedTable: pass`) since real production
   always has `pig_daily_log`/`poultry_daily_log` but a minimal test fixture for an
   unrelated tool might not - a real regression (47 test failures) was caught and fixed
   during this same ticket's own verification, from an earlier, unconditional version of
   this lookup.

**Two items from the original report investigated and found NOT to be bugs, verified
against real data rather than assumed:**
- Headcount = 12 is correct: 3 of 4 pig batches (`PIG-B01/02/03`) are already
  `status='Sold'` and correctly excluded from "active as of today" (their daily logs
  stopped months ago); only `PIG-B04` (12 head) is still active.
- The hen-day lay-rate refusal is correct and honest, not a gap: this farm's poultry
  batches are all `bird_type='Broiler'`, and `eggs_collected/cracked/dirty` sum to zero
  across every logged row - there are no layers and no real egg data on this farm. (The
  claim that this was "one of the 19 tools that passed 50/50 in ticket 24" was mistaken -
  no lay-rate tool was ever built.)

**Explicitly NOT fixed here, correctly deferred to existing open tickets**: the profit
question ("which enterprise made the most profit") still only compares within one
domain (`q_profit` called with `domain="piggery"` instead of a real cross-domain
comparison) - that is ticket 27's exact concern (right tool family, wrong argument for
what was actually asked), not a grounding or period-resolution bug.

- [x] All three grounding-check bugs fixed and unit-tested directly
      (`tests/test_chatbot_grounding.py`), each reproducing the real failure shape
      before fixing (a real negative number, a real Decimal value, a real reformatted
      date).
- [x] `feed_cost_split`'s relative-period bug fixed and tested at three levels: pure
      unit tests for `extract_relative_period`/`extract_period`
      (`tests/test_chatbot_matcher_period.py`), `validate_llm_intent`'s bypass behavior
      (`tests/test_chatbot_fallback_validation.py`), and a full black-box
      `answer_question` integration test proving "this month" resolves to the same real
      period an explicit "January 2026" phrasing already does
      (`tests/test_chatbot_engine.py`).
- [x] The `anchor_date`-lookup regression (47 test failures from an unconditional,
      undefended query) caught and fixed within this same ticket, before it ever reached
      a commit.
- [x] 195 tests passing (up from 176), run twice for stability - zero regressions.
- [x] Re-verified against real production data: the exact 6 originally-reported
      questions plus a broader 16-question sweep, zero fallback-format answers across
      all of them; the "this month"/"last month" period fix independently verified with
      real, distinct real figures for each period.
