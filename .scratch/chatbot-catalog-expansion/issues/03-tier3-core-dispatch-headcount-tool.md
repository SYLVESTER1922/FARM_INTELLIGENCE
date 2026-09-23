# 03: Tier-3 core - tool-calling dispatch + first tool (headcount)

**What to build:** The full tier-3 mechanism, working end-to-end for one real question -
live pig/poultry headcount - reached only when tier-1 and tier-2 both produce a true
`no_match`/`ambiguous`. OpenAI native tool-calling picks the tool; the tool runs a
parameterized query and returns a real result; a second LLM call narrates only that
result. This ticket establishes module scoping, date-range filter integration, argument
validation, and `query_log` recording for tier-3 as a whole, all exercised through this
one tool, so every later tier-3 tool ticket is pure reuse of this infrastructure.

**Blocked by:** None (can start immediately) - this is the prefactor-and-first-tracer-
bullet ticket that everything else in this feature builds on.

**Status:** done

**Implementation note**: the headcount SQL/methodology was relocated from `ui/queries.py`
into `chatbot/catalog.py` (`active_headcount_asof`) rather than duplicated, mirroring
`date_filter_sql`'s existing placement there for the same dependency-direction reason
(chatbot must never depend on ui). `ui/queries.py`'s dashboard stat card now imports and
calls the same function tier-3's tool does - one source of truth, verified to produce
identical results before and after the move. The date-range filter is applied as a
point-in-time cutoff (`date_to` or the latest real data date), not the `{date_filter}`
SQL-fragment range pattern tiers 1-2 use - a deliberate difference since this tool's
query is a snapshot, not a range aggregate, documented in `chatbot/tools.py`.

- [x] "How many pigs do we have?" and real logged phrasing variants resolve via tier-3
      to a real, current headcount figure - reusing the existing "active as of a date"
      methodology already established for the dashboard's Active Headcount stat card,
      not a naive current-status read. Verified against real production Supabase data
      (independently cross-checked: 12 active pigs as of 2026-09-15, matching the real
      underlying data exactly) in addition to local test-DB coverage.
- [x] The headcount tool is reached only after a true `no_match`/`ambiguous` from tier-1
      and tier-2 - it is never reached for a `missing_parameter` or `scoped_out` result
      (regression test added: the ticket-02 missing_parameter case is confirmed to never
      reach tier-3).
- [x] The tool executes through parameterized queries only; no string-built SQL.
- [x] Any closed-vocabulary argument the tool takes (e.g. a domain name) is validated
      against its fixed list before the query runs; an invalid value fails cleanly (no
      query executed) rather than returning an empty or wrong result - covered by two
      dedicated tests (the validation function directly, and the full dispatch path).
- [x] Module scoping applies: if piggery (or poultry) is turned off for the farm, a
      headcount question touching that domain is scoped out, using the same
      static-declaration mechanism and uniform check the existing catalog already uses.
- [x] The tool respects the globally-selected date-range filter, applied as an as-of
      cutoff (see implementation note above).
- [x] `query_log` records, for this tier-3 hit, the tool name and its validated
      arguments - required an `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` migration
      (idempotent, safe against the already-existing production table, same pattern the
      sync engine already uses throughout).
- [x] Tested at both seams agreed in the spec: black-box through `answer_question`
      (final answer content, scoping, date-filter behavior - 8 tests), and directly
      against the narrow tool-selection function (real OpenAI call, asserting the
      headcount tool is selected for canonical real phrasings, and correctly *not*
      selected for an unrelated question - 2 tests).
- [x] All existing tier-1/tier-2 tests and behavior remain unchanged (86 tests passing,
      up from 76; zero regressions).
