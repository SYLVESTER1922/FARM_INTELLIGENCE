# 01: Domain summary lookup tab

**What to build:** A new dashboard destination (matching the existing sidebar-page
pattern) where picking a domain (Piggery/Poultry/Crops) from a dropdown shows a summary
card of that domain's key metrics, without typing a chat question - mirroring Lobels'
"Material Lookup" tab. Built independently of the chatbot/tier-3 work (confirmed: not
blocked on it).

**Blocked by:** None (can start immediately) - confirmed independent of
`.scratch/chatbot-catalog-expansion/`.

**Status:** ready-for-agent

- [ ] A domain dropdown (Piggery/Poultry/Crops) drives a summary card showing that
      domain's key real metrics - reusing existing `ui/queries.py` functions and
      slicing their already-domain-tagged/domain-split results (`fetch_mortality_by_month`,
      `fetch_headcount_by_month`, `fetch_feed_cost_by_month` already return
      `{"piggery": [...], "poultry": [...]}`; `fetch_health_summary`,
      `fetch_recent_health_events`, and `fetch_debtors` already carry a `domain` column).
- [ ] A new, small crops-specific query is added (plantings/harvest totals - area
      planted, total harvested, active plots) since no crops-domain summary data is
      currently exposed anywhere in `ui/queries.py` - this is the one real gap, not pure
      reuse.
- [ ] Respects the existing global date-range filter, same mechanism the rest of the
      dashboard already uses.
- [ ] Module scoping applies: selecting a domain whose module is inactive for the farm
      shows an honest "this module is off" state, not empty/misleading data.
- [ ] Placed in the sidebar nav or folded into an existing page, matching this project's
      established layout conventions - a judgment call to make while implementing, not a
      new design decision requiring further grilling.
