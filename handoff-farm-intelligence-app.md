# Handoff: Farm Intelligence App

Session focus: turning a 23-tab Netrisyl Farm Intelligence Google Sheets workbook into a
populated demo dataset, validating its schema design via a prototype, fixing the data-model
issue that surfaced, then writing and fully implementing a spec to sync the workbook into
a real Postgres/Supabase database — landing a working, tested sync engine that answers the
project's original motivating question ("how does feed cost split between pigs and
chickens") for real.

## Repo state

- Working dir: `/Users/vharsh/Farm-Intelligence-App` — git repo, initialized mid-session.
- `main` branch, commits in order:
  - `d4cdbaa` — initial workbook + 12 months of synthetic data + generation scripts.
  - `21bd86e` — fix to `06_FEED_INVENTORY` grain (domain+feed_type+week).
  - `59f45f2` / `1fd685e` — session handoff doc (this file) and a correction to it.
  - `0bbdf46` — `spec-supabase-sync.md`: the spec for syncing the workbook into Supabase.
  - `daaf0a6` — six local tickets under `.scratch/supabase-sync/issues/` breaking the spec
    into tracer-bullet slices (no issue tracker configured; this is a solo/two-person
    project, tracker setup was explicitly declined).
  - `07e0c1b` → `fda9117` — tickets 01 through 06, all implemented test-first and all
    marked `done` in their ticket files. **The whole spec is complete.**
- Throwaway branch `prototype/supabase-domain-join-test` (`447dbec`) — the SQLite
  prototype that first found the feed_inventory grain issue. Deliberately not merged into
  `main` (prototypes are a primary source kept on their own branch here, not folded in).
- Working tree is clean.

## What's been built: the sync engine

`sync/engine.py` + `sync/workbook_reader.py` sync the entire real workbook (all 23 tabs)
into Postgres, through one public seam: `sync_workbook_to_supabase(filepath, farm_code,
dsn) -> SyncReport`. Built test-first (TDD skill, seam agreed once at the spec stage and
reused for every ticket) against a **real local Postgres 16 instance** — not SQLite, not a
mock. 50 tests, all passing, in `tests/`.

- **Environment setup done this session**: Homebrew installed (needed sudo, so the user
  ran the installer themselves in their own terminal), then `postgresql@16` via
  `brew install postgresql`. It's running as a `brew services` launch agent. A dedicated
  test database `farm_intelligence_test` exists, local trust auth (no password). A
  project-local virtualenv at `.venv/` has `psycopg[binary]`, `pytest`, `openpyxl`
  installed (`.venv/` and `.pytest_cache/` are gitignored). To run the tests:
  `source .venv/bin/activate && python -m pytest tests/`.
- **What's synced**: all 23 tabs — farm profile, staff, `99_LISTS` (as a generic
  `list_values(list_name, value)` reference table), all 5 piggery tabs, all 3 poultry
  tabs, all 5 crop tabs, and all 6 shared-core tabs (expenses, revenue, labour, weather,
  feed inventory, health log).
- **Design decisions carried through from the prototype/spec**: `06_FEED_INVENTORY` is
  synced at `domain + feed_type + week` grain (not `domain + week`) — this is what makes
  the feed-cost-split query resolve with 0 kg unpriced. Referential integrity uses real
  Postgres FK constraints wherever a single target table exists (e.g. `P2 → P1`); where a
  reference is polymorphic (an expense/revenue/labour/health row's batch reference can
  point at either `pig_batches` or `poultry_batches` depending on `domain`, and Postgres
  can't declare a FK across two possible tables), a new `_validate_batch_ref` helper does
  the check in application code instead. Every FK violation and every invalid-dropdown
  value (checked against `99_LISTS`) is caught, rolled back, and reported in
  `SyncReport.errors` rather than raised or silently dropped. Every sync is idempotent
  (upsert on each table's natural key).
- **The capstone**: `tests/test_sync_shared_core.py::test_feed_cost_split_by_domain_query_resolves_cleanly`
  promotes the prototype's SQLite query to run for real against Postgres and confirms 0 kg
  of feed usage left unpriced — the project's original motivating cross-domain question,
  now actually answerable from a real database.
- **`tests/test_sync_full_workbook.py`** is the acceptance test for the whole spec: runs
  the sync against the actual, fully-populated `Netrisyl_Farm_Intelligence_Workbook.xlsx`
  (not a fixture), asserts zero validation errors, checks every table's row count against
  the known generation counts, checks idempotency on a second run, and confirms all three
  planted findings are discoverable via SQL afterward.

### Two real bugs this surfaced (both fixed, both worth knowing about)

1. **Row 3 isn't always a discardable sample.** The original convention (row 1 =
   purpose note, row 2 = headers, row 3 = sample, row 4+ = data) holds for growing log
   tables, but `00_FARM_PROFILE` and `01_STAFF` are singleton/registry tabs where the real
   workbook's actual data starts at row 3: `00_FARM_PROFILE` has no row 4 at all (it's a
   one-farm-per-workbook singleton), and `01_STAFF`'s row 3 holds staff member `S01`,
   referenced 286 times by `04_LABOUR_LOG`. `read_tab_rows` gained a `min_row` parameter;
   `_sync_farm_profile` reads from row 3 and takes the *last* row found (so a test fixture
   with a sample-then-real-row pattern still resolves to the real one); `_sync_staff`
   reads from row 3 directly.
2. **`07_HEALTH_LOG`'s reference column is `batch_ref`, not `batch_code`.** Used the wrong
   name throughout `_sync_health_log` since ticket 05; my own test fixtures repeated the
   same wrong assumption, so nothing caught it until the sync ran against the real header
   row. Fixed in both the engine and the tests.

Neither bug was caught by 47 passing fixture-based tests across tickets 01–05 — both only
surfaced once the sync ran against real, fully-populated data in ticket 06. Worth
remembering next time a fixture-only test suite feels "done": fixtures only test what you
thought to model.

## Open items — unresolved, don't assume either way

- **`~/.claude/settings.json` question still never answered.** A request came in
  mid-session (several sessions ago now) to set
  `permissions.blockReadsOutsideWorkingDirectories` from `true` to `false` (a global, not
  project-scoped, sandboxing setting). It's still `true` — confirmed unchanged as of this
  update. Ask before touching it; it weakens a security boundary for all future sessions
  on this machine, not just this project.
- **Previously-flagged leftover files are gone.** The duplicate
  `Netrisyl_Farm_Intelligence_Workbook_generated.xlsx` and the `~$...` Office lock file
  that were flagged in earlier versions of this doc are no longer present — checked as of
  this update. No action needed.

## Key facts about the workbook (reference, don't re-derive)

- 23 tabs: `README`, `99_LISTS`, `00_FARM_PROFILE`, `01_STAFF`, `02_EXPENSES`,
  `03_REVENUE`, `04_LABOUR_LOG`, `05_WEATHER_LOG`, `06_FEED_INVENTORY`, `07_HEALTH_LOG`,
  `P1`–`P5` (piggery), `C1`–`C3` (poultry), `F1`–`F5` (crops).
- Row convention: row 1 = purpose/cadence note, row 2 = headers, row 3 = sample, row 4+ =
  data — **except** `00_FARM_PROFILE` and `01_STAFF`, where row 3 holds real data (see
  the bugs above). Never touch rows 1–3 when writing to the workbook itself.
- Formula-bearing columns in the workbook that must stay formulas, never hardcoded values,
  if writing to the `.xlsx` directly: `02_EXPENSES.total_cost`, `03_REVENUE.total_amount`,
  `04_LABOUR_LOG.labour_cost`, `P2_PIG_DAILY_LOG.closing_count`,
  `P3_PIG_WEIGHTS.age_days`, `P5_BREEDING_FARROWING.expected_farrow_date`,
  `F5_HARVEST_LOG.quantity_kg`. (The sync engine reads the workbook with
  `data_only=True` and assumes it's already been recalculated — see below — so this only
  matters if something writes to the spreadsheet again.)
- Recalculation status: confirmed clean via LibreOffice in a separate session — 1,876
  formulas recalculated, 0 errors. Not re-verified since, but nothing in this session
  wrote new formulas to the workbook.
- Three planted findings, all confirmed independently queryable from the synced Postgres
  tables in `test_three_planted_findings_are_discoverable_after_sync`:
  - Poultry batch `BRO-P02` — heatwave-linked mortality spike (worst of all batches,
    >5% vs <2% for the others).
  - Pig batch `PIG-B02` — disease outbreak in `07_HEALTH_LOG` (Inspection → Treatment ×3
    → Recovered), 2026-04-25→05-05.
  - Crop sale (soyabean, `SB-PL2-25A` / product `Soyabean`) — still `payment_status =
    Owing`, unresolved at window end.
- `gen_scripts/` contents (data generation, separate from the sync engine):
  `generate_data.py` (full 23-tab generator, seed=42), `write_workbook.py`, `verify.py`,
  `regenerate_feed_inventory.py` (targeted regenerator used for the grain fix), and
  `Netrisyl_Farm_Intelligence_Workbook.original_backup.xlsx` (pristine template).
- `sync/` contents (new this session): `engine.py` (`sync_workbook_to_supabase` and all
  20 per-table sync functions), `workbook_reader.py` (`read_tab_rows`,
  `read_list_values`). `tests/` holds 50 tests across 6 files, plus `fixtures.py` and
  `workbook_builder.py` (shared test-fixture helpers).
- `spec-supabase-sync.md` and `.scratch/supabase-sync/issues/01`–`06` are the spec and
  tickets that drove this build — read them for the full acceptance criteria and design
  decisions rather than re-deriving from the code.

## Ultimate goal (stated by user)

Build a chatbot prototype on top of this farm data, able to answer cross-domain questions
(feed cost split, P&L by domain, "what's wrong with my farm" surfacing the three planted
findings). **The data layer for this is now done and tested** — a real Postgres database,
synced from the workbook, that answers the feed-cost question correctly. What's not built
yet: the natural-language layer itself (question → SQL → answer), any actual Supabase
cloud deployment (everything so far runs against a local Postgres instance), and the
chatbot's UI/interface.

## Suggested skills for the next session

- **mattpocock-skills:to-spec** / **to-tickets** — if the next concrete piece of work
  (e.g. "the chatbot's question-answering layer" or "deploy this to real Supabase") is
  well-understood enough to spec and break down the same way this sync was.
- **mattpocock-skills:grilling** — if the chatbot's architecture (which LLM, how it turns
  a question into SQL, how it's hosted) needs stress-testing before committing to a spec.
- **mattpocock-skills:tdd** — for building the chatbot layer itself, following the same
  seam-first discipline used here (`sync_workbook_to_supabase` was the one seam for this
  entire spec; the chatbot will need its own seam agreed before writing its first test).
- **code-review** or **simplify** — the sync engine has 20 near-identical per-table sync
  functions (schema + upsert + validation) that could likely be collapsed behind a
  smaller, table-driven abstraction now that the pattern is fully proven across 6
  tickets; worth a look before adding much more to `sync/engine.py` as-is. This wasn't
  done during the TDD loop on purpose — refactoring is explicitly a separate step from
  the red→green cycle per the TDD skill.
- **mattpocock-skills:domain-modeling** — if formalizing the workbook's domain
  vocabulary (a `CONTEXT.md` or ADR) makes sense now that the schema has been through two
  real design fixes (the feed_inventory grain, and the two bugs ticket 06 found).
