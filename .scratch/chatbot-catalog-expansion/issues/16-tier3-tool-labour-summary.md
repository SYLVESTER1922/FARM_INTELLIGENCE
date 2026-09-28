# 16: Tier-3 tool - labour summary

**What to build:** "What's our total labour cost?" / "how many labour hours did we
use" and real phrasing variants resolve via a new tier-3 tool over `labour_log` - total
hours, overtime hours, and labour cost, farm-wide or for one domain. Closes a real gap:
`labour_log` is tracked (daily hours/cost per staff member/task) but had zero dashboard
page and zero prior chat coverage before this ticket.

**Blocked by:** 03 (Tier-3 core - tool-calling dispatch)

**Status:** done

**Implementation note**: `domain` is optional, validated against the same closed
vocabulary as expenses (`piggery`/`poultry`/`crops`) - `labour_log` can also carry
shared/unassigned entries with a NULL domain, which a domain filter correctly excludes
rather than mismatching. A straight SQL SUM, no cutoff/as-of pattern needed since this
is a genuine range aggregate, not a point-in-time snapshot.

- [x] "What's our total labour cost for piggery?" resolves to `q_labour_summary` with
      the real summed cost (verified against a real fixture: two labour_log rows,
      15.0 + 9.0 = 24.0 total).
- [x] `domain` optionally narrows the summary; omitted gets the farm-wide total.
- [x] Module scoping applies (piggery/poultry/crops).
- [x] Tested at both seams: black-box final-answer content and tool-selection assertion
      for canonical phrasings.
