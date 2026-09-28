# 19: Tier-3 tool - feed stock on hand

**What to build:** "How much feed do we have left?" / "are we running low on feed" and
real phrasing variants resolve via a new tier-3 tool - current physical feed stock
(`closing_kg`) per feed type, as of the latest logged inventory date or a given cutoff.
Distinct from feed *cost* (already covered by the dashboard's Feed Cost chart and
`q_expense_by_category`) - this is physical stock on hand, closing a real gap.

**Blocked by:** 03 (Tier-3 core - tool-calling dispatch)

**Status:** done

**Implementation note**: a point-in-time snapshot (like `q_headcount`), not a range
aggregate - `DISTINCT ON (domain, feed_type) ... ORDER BY date DESC` gets the latest row
per feed type as of the cutoff. `date_from` accepted for a uniform signature but unused.

- [x] "How much pig feed do we have left?" resolves to `q_feed_stock` with the real
      latest closing_kg (verified against a real fixture: two dated rows for the same
      feed type, correctly picks the later 350kg over the earlier 400kg).
- [x] Module scoping applies (piggery/poultry).
- [x] Tested at both seams: black-box final-answer content and tool-selection assertion
      for canonical phrasings.
