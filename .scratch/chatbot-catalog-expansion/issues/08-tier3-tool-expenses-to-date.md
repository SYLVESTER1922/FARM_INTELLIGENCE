# 08: Tier-3 tool - cumulative expenses to date

**What to build:** "What's the expense amount to date?" and real phrasing variants
resolve via a new tier-3 tool giving cumulative total expenses up to a cutoff date -
matching the dashboard's existing cumulative stat-card treatment (Total Livestock
Placed, Piglets Born), not a `date_from`-bounded range. Sourced from a real logged
failure surfaced by live production usage right after tickets 01-06 shipped.

**Blocked by:** 03 (Tier-3 core - tool-calling dispatch)

**Status:** done

- [x] "What's the expense amount to date?" resolves to a real, correct cumulative total
      from `expenses`, "as of" the selected date filter's end date (or the latest real
      expense date if none given). Verified against real production Supabase data
      (independently cross-checked: 30380.06 as of 2026-09-14, matching the real
      underlying data exactly).
- [x] Supports an optional domain filter (piggery/poultry/crops), validated against the
      closed vocabulary before querying, matching the argument-validation pattern
      ticket 03 established (tested directly, both the validation function and the full
      dispatch path).
- [x] Module scoping applies statically across all three domains (expenses can touch
      any of them) - same rule ticket 03 settled, regardless of which domain (if any)
      the question or a filter argument actually narrows to.
- [x] `query_log` records the tool name + arguments for this tool's hits.
- [x] Tested at both seams: black-box final-answer content (3 tests) plus two argument-
      validation tests, and direct tool-selection assertion for canonical phrasings
      including the exact real logged question.
- [x] No changes required to tier-3's core dispatch mechanism itself (108 tests passing,
      up from 98, zero regressions).
