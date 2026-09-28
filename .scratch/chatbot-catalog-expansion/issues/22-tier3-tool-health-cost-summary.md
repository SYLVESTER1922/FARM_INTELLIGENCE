# 22: Tier-3 tool - health/vet cost summary over time

**What to build:** "How much have we spent on vet care this month?" / "health events
this month" and real phrasing variants resolve via a new tier-3 tool - total health/vet
events and cost over a period, farm-wide or for one domain, broken down by event type.
Distinct from the existing `piggery_disease_outbreak` catalog query, which only ever
surfaces today's single worst batch - this tool answers cost/trend questions over an
arbitrary period instead.

**Blocked by:** 03 (Tier-3 core - tool-calling dispatch)

**Status:** done

**Implementation note**: reuses the exact rows already computed for the dashboard's
Health page - `health_by_event_type`, relocated from `ui/queries.py` to
`chatbot/catalog.py` (same dependency-direction reason as the other relocated shared
queries), so this tool and the dashboard share one source of truth.

- [x] "How much have we spent on vet care for piggery?" resolves to
      `q_health_cost_summary` with the real total cost and per-event-type breakdown
      (verified against a real fixture: 15.0 + 30.0 = 45.0 total, across a Treatment
      and a Vaccination event).
- [x] `health_by_event_type`/`fetch_health_summary` relocated to `chatbot/catalog.py`;
      `ui/queries.py`'s dashboard delegates to it, zero regression (full suite green).
- [x] Module scoping applies (piggery/poultry).
- [x] Tested at both seams: black-box final-answer content and tool-selection assertion
      for canonical phrasings.
