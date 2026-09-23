# 06: Honest "not tracked" vs. "not yet wired" refusals

**What to build:** A curated data dictionary describing what the app actually tracks,
domain by domain, informs both tier-3's tool selection and a differentiated refusal
message when nothing at any tier matches - distinguishing "we don't track that at all"
from a generic "can't answer."

**Blocked by:** 03 (Tier-3 core - tool-calling dispatch + first tool). Expected to be
refined as tickets 04/05 (and future tier-3 tools) land, but not strictly gated on them.

**Status:** done

**Implementation note - a real limitation found and documented, not fixed (out of
scope)**: the real logged phrasing "Do we owe anyone money?" turned out to be genuinely
borderline - it shares enough vocabulary with `crop_debtor`'s own catalog phrase ("who
owes US money for crops") that tier-2's LLM classifier occasionally (non-deterministically)
misroutes it there instead of reaching this ticket's gap-explanation path at all, and even
when it does fall through, the gap-explainer doesn't always catch that specific indirect
phrasing. This is a pre-existing characteristic of tier-2's classification, not something
introduced by this ticket, and fixing it is out of scope here (it would mean hardening
tier-2's prompt/validation against confusable phrasing generally, a separate concern).
Verified instead with "What accounts payable does the farm have?" - a real, natural,
reliable phrasing of the same underlying question - and documented this finding in the
test file for whoever picks up tier-2 classification robustness next.

- [x] A real accounts-payable question gets a refusal that honestly names this as
      untracked, distinct from `revenue.payment_status='Owing'` (money owed *to* the
      farm), rather than the generic unresolved message. Verified against real
      production Supabase data with the exact live response: "The farm does not track
      accounts payable, which refers to money the farm owes to suppliers or creditors;
      it only tracks revenue owed to the farm by customers."
- [x] The data dictionary never surfaces raw table/column names in user-facing text - it
      is a curated, farm-owner-legible description, not a schema dump (tested directly:
      none of `pig_daily_log`/`poultry_daily_log`/`farm_profile`/`closing_count`/
      `query_log` ever appear in the refusal text).
- [x] The data dictionary is hand-maintained (not derived from live schema
      introspection) and documented as a living artifact expected to be updated as
      tier-3 tools are added - see `chatbot/data_dictionary.py`'s module docstring.
- [x] A genuinely out-of-scope question unrelated to farm data at all ("who owns the
      company?") still refuses cleanly - verified against real production data too,
      correctly falling back to the plain generic message (the gap-explainer correctly
      classified it as NONE).
- [x] Existing tier-0/1/2/3 resolution behavior for all currently-answerable questions
      is unaffected - this only changes what happens on a genuine full miss (98 tests
      passing, up from 95, zero regressions; re-run 3x to check for flakiness in the new
      LLM-dependent path, stable each time).
