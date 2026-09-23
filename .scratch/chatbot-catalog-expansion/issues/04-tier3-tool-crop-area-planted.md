# 04: Tier-3 tool - crop area planted

**What to build:** "How many hectares of crop is planted?" and real phrasing variants
resolve via a new tier-3 tool, reusing ticket 03's dispatch, argument-validation,
module-scoping, date-filter, and query-log infrastructure.

**Blocked by:** 03 (Tier-3 core - tool-calling dispatch + first tool)

**Status:** done

**Implementation note**: unlike ticket 03's headcount tool (a point-in-time snapshot),
crop area planted is a genuine range aggregate, so it uses the same `{date_filter}`/
`date_filter_sql` mechanism tiers 1-2 already use (filtered by `planting_date`), not
headcount's as-of-cutoff approach. This required extending `_run_tool_call`'s dispatch
to pass both `date_from` and `date_to` to every tier-3 tool uniformly (headcount simply
ignores `date_from`, documented in its own docstring) - a small, backward-compatible
change to ticket 03's infrastructure, not a new mechanism.

- [x] The real logged question "How many hectres of crop is planted?" (and the corrected
      spelling) resolves to a real, correct total planted-area figure. Verified against
      real production Supabase data (independently cross-checked: 23.0 hectares,
      matching the real underlying data exactly).
- [x] Module scoping applies: if crops is turned off for the farm, this is scoped out
      via the same mechanism as ticket 03's tool.
- [x] Respects the global date-range filter (by planting date) the same way ticket 03's
      tool does, adapted for a range aggregate rather than a snapshot (see note above).
- [x] `query_log` records the tool name + arguments for this tool's hits.
- [x] Tested at both seams: black-box final-answer content (4 tests, including the real
      logged misspelling "hectres"), and direct tool-selection assertion for canonical
      phrasings (real OpenAI call).
- [x] No changes required to tier-3's core dispatch mechanism *shape* - only the
      `date_from` pass-through noted above, applied uniformly to all tier-3 tools
      including ticket 03's headcount tool (91 tests passing, up from 86, zero
      regressions).
