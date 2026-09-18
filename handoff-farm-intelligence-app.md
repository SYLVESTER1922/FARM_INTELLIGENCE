# Handoff: Farm Intelligence App

Session focus, across the project's full history: turning a 23-tab Netrisyl Farm
Intelligence Google Sheets workbook into a populated demo dataset, syncing it into a real
Postgres/Supabase database, and building a full chatbot answer engine on top of it —
landing a working, tested pipeline that answers the project's original motivating question
("how does feed cost split between pigs and chickens") in plain language, for real,
against the cloud database.

## Repo state

- Working dir: `/Users/vharsh/Farm-Intelligence-App` — git repo.
- Remote: `https://github.com/SYLVESTER1922/FARM_INTELLIGENCE.git` (`origin`). Both
  `main` and `prototype/supabase-domain-join-test` are pushed and tracking their remote
  counterparts. Working tree clean.
- `main` branch, commits in order (oldest to newest):
  - `d4cdbaa` — initial workbook + 12 months of synthetic data + generation scripts.
  - `21bd86e` — fix to `06_FEED_INVENTORY` grain (domain+feed_type+week).
  - `0bbdf46` — `spec-supabase-sync.md`.
  - `daaf0a6` — six local tickets under `.scratch/supabase-sync/issues/`.
  - `07e0c1b` → `fda9117` — sync tickets 01–06, all `done`. Sync spec fully implemented.
  - `2ec2fd3` / `13d5a83` — gitignore entries for `.env.supabase` and `supabase/`.
  - `763611b` — `spec-chatbot-answer-engine.md` + four local tickets under
    `.scratch/chatbot-answer-engine/issues/`.
  - `c5e0fd0` — switched the chatbot's LLM provider from Claude to OpenAI GPT-4o-mini,
    before any ticket code was written against the old provider.
  - `8a60063` — corrected tickets 01/03: phrasing is always an LLM call (caught before
    implementation started; "zero LLM calls" only ever applied to pure-refusal tests).
  - `7eddd6a` → `7cab355` — chatbot tickets 01–04, all `done`. Chatbot spec fully
    implemented.
- Throwaway branch `prototype/supabase-domain-join-test` (`447dbec`) — the SQLite
  prototype that first found the sync's feed_inventory grain issue. Deliberately not
  merged into `main` (prototypes are a primary source kept on their own branch here).

## What's built, in two layers

**Both specs below are complete.** Read them plus their ticket files for full design
rationale and acceptance criteria — this doc summarizes, it doesn't duplicate them.

### 1. Sync engine (`sync/`) — `spec-supabase-sync.md`, tickets 01–06

`sync/engine.py` + `sync/workbook_reader.py`: one seam,
`sync_workbook_to_supabase(filepath, farm_code, dsn) -> SyncReport`, syncing the entire
23-tab workbook into Postgres. Key facts:

- `06_FEED_INVENTORY` is synced at `domain + feed_type + week` grain — the fix that
  makes cross-domain feed-cost queries resolve cleanly (found via a throwaway SQLite
  prototype before the real sync was built).
- Real Postgres FK constraints where one target table exists; a `_validate_batch_ref`
  helper for polymorphic references (piggery vs. poultry) a single FK can't express.
  Every violation is caught and reported in `SyncReport.errors`, never raised. Every
  sync is idempotent.
- **Two real bugs found by `tests/test_sync_full_workbook.py`** (the full-workbook
  regression, run against real data, not fixtures — neither bug was caught by 47 passing
  fixture-based tests beforehand):
  1. `00_FARM_PROFILE` and `01_STAFF` are singleton/registry tabs where real data starts
     at row 3, not row 4 (the general convention) — `01_STAFF`'s row 3 holds a staff
     member referenced 286 times elsewhere. `read_tab_rows` gained a `min_row` param to
     handle this.
  2. `07_HEALTH_LOG`'s reference column is `batch_ref`, not `batch_code` as I'd assumed
     and written throughout — including in my own test fixtures, which is why it went
     uncaught until the sync ran against the real header row.
- Local dev environment: Postgres 16 via Homebrew (`brew services`), test database
  `farm_intelligence_test`, trust auth. Project venv at `.venv/`.
- Three planted findings, confirmed queryable end-to-end (local Postgres *and* real
  Supabase): poultry batch `BRO-P02` (mortality spike), pig batch `PIG-B02` (disease
  outbreak), crop sale product `Soya` (not `"Soyabean"` as earlier notes said) /
  `batch_ref='SB-PL2-25A'` — still `payment_status='Owing'`.

**Supabase cloud deployment**: real project `farm-intelligence` (ref
`bfetyunxnmqfvtiqirsr`, region `us-west-2`, org `gwemzvnyvfifialranlt`), created via the
`supabase` CLI. Verified: sync ran against it with zero errors, all row counts matching
the local-Postgres regression exactly, feed-cost-split query resolving cleanly there too.

- Auth note: the Supabase CLI's OAuth flow doesn't work at all in this sandboxed
  environment (no TTY) — only a personal access token works.
- Account is free-tier, 2-active-project cap — creating `farm-intelligence` required
  pausing an existing project (`JCC-Chatbot`, ref `gsdvxywkbhthrjhmffnm`) via the
  Management API, with the user's explicit go-ahead. **Still paused** — see Open Items.
- Credentials, none committed: `~/.supabase_access_token`, `~/.supabase_farm_db_password`,
  `.env.supabase` (project root, gitignored — `SUPABASE_PROJECT_REF` +
  `SUPABASE_DB_DSN`), `supabase/` (gitignored, CLI-local state only).

### 2. Chatbot answer engine (`chatbot/`) — `spec-chatbot-answer-engine.md`, tickets 01–04

`chatbot/` package, one seam mirroring the sync's:
`answer_question(question, farm_code, dsn) -> Answer`. Design was fully grilled via
`/grill-me` before the spec was written (tiered intent resolution, module scoping, strict
no-LLM-arithmetic split — all explicitly settled decisions, not open for re-litigation).

- `catalog.py` — the query catalog: `feed_cost_split` (cross-domain, requires an
  explicit `<Month> <Year>` parameter extracted from the question text),
  `poultry_mortality_spike`, `piggery_disease_outbreak`, `crop_debtor` (the three
  planted findings, no required params). Each entry declares which `domains` it
  touches, for scoping.
- `matcher.py` — tier-1 deterministic matcher: pure Python, curated phrase clusters,
  normalized token-overlap scoring, zero LLM/network calls. Modeled explicitly on a
  lesson from a prior Netrisyl pharmacy chatbot project: flat keyword lists were
  brittle, and full LLM-per-question was unnecessary machinery for a small known
  catalog.
- `fallback.py` — tier-2: one OpenAI (GPT-4o-mini) call only when tier 1 misses,
  validated against the exact same closed vocabulary tier 1 uses before being trusted.
  No retry loop.
- `engine.py` — orchestrates: tier-1 match → tier-2 fallback if needed → module scoping
  (one uniform check, applied regardless of which tier resolved intent, cross-domain-safe
  — a query touching multiple domains is scoped out if *any* touched domain's module is
  inactive) → SQL execution → OpenAI phrasing (only ever sees already-computed final
  values, never raw rows) → fire-and-forget `query_log` write.
- **LLM provider is OpenAI GPT-4o-mini, not Claude** — switched mid-build per explicit
  user decision, to match what other Netrisyl products already use (JCC-Chatbot, the
  pharmacy assistant). Reads `OPENAI_API_KEY` from the environment only, never a
  hardcoded path; `tests/conftest.py` sets it from `~/.openai_api_key` for local test
  runs only.
- **`query_log`** (Supabase table, created idempotently): logs every question, answered
  or not — `intent_source` (`deterministic`/`llm_fallback`/`unresolved`), `query_id`
  (populated whenever resolution succeeded, including scoped-out cases),
  `failure_reason` (genuine catalog gaps only: `no_match`/`ambiguous`/
  `missing_parameter`/`invalid_llm_intent`), `scoped_out_reason` (the module name
  itself, kept structurally separate from `failure_reason` so the two "no answer" kinds
  don't pollute each other's later analysis).

**Three real bugs/gaps found while implementing** (full detail in each ticket file's
notes):
1. First phrasing prompt only told the model to preserve numeric values exactly, not
   identifiers — it correctly computed `PIG-B02`'s data in SQL but the phrased answer
   never named the batch. Fixed by requiring every field, identifiers included, verbatim.
2. First fallback-validation pass conflated "the LLM honestly declines" with "the LLM
   names an unknown `query_id`" — both mapped to `invalid_llm_intent`, which silently
   overwrote every tier-1 `unresolved` reason whenever fallback was attempted and also
   failed, breaking "all tier-1-only tests keep passing unmodified." Fixed by threading
   tier 1's original reason through, and further distinguishing "unknown `query_id`"
   (real `invalid_llm_intent`) from "right `query_id`, question just lacks a required
   parameter" (still `missing_parameter` — same root cause tier 1 uses that label for).
3. `invalid_llm_intent` turned out untestable via the real API: GPT-4o-mini, given the
   extraction prompt, empirically never hallucinates an unknown `query_id` — it either
   resolves correctly or honestly declines, even under mild adversarial prompting
   (probed directly before concluding this). Agreed with the user to test this one
   branch via a deterministic unit test directly on `validate_llm_intent` instead of a
   live call — an explicitly-agreed, narrow second seam (validating our own
   closed-vocabulary check, not model behavior), not a silent black-box violation.

**Testing conventions established across both layers** (precedent for future work):
black-box only, through the one public seam; real local Postgres for every test, no
mocking; a *small* number of tests hit real external services end-to-end (Supabase, then
OpenAI) rather than exhaustive scenario coverage against a paid/slow API; a narrow,
explicitly-agreed-with-the-user exception when a live service genuinely can't be made to
exercise a specific branch.

- Combined test suite: **68 tests, all passing**, stable across repeated full-suite runs.
  Run with `source .venv/bin/activate && python -m pytest tests/`.

## Open items — unresolved, don't assume either way

- **`~/.claude/settings.json` question still never answered.** Whether to set
  `permissions.blockReadsOutsideWorkingDirectories` from `true` to `false` (a global,
  not project-scoped, sandboxing setting). Still `true`. Ask before touching it.
- **Supabase `JCC-Chatbot` project is still paused** (paused to free a slot under the
  account's 2-active-project free-tier limit when `farm-intelligence` was created). The
  user was asked whether to unpause it and chose to leave it paused. Revisit if needed:
  pause something else to swap it back in, or upgrade the plan.

## Key facts about the workbook (reference, don't re-derive)

- 23 tabs: `README`, `99_LISTS`, `00_FARM_PROFILE`, `01_STAFF`, `02_EXPENSES`,
  `03_REVENUE`, `04_LABOUR_LOG`, `05_WEATHER_LOG`, `06_FEED_INVENTORY`, `07_HEALTH_LOG`,
  `P1`–`P5` (piggery), `C1`–`C3` (poultry), `F1`–`F5` (crops).
- Row convention: row 1 = purpose/cadence note, row 2 = headers, row 3 = sample, row 4+ =
  data — **except** `00_FARM_PROFILE` and `01_STAFF`, where row 3 holds real data (see
  sync bug #1 above). Never touch rows 1–3 when writing to the workbook itself.
- Formula-bearing columns that must stay formulas if writing to the `.xlsx` directly:
  `02_EXPENSES.total_cost`, `03_REVENUE.total_amount`, `04_LABOUR_LOG.labour_cost`,
  `P2_PIG_DAILY_LOG.closing_count`, `P3_PIG_WEIGHTS.age_days`,
  `P5_BREEDING_FARROWING.expected_farrow_date`, `F5_HARVEST_LOG.quantity_kg`. Confirmed
  clean via LibreOffice recalculation in an earlier session: 1,876 formulas, 0 errors.
- `gen_scripts/`: `generate_data.py` (full generator, seed=42), `write_workbook.py`,
  `verify.py`, `regenerate_feed_inventory.py`, `Netrisyl_Farm_Intelligence_Workbook.original_backup.xlsx`.

## Ultimate goal (stated by user) — now fully done, backend-wise

Build a chatbot on top of this farm data, able to answer cross-domain questions in plain
language. **Both the data layer and the answer-engine backend are now done, tested, and
deployed** — a real Supabase Postgres database, populated from the workbook, and a
working `answer_question` seam that resolves questions (deterministic → LLM fallback),
respects module scoping, never lets an LLM touch raw-row arithmetic, and logs everything
for future catalog improvement.

**Not built**: any UI/frontend for the chatbot (explicitly out of scope in the spec),
multi-turn conversation handling (also explicitly out of scope — each question resolved
independently), and any analysis/dashboarding on top of `query_log` (the table and write
path exist; nothing reads it yet).

## Suggested skills for the next session

- **mattpocock-skills:to-spec** / **to-tickets** — for the chatbot's UI/frontend, or for
  wiring `answer_question` behind an actual API endpoint/deployment target, the same way
  both prior specs were built.
- **mattpocock-skills:grilling** — if the next concrete step (a real chatbot UI, an API
  layer, a deployment target) has open architectural questions worth stress-testing
  first, the way both the sync design and the chatbot's tiered-intent design were here.
- **mattpocock-skills:tdd** — for any further catalog growth or new capability on
  `answer_question`; the seam and testing-split conventions above are now
  well-established precedent to follow.
- **code-review** or **simplify** — `sync/engine.py` (20 near-identical per-table sync
  functions) and `chatbot/catalog.py` (a growing list of near-identical `CatalogQuery`
  entries) are both candidates for a table-driven refactor now that the pattern is
  proven several times over. Deliberately not done mid-TDD-loop — refactoring is a
  separate step per the TDD skill.
- **mattpocock-skills:domain-modeling** — if formalizing the workbook's domain
  vocabulary (a `CONTEXT.md` or ADR) makes sense now that the schema has been through
  several real design fixes across both the sync and chatbot builds.
