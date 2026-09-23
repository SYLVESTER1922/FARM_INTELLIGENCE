# 05: Tier-3 tool - weather log lookup

**What to build:** "What's the weather like today?" and real phrasing variants resolve
via a new tier-3 tool querying `weather_log` (synced today with zero existing query
coverage), reusing ticket 03's infrastructure.

**Blocked by:** 03 (Tier-3 core - tool-calling dispatch + first tool)

**Status:** done

**Implementation note**: `_find_inactive_domain` needed a small defensive fix - weather
is farm-wide, not owned by any single domain module, so its tool declares an *empty*
domains list (`TOOL_DOMAINS["q_weather"] = []`). The existing scoping check built its SQL
column list directly from the declared domains, which produced invalid SQL (`SELECT
FROM farm_profile...`) for an empty list - every existing catalog entry always declared
at least one domain, so this was never hit before. Fixed by returning `None` immediately
for an empty domain list, benefiting both this tool and any future farm-wide tool.

- [x] The real logged question "What's the weather like today?" resolves to a real
      answer drawn from `weather_log` - "today" honestly reflects the latest real data
      date, not the calendar date, consistent with how "freshness" is already handled
      elsewhere in this app (e.g. Data Coverage). Verified against real production
      Supabase data (independently cross-checked: 2026-09-15, min 6.7°C, max 21°C, 0mm
      rain, 47% humidity, "Normal" - matching the real underlying data exactly).
- [x] Respects the global date-range filter, applied as an as-of cutoff like ticket 03's
      headcount tool (a point-in-time lookup, not a range aggregate).
- [x] `query_log` records the tool name + arguments for this tool's hits.
- [x] Tested at both seams: black-box final-answer content (3 tests, asserting on the
      real numeric values rather than the LLM's own paraphrasing of dates/event text,
      which varies harmlessly between "2026-01-08" and "January 8, 2026"), and direct
      tool-selection assertion for canonical phrasings including the real logged
      question's exact casing.
- [x] Required one small, reusable fix to tier-3's core dispatch mechanism (see note
      above) - otherwise no changes to the mechanism's shape (95 tests passing, up from
      91, zero regressions).
