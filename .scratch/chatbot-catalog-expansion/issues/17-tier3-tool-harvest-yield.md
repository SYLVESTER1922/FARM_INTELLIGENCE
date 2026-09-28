# 17: Tier-3 tool - harvest yield per hectare

**What to build:** "Which plot yields best per hectare?" and real phrasing variants
resolve via a new tier-3 tool joining `harvest_log`/`plantings`/`plots` to compute kg
harvested per hectare, per plot - distinct from the Domain Lookup tab's existing
total-kg-harvested figure, which never divides by area. Ranks plots best/worst.

**Blocked by:** 03 (Tier-3 core - tool-calling dispatch)

**Status:** done

**Implementation note**: grouped by `planting_code` (the correct grain for area_ha - one
planting has one area, and a plot can carry multiple plantings across seasons), joined
up to `plot_code`/`crop` for labelling. `domain` accepted for a uniform tool-calling
signature but unused - crops is the only domain harvest_log belongs to.

- [x] "Which plot had the best yield per hectare?" resolves to `q_harvest_yield` with
      the real best plot and its kg/ha figure (verified against a real fixture:
      PLOT-1 at 8000kg/2.0ha = 4000 kg/ha vs. PLOT-2 at 1000kg/1.0ha = 1000 kg/ha).
- [x] Module scoping applies (crops).
- [x] Tested at both seams: black-box final-answer content and tool-selection assertion
      for canonical phrasings.
