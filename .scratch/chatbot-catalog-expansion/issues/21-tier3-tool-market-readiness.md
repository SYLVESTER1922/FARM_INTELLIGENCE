# 21: Tier-3 tool - market/off-take readiness

**What to build:** "Which batches are ready to sell?" / "are any pigs overdue for
market" and real phrasing variants resolve via a new tier-3 tool - batches whose
`target_market_date`/`target_off_date` has passed (overdue) or falls within the next 30
days (upcoming), as of a cutoff.

**Blocked by:** 03 (Tier-3 core - tool-calling dispatch)

**Status:** done

**Implementation note**: deliberately NOT filtered by a `status` column. Real fixtures
show `pig_batches` and `poultry_batches` use different status vocabularies for an
in-progress batch (`"Active"` vs. `"Growing"`) - a single hardcoded status string (first
drafted as `status = 'Active'`) would have silently excluded every poultry batch from
the results. Caught before shipping by checking real fixture sample rows rather than
guessing the status vocabulary; fixed by dropping the status filter entirely and
surfacing every batch with a target date instead.

- [x] "Which pig batches are overdue for market?" resolves to `q_market_readiness` with
      the real overdue batch (verified against a real fixture: one batch past its
      target_market_date relative to the latest data date, one far in the future -
      only the overdue one is returned).
- [x] No hardcoded `status` filter - real per-domain status vocabulary differs and isn't
      exhaustively known; the tool trusts target dates only.
- [x] Module scoping applies (piggery/poultry).
- [x] Tested at both seams: black-box final-answer content and tool-selection assertion
      for canonical phrasings.
