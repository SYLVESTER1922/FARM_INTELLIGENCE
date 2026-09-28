# 23: Tier-3 tool - revenue breakdown (top buyers / products)

**What to build:** "Who's our biggest buyer?" / "what's our best-selling product" and
real phrasing variants resolve via a new tier-3 tool - top 5 buyers or products by total
revenue, over a period, farm-wide or for one domain.

**Blocked by:** 03 (Tier-3 core - tool-calling dispatch)

**Status:** done

**Implementation note**: `by` (`"buyer"` or `"product"`) is required in the tool schema
and validated explicitly, same pattern as `q_cost_per_animal`'s required `domain` and
this batch's `q_batch_weight`'s required-one-of validation.

- [x] "Who's our biggest buyer for piggery?" resolves to `q_revenue_breakdown` with the
      real top buyer and their total (verified against a real fixture: one buyer across
      two sales totalling 1800, correctly ranked above a second buyer's single 240
      sale).
- [x] `by` is required and validated; a missing or invalid value fails cleanly as
      `invalid_tool_argument`, not a crash.
- [x] Module scoping applies (piggery/poultry/crops).
- [x] Tested at both seams: black-box final-answer content, direct argument-validation
      tests (missing and invalid `by`), and tool-selection assertion for canonical
      phrasings.
