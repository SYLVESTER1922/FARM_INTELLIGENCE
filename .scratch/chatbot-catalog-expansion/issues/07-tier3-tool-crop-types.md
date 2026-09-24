# 07: Tier-3 tool - crop types listing

**What to build:** "What crops do we have?" and real phrasing variants resolve via a new
tier-3 tool listing the distinct crop types planted - a listing, not an aggregate,
complementing ticket 04's `q_crop_area_planted` (total hectares). Sourced from a real
logged failure surfaced by live production usage right after tickets 01-06 shipped.

**Blocked by:** 03 (Tier-3 core - tool-calling dispatch)

**Status:** done

- [x] "What crops do we have?" resolves to a real, correct list of distinct crop types
      from `plantings`, not the total-area figure ticket 04 already covers. Verified
      against real production Supabase data (independently cross-checked: Groundnuts,
      Maize, Soyabean, Tomatoes - matching the real underlying data exactly).
- [x] Module scoping applies: if crops is turned off for the farm, this is scoped out.
- [x] Respects the global date-range filter (by planting date) the same way ticket 04's
      tool does - a range-scoped listing, not a point-in-time snapshot.
- [x] `query_log` records the tool name + arguments for this tool's hits.
- [x] Tested at both seams: black-box final-answer content (3 tests), and direct
      tool-selection assertion for canonical phrasings, including the exact real logged
      question "what crops do we have ?" (trailing space and all).
- [x] No changes required to tier-3's core dispatch mechanism itself (108 tests passing,
      up from 98, zero regressions).
