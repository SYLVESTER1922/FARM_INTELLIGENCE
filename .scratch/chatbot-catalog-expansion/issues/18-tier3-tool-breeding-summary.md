# 18: Tier-3 tool - breeding summary

**What to build:** "How many litters this month?" / "which sow had the biggest litter"
and real phrasing variants resolve via a new tier-3 tool - litters, born-alive, weaned
counts, average litter size, and best sow (by born-alive count) over a period. The
Breeding page exists on the dashboard but had zero prior chat coverage before this
ticket.

**Blocked by:** 03 (Tier-3 core - tool-calling dispatch)

**Status:** done

**Implementation note**: reuses the exact rows already computed for the dashboard's
Breeding page - `farrowing_records`, relocated from `ui/queries.py` to
`chatbot/catalog.py` (same dependency-direction reason as `active_headcount_asof`,
`fcr_by_batch`, etc.) so this tool and the dashboard share one source of truth, not two
divergent queries. `domain` accepted for a uniform signature but unused - breeding is
piggery-only.

- [x] "How many litters did we have and which sow had the biggest litter?" resolves to
      `q_breeding_summary` with the real litter count and best sow (verified against a
      real fixture: 2 litters, SOW-1 best with 12 born alive vs. SOW-2's 8).
- [x] `farrowing_records`/`fetch_breeding_summary` relocated to `chatbot/catalog.py`;
      `ui/queries.py`'s dashboard delegates to it, zero regression (full suite green).
- [x] Module scoping applies (piggery).
- [x] Tested at both seams: black-box final-answer content and tool-selection assertion
      for canonical phrasings.
