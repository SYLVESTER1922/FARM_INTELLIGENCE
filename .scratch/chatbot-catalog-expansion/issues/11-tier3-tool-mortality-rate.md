# 11: Tier-3 tool - mortality rate + relative-period death counts

**What to build:** "What's our mortality rate for the whole farm?" and "how many
chickens died last week?" both resolve via one tier-3 tool - a combined death-count and
mortality-rate figure, farm-wide or per-domain, over either the global date filter, a
30-day default, or a relative period named in the question ("last week" -> a real,
deterministically-computed window). Two real QA-pass gaps closed by one tool, not two,
since they share the same underlying "deaths in a window / headcount" computation.

**Blocked by:** 03 (Tier-3 core - tool-calling dispatch)

**Status:** done

**Implementation note**: `period` is a symbolic enum (`last_7_days`/`last_30_days`/
`last_90_days`), matching Savanna QSR Intelligence's own proven `q_revenue_by_period`
pattern (verified by reading its real code) - the LLM is never trusted to compute a
relative date itself, since it has no way to know "today" here means the latest real
data date, not the calendar date. The tool computes the real window boundary in Python
instead. Reuses `deaths_in_window` and `active_headcount_asof`, both relocated to
`chatbot/catalog.py` (mirroring `date_filter_sql`'s and `active_headcount_asof`'s
existing placement there) so this tool and the dashboard's Mortality Rate stat card
share one source of truth - `ui/queries.py` now imports `deaths_in_window` from there
too.

- [x] Farm-wide (both domains combined) and single-domain mortality rate both work.
      Verified against real production Supabase data: 0 deaths / 521 headcount over the
      default 30-day window - independently cross-checked, exact match (a real zero,
      not a bug).
- [x] "How many chickens died last week?" resolves via `period=last_7_days`,
      domain=poultry - verified against real data (0 deaths in that exact window,
      cross-checked directly).
- [x] Module scoping applies (piggery/poultry), same static-declaration rule.
- [x] Tested at both seams: black-box final-answer content (farm-wide rate and
      relative-period count), a direct test confirming `period` computes the real
      window boundary correctly, and tool-selection assertion for canonical phrasings
      including both exact real logged questions.
