# Spec: Chatbot Answer Engine (Tiered Intent Resolution)

## Problem Statement

The farm owner's data is now synced into a real Postgres/Supabase database (see
`spec-supabase-sync.md`), and a proven query can answer cross-domain questions like "how
does feed cost split between pigs and chickens." But there's still no way for the farm
owner to actually ask a question in plain language and get an answer — and any naive
"let an LLM figure it out" approach risks two specific failure modes already identified:
the model hallucinating arithmetic on raw data instead of using the database's real
numbers, and the model answering questions about modules (piggery/poultry/crops) the farm
has explicitly turned off in its profile.

## Solution

A tiered intent-resolution chatbot. A deterministic, zero-LLM concept-cluster matcher
tries first against a small, hand-written, hand-tested catalog of parameterized SQL
queries — the same kind of query already proven in the sync engine's own tests. Only when
that deterministic pass can't produce a complete, unambiguous intent does the system fall
back to a single LLM call for structured-intent extraction, and even then, the LLM's
output is validated against the same closed vocabularies before any SQL runs. Every query
in the catalog is hand-written SQL, so all arithmetic is verifiable and never delegated to
the model. Module scoping is enforced once, uniformly, regardless of which tier resolved
the intent. Every question — answered or not — logs its resolution path to a `query_log`
table, purely for later improving the deterministic catalog from real usage data, never
affecting the answer given.

## User Stories

1. As a farm owner, I want to ask "how does feed cost split between pigs and chickens"
   in plain language and get a correct answer, so I don't need to know SQL or open a
   spreadsheet.
2. As a farm owner, I want to ask about the poultry mortality spike, the piggery disease
   outbreak, or the unpaid crop sale in plain language, so the chatbot can surface real
   problems on my farm, not just answer questions I already know to ask.
3. As a farm owner, I want to ask about a module I've turned off (e.g. crops, if
   `module_crops_active = No`) and get a clear explanation of why it can't answer, so I
   understand the refusal isn't a bug.
4. As a farm owner, I want an honest "I can't answer that yet" when my question doesn't
   match anything the system knows how to answer, so I never get a confidently wrong
   answer.
5. As a developer, I want a deterministic concept-cluster matcher to try first, so common
   questions never cost an LLM call or introduce nondeterminism.
6. As a developer, I want the concept-cluster matcher built from curated phrase clusters
   (multiple example phrasings per query), not a flat keyword list, so it's resilient to
   phrasing variation without the brittleness a prior chatbot project hit with keyword
   lists.
7. As a developer, I want the LLM fallback's structured-intent output validated against
   the same closed vocabularies (query IDs, domains, metrics) the deterministic matcher
   uses, so a hallucinated metric or domain can never reach SQL.
8. As a developer, I want the LLM fallback to fail straight to "unresolved" on a
   validation miss, with no retry loop, so failures are fast and don't burn extra API
   calls chasing a fix.
9. As a developer, I want the phrasing step to receive only already-computed final values
   from the query catalog's SQL execution, never raw or row-level data, so it is
   structurally unable to compute a wrong number — not just instructed not to.
10. As a developer, I want every query in the catalog to be hand-written, parameterized
    SQL, so every possible arithmetic operation is written and tested once, not generated
    per request.
11. As a developer, I want to know later which phrasings are causing LLM fallbacks or
    outright failures, so I can improve the deterministic catalog from real usage instead
    of guessing.
12. As a developer, I want failed-lookup reasons categorized into genuine catalog gaps
    (`no_match`, `ambiguous`, `missing_parameter`, `invalid_llm_intent`), distinct from
    expected module-scoping refusals, so a fallback-rate metric isn't polluted by farm
    owners legitimately asking about modules they've turned off.
13. As a developer, I want inactive-module refusals tracked with their resolved
    `query_id` still populated, so "what do people ask about when a module is off" is
    itself an answerable, legitimate question, separate from catalog-gap analysis.
14. As a developer, I want `query_log` writes to be fire-and-forget, so a logging failure
    can never block or break the user-facing answer.
15. As a developer, I want the two refusal paths (`unresolved`, `scoped_out`) to return
    fixed template strings rather than LLM-phrased text, so no unnecessary LLM call
    happens where a deterministic message already suffices.
16. As a developer, I want a single public seam (`answer_question`) covering the whole
    pipeline, so tests observe input/output behavior without depending on the matcher's,
    the LLM's, or the query catalog's internals.
17. As a developer, I want intent resolution on the deterministic path tested
    exhaustively against a real Postgres instance with zero LLM calls for that step, so
    the bulk of the test suite's *intent-resolution logic* stays fast, free, and fully
    deterministic (phrasing itself is still a real LLM call for every successful answer,
    regardless of tier — see Testing Decisions).
18. As a developer, I want a small number of tests to call the real OpenAI API for the
    fallback path, so the actual integration is proven end-to-end, not just simulated —
    the same reasoning that drove ticket 06 to test the real Supabase sync rather than
    trust a mock.
19. As a developer, I want the raw question text stored in `query_log` (not just
    metadata like `intent_source`), so a fallback or failure row is actually actionable —
    you can see exactly what phrasing tripped the system, not just that something did.
20. As a developer, I want `query_log.intent_source` to be a closed enum
    (`deterministic`, `llm_fallback`, `unresolved`), so downstream analysis queries stay
    reliable as the table grows.
21. As a developer, I want module-scoping enforced once, on the resolved intent object,
    rather than duplicated inside the matcher and the LLM prompt separately, so there's
    one place to change if scoping logic ever changes.
22. As a farm owner, I want scoping to reflect my farm's *current* module configuration
    (`00_FARM_PROFILE`), not a snapshot taken at some earlier point, so toggling a module
    on later immediately unblocks questions about it.
23. As a developer, I want the query catalog and its phrase clusters defined as plain
    Python data, matching the sync engine's existing constants-based style, so the
    codebase stays consistent.
24. As a developer, I want a query catalog entry to declare both its SQL and the
    parameters/vocabularies it needs, so validation (closed-vocabulary checks, module
    mapping) can be driven generically rather than hand-coded per query.
25. As a developer, I want the phrasing call and the fallback-extraction call to use the
    same model (OpenAI GPT-4o-mini) for now, so the prompt/response contract stays simple
    while the rest of the pipeline is still new — per-step model optimization is a later
    concern, not a day-one one.
26. As a developer, I want this feature to use the same LLM provider (OpenAI) already
    used elsewhere across Netrisyl's other products (JCC-Chatbot, the pharmacy
    assistant), so the stack stays consistent instead of introducing a second provider
    for one feature.

## Implementation Decisions

- **Seam**: a single public entry point, `answer_question(question: str, farm_code: str,
  dsn: str) -> Answer`, mirroring `sync_workbook_to_supabase`'s shape — the one tested
  boundary for this entire feature. Every internal stage (matcher, LLM calls, catalog
  dispatch, phrasing, logging) stays internal to this seam.
- **Tier 1 — deterministic concept-cluster matcher**: pure Python, no ML dependency, no
  network call. Each query in the catalog owns a curated list of example phrasings
  ("clusters"); an incoming question is matched via normalized substring/token-overlap
  logic against these clusters. A match only counts as *complete* if it (a) identifies
  exactly one `query_id` and (b) can deterministically extract every parameter that query
  needs (e.g. domain, date range) from the question text. Anything less than a complete,
  unambiguous match falls through to tier 2.
- **Tier 2 — LLM fallback**: a single OpenAI (GPT-4o-mini) call, invoked only when tier 1
  doesn't produce a complete match, extracting a structured intent object (`query_id` +
  parameters) from the question. Its output is validated against the exact same closed
  vocabularies tier 1 uses (known `query_id`s, known domain/metric values from
  `99_LISTS`-backed enums) before it's trusted. No retry on validation failure — a miss
  here goes straight to `intent_source = unresolved`, `failure_reason = invalid_llm_intent`.
- **Module scoping**: one check, applied after intent resolution succeeds from *either*
  tier, against `00_FARM_PROFILE.module_piggery_active` / `module_poultry_active` /
  `module_crops_active` (already synced by the sync engine). If the resolved query's
  domain maps to an inactive module, the request is refused via the `scoped_out` path:
  `intent_source` still reflects which tier resolved it, `query_id` stays populated
  (resolution genuinely succeeded), and a `scoped_out_reason` records which module was
  inactive.
- **Query catalog**: a fixed, hand-written set of parameterized SQL queries, each with a
  stable `query_id`, declared required parameters, and the closed vocabulary each
  parameter must validate against. All arithmetic (`SUM`, `AVG`, `ROUND`, `GROUP BY`, the
  date-range/join logic already proven in the sync engine's own tests) lives in this SQL —
  never deferred to the phrasing step. Starts with the queries already proven end-to-end:
  feed-cost split by domain, and lookups for the three planted findings; grows over time
  from real `query_log` data, not pinned down exhaustively by this spec.
- **Phrasing**: a second LLM call (same model), whose prompt contains *only* the
  already-computed final result of the matched query's execution — scalars or a small
  aggregate result set, never raw per-row data and never the ambiguity of the original
  question. Its sole job is turning computed values into natural language.
- **Refusal paths**: `unresolved` and `scoped_out` never invoke any LLM, not even for
  phrasing — both return a fixed template string.
- **`query_log` schema** (Supabase table, written by `answer_question` as a fire-and-forget
  side effect on every call, success or failure):
  - timestamp, `farm_code`, `question_text` (raw, stored unredacted — solo/two-person
    farm-ops context, not consumer PII)
  - `intent_source`: enum `deterministic` | `llm_fallback` | `unresolved`
  - `query_id`: nullable; populated whenever intent resolution succeeded (including
    `scoped_out` cases); null only when `intent_source = unresolved`
  - `failure_reason`: nullable; populated only when `intent_source = unresolved`; enum
    `no_match` | `ambiguous` | `missing_parameter` | `invalid_llm_intent` — genuine
    catalog/matching gaps only
  - `scoped_out_reason`: nullable; populated only when a resolved query was refused for
    an inactive module
  - Write failures are caught and logged to application logs only; they never propagate
    into the request path or affect the answer returned.
- **Model**: OpenAI GPT-4o-mini, one model, used for both the tier-2 fallback extraction
  call and the phrasing call — chosen to match the LLM provider already used for this
  exact purpose in Netrisyl's other products (JCC-Chatbot, the pharmacy assistant),
  keeping one provider across the stack rather than introducing Claude for a single
  feature.

## Testing Decisions

- All tests go through the single `answer_question` seam — black-box only; no test reaches
  into the matcher, the catalog dispatch, or prompt construction directly, matching this
  repo's existing testing discipline (`tests/test_sync_*.py`).
- **Deterministic path**: intent resolution is tested exhaustively against a real local
  Postgres instance (same pattern/instance as the sync engine's tests), with zero LLM
  calls for the resolution step itself. Covers every `query_id` in the starting catalog,
  module-scoping for both active and inactive modules, the `query_log` row shape for
  success and `scoped_out` cases, and every `failure_reason` reachable without an LLM
  (`no_match`, `ambiguous`, `missing_parameter`). Note: phrasing is a real OpenAI call
  for *every* successful answer regardless of tier, so "zero LLM calls" describes the
  intent-resolution tests specifically, not the full success-path test (which still
  costs one real API call for phrasing) — only the pure-refusal tests (`unresolved`,
  `scoped_out`) are genuinely zero-LLM end-to-end.
- **LLM fallback path**: a small number of tests call the real OpenAI API end-to-end —
  not mocked, not stubbed — proving the integration genuinely works, the same reasoning
  that drove ticket 06 to regression-test the real Supabase sync instead of trusting a
  simulated one. Not exhaustive scenario coverage: enough to prove (a) a valid fallback
  intent reaches the catalog and produces a correct, correctly-phrased answer, and (b) an
  invalid/hallucinated fallback intent is caught by closed-vocabulary validation and
  logged as `invalid_llm_intent`, never silently trusted.
- Assertions land on the returned `Answer` (text/content) and the resulting `query_log`
  row (`intent_source`, `query_id`, `failure_reason`, `scoped_out_reason`) — never on
  internal function calls, matcher internals, or prompt contents.
- Prior art: `tests/test_sync_shared_core.py` (black-box seam testing, real-database
  assertions) and `tests/test_sync_full_workbook.py` (a small number of tests proving a
  real, costly integration end-to-end rather than exhaustively re-testing it).

## Out of Scope

- The chatbot's UI/frontend — this spec covers the `answer_question` backend seam only.
- Multi-turn conversation or follow-up-question handling — each question is resolved
  independently; no session/context is carried between calls.
- Exhaustively growing the query catalog beyond the queries already proven (feed-cost
  split, the three planted findings) — catalog growth is an ongoing effort informed by
  `query_log` data over time, not something this spec pins down completely.
- A retry/self-correction loop on LLM fallback validation failure — explicitly decided
  against; failures go straight to `unresolved`.
- Embedding- or ML-based matching for tier 1 — explicitly deferred until curated phrase
  clusters stop scaling for the catalog's size.
- Per-step model differentiation (e.g. a cheaper model for extraction vs. phrasing) —
  explicitly deferred as premature optimization.
- Any analysis, dashboarding, or review tooling built on top of `query_log` — this spec
  defines the table and its write path only, not how it's later queried or reviewed.
- Changes to the sync engine itself (`sync/engine.py`) — this spec is built entirely on
  top of the already-synced tables, and doesn't modify them.

## Further Notes

- This spec builds directly on the completed sync engine (`spec-supabase-sync.md`,
  tickets 01–06) and treats its schema (`pig_batches`, `poultry_batches`,
  `feed_inventory` at `domain + feed_type + week` grain, etc.) as a given foundation, not
  open for re-litigation here.
- The full design behind this spec was stress-tested via `/grill-me` before being
  written down; treat the decisions above as settled, not open for re-litigation during
  implementation.
- `query_log`'s table-creation mechanism should follow the same idempotent
  `CREATE TABLE IF NOT EXISTS` pattern already used throughout `sync/engine.py`, but the
  exact wiring (where that creation call lives) is left to the implementing ticket.
- No issue tracker is configured for this project; this is a standalone spec file,
  consistent with `spec-supabase-sync.md`.
