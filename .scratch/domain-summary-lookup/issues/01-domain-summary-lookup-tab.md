# 01: Domain summary lookup tab

**What to build:** A new dashboard destination (matching the existing sidebar-page
pattern) where picking a domain (Piggery/Poultry/Crops) from a dropdown shows a summary
card of that domain's key metrics, without typing a chat question - mirroring Lobels'
"Material Lookup" tab. Built independently of the chatbot/tier-3 work (confirmed: not
blocked on it).

**Blocked by:** None (can start immediately) - confirmed independent of
`.scratch/chatbot-catalog-expansion/`.

**Status:** done

**Implementation note**: headcount reuses `active_headcount_asof` (the same "active as
of a date" methodology already shared by the dashboard's stat card and the chatbot's
tier-3 headcount tool) rather than `fetch_headcount_by_month`'s coarser monthly grain -
a more accurate choice for a single-domain snapshot than the ticket's original wording
implied, kept consistent with existing precedent elsewhere in this codebase. Placed as
a 9th sidebar item ("🔍 Domain Lookup"), between Reports and Settings. The domain
dropdown updates its own summary instantly on change (independent of Apply Filter,
since switching domains is lighter/more frequent than changing the date range), and is
also included in `load_all`'s orchestration so Apply Filter/Refresh Data/initial load
all keep it in sync with the current date-range filter too.

- [x] A domain dropdown (Piggery/Poultry/Crops) drives a summary card showing that
      domain's key real metrics - reusing existing `ui/queries.py` functions and
      slicing their already-domain-tagged/domain-split results (`fetch_mortality_by_month`,
      `fetch_feed_cost_by_month`, `fetch_health_summary`, `fetch_debtors`). Verified
      against real production Supabase data for all three domains, every figure
      independently cross-checked against a direct SQL query: piggery headcount 12,
      poultry headcount 509, crop area 23.0 ha, 3 plots, 1/5 active plantings, 106000 kg
      harvested, 1 outstanding debtor at $8681.12 - all exact matches.
- [x] A new, small crops-specific query was added (`fetch_crops_summary` in
      `ui/queries.py`: plantings/harvest totals - area planted, total harvested, active
      plots) since no crops-domain summary data existed anywhere in `ui/queries.py`
      before this ticket - the one real gap, not pure reuse.
- [x] Respects the existing global date-range filter, same mechanism the rest of the
      dashboard already uses (verified: piggery/poultry use the as-of-cutoff pattern,
      crops uses the range-filter pattern, matching each metric's own query shape,
      exactly as already established for tier-3's tools).
- [x] Module scoping applies: selecting a domain whose module is inactive for the farm
      shows an honest "this module is off" state, not empty/misleading data (verified
      directly against local test data).
- [x] Placed in the sidebar nav, matching this project's established layout conventions
      (108 tests passing throughout, zero regressions - this layer has no dedicated
      automated tests by established precedent for the dashboard, verified instead by
      running the real functions against real data, matching section 4's convention).
