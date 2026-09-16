# Handoff: Farm Intelligence App

Session focus: turning a 23-tab Netrisyl Farm Intelligence Google Sheets workbook into a
populated demo dataset, validating its schema design via a prototype, fixing the data-model
issue that surfaced, writing and fully implementing a spec to sync the workbook into
Postgres, then standing up a real Supabase cloud project and pointing the sync at it —
landing a working, tested pipeline that answers the project's original motivating question
("how does feed cost split between pigs and chickens") for real, in the cloud.

## Repo state

- Working dir: `/Users/vharsh/Farm-Intelligence-App` — git repo, initialized mid-session.
- Remote: `https://github.com/SYLVESTER1922/FARM_INTELLIGENCE.git` (`origin`). Both
  `main` and `prototype/supabase-domain-join-test` are pushed and tracking their remote
  counterparts.
- `main` branch, commits in order:
  - `d4cdbaa` — initial workbook + 12 months of synthetic data + generation scripts.
  - `21bd86e` — fix to `06_FEED_INVENTORY` grain (domain+feed_type+week).
  - `59f45f2` / `1fd685e` — session handoff doc (this file) and a correction to it.
  - `0bbdf46` — `spec-supabase-sync.md`: the spec for syncing the workbook into Supabase.
  - `daaf0a6` — six local tickets under `.scratch/supabase-sync/issues/` (no issue
    tracker configured; solo/two-person project, tracker setup explicitly declined).
  - `07e0c1b` → `fda9117` — tickets 01 through 06, all implemented test-first and marked
    `done`. The sync spec is fully implemented.
  - `c3709f2` — handoff doc updated for spec completion.
  - `2ec2fd3` / `13d5a83` — gitignore entries for `.env.supabase` and `supabase/` (see
    below).
- Throwaway branch `prototype/supabase-domain-join-test` (`447dbec`) — the SQLite
  prototype that first found the feed_inventory grain issue. Deliberately not merged into
  `main` (prototypes are a primary source kept on their own branch here).
- Working tree is clean.

## What's been built: the sync engine

`sync/engine.py` + `sync/workbook_reader.py` sync the entire real workbook (all 23 tabs)
into Postgres through one public seam: `sync_workbook_to_supabase(filepath, farm_code,
dsn) -> SyncReport`. Built test-first (TDD skill, one seam agreed at the spec stage and
reused for every ticket) against a real local Postgres 16 instance. 50 tests, all
passing, in `tests/`.

- **Local environment**: Homebrew + `postgresql@16` installed via Homebrew, running as a
  `brew services` launch agent. Test database `farm_intelligence_test`, local trust auth.
  Project-local virtualenv at `.venv/` (`psycopg[binary]`, `pytest`, `openpyxl`). Run
  tests with `source .venv/bin/activate && python -m pytest tests/`.
- **What's synced**: all 23 tabs — farm profile, staff, `99_LISTS` (as a generic
  `list_values` reference table), all 5 piggery tabs, all 3 poultry tabs, all 5 crop
  tabs, and all 6 shared-core tabs.
- **Key design decisions**: `06_FEED_INVENTORY` synced at `domain + feed_type + week`
  grain (not `domain + week`) — the fix that makes the feed-cost-split query resolve
  cleanly. Real Postgres FK constraints where a single target table exists; a
  `_validate_batch_ref` helper for polymorphic references (a batch reference that could
  point at either `pig_batches` or `poultry_batches` depending on `domain`) that a single
  hard FK can't express. Every FK violation and invalid-dropdown value is caught and
  reported in `SyncReport.errors`, never raised or silently dropped. Every sync is
  idempotent.
- **The capstone**: the feed-cost-split-by-domain query (originally the prototype's
  SQLite query) resolves with 0 kg of feed usage left unpriced — proven both in
  `tests/test_sync_shared_core.py` (local Postgres) and, this session, against the real
  Supabase project (see below).
- **`tests/test_sync_full_workbook.py`**: the acceptance test for the whole spec — runs
  the sync against the actual, fully-populated workbook (not a fixture), checks zero
  errors, every table's row count, idempotency, and all three planted findings.

### Two real bugs the full-workbook regression found (both fixed)

1. **Row 3 isn't always a discardable sample.** `00_FARM_PROFILE` and `01_STAFF` are
   singleton/registry tabs where the real workbook's data genuinely starts at row 3 —
   `00_FARM_PROFILE` has no row 4 at all, and `01_STAFF`'s row 3 holds staff member `S01`,
   referenced 286 times by `04_LABOUR_LOG`. `read_tab_rows` gained a `min_row` parameter;
   `_sync_farm_profile` takes the *last* row from row 3 onward, `_sync_staff` reads from
   row 3 directly.
2. **`07_HEALTH_LOG`'s reference column is `batch_ref`, not `batch_code`.** Wrong name
   used throughout `_sync_health_log` since ticket 05; my own fixtures repeated the same
   mistake, so nothing caught it until the sync hit the real header row.

Neither was caught by 47 passing fixture-based tests — both only surfaced against real,
fully-populated data. Worth remembering: fixtures only test what you thought to model.

## Supabase cloud deployment (this session, after the spec was already complete)

The sync is now pointed at a **real Supabase cloud project**, not just local Postgres.

- **Project**: `farm-intelligence`, ref `bfetyunxnmqfvtiqirsr`, region `us-west-2`, org
  `gwemzvnyvfifialranlt`. Created via the `supabase` CLI (installed via Homebrew,
  `2.117.0`).
- **Auth note**: the Supabase CLI's OAuth login flow doesn't work in this sandboxed
  environment at all (no TTY, even when the user runs it themselves) — only a personal
  access token works, via `SUPABASE_ACCESS_TOKEN` env var or `~/.supabase_access_token`.
  **Incident**: the user's first token was pasted directly into the chat (as part of a
  shell command), exposing it in the conversation transcript. It was flagged immediately,
  the user revoked it and generated a replacement, saved safely thereafter (confirmed
  working, never printed). Going forward: credentials should be saved to local files by
  the user directly in their own terminal, never typed into a message here.
- **Project-limit note**: the account is on the free tier with a 2-active-project cap.
  Creating `farm-intelligence` required pausing an existing project first — `JCC-Chatbot`
  (ref `gsdvxywkbhthrjhmffnm`, org `gwemzvnyvfifialranlt`) was paused via the Supabase
  Management API (`POST /v1/projects/{ref}/pause`) with the user's explicit go-ahead.
  **`JCC-Chatbot` is still paused** — the user was later asked whether to unpause it
  (which would require pausing something else, since the limit is still 2) and chose to
  leave it paused for now. Revisit this if `JCC-Chatbot` is needed again: either pause
  `farm-intelligence` or another project to swap it back in, or upgrade the plan.
- **Verified working**: ran `sync_workbook_to_supabase` against the real workbook and
  this real project — **zero errors**, every table's row count matching exactly (same
  counts as the local-Postgres regression: `staff: 4`, `feed_inventory: 105`,
  `labour_log: 1143`, etc., `list_values: 195`). Also re-ran the feed-cost-split query
  directly against Supabase: 0 kg unpriced for both domains, `piggery` feed_cost
  ≈$10,000.46, `poultry` ≈$4,781.46. Spot-checked the crop debtor finding too — it's
  there (`product='Soya'`, buyer `Chikafu Grain Traders`, `payment_status='Owing'`,
  `batch_ref='SB-PL2-25A'`) — note the real product name is `"Soya"`, not `"Soyabean"` as
  written in some earlier notes; the ticket 06 test correctly matched on `batch_ref`
  instead, so it wasn't affected.
- **Credentials, where they live** (none of this is committed):
  - `~/.supabase_access_token` — personal access token, used for CLI/Management-API
    calls (project create/pause/restore, listing projects, etc.).
  - `~/.supabase_farm_db_password` — the generated DB password for the
    `farm-intelligence` project's `postgres` role.
  - `.env.supabase` (project root, gitignored) — `SUPABASE_PROJECT_REF` and
    `SUPABASE_DB_DSN` (a full libpq DSN string including the password), ready to pass as
    the `dsn` argument to `sync_workbook_to_supabase`.
  - `supabase/` (project root, gitignored) — CLI-local state only (linked project ref,
    version cache), not meaningful to version.
- **Running the sync against Supabase again**, from the project root:
  ```python
  from sync.engine import sync_workbook_to_supabase
  with open(".env.supabase") as f:
      for line in f:
          if line.startswith("SUPABASE_DB_DSN="):
              dsn = line.strip().split("=", 1)[1]
  report = sync_workbook_to_supabase("Netrisyl_Farm_Intelligence_Workbook.xlsx",
                                      farm_code="NIS-001", dsn=dsn)
  ```
  Expect this to take noticeably longer than the local-Postgres tests (each of the
  ~2,600 rows is now a network round trip to `us-west-2`, not a unix socket) — it ran as
  a background task last time rather than completing within a normal command timeout.

## Open items — unresolved, don't assume either way

- **`~/.claude/settings.json` question still never answered.** A request came in
  several sessions ago to set `permissions.blockReadsOutsideWorkingDirectories` from
  `true` to `false` (a global, not project-scoped, sandboxing setting). Still `true` as
  of this update. Ask before touching it.
- **`JCC-Chatbot` Supabase project is paused** (see above) — the user knows and chose to
  leave it that way for now, but it's still a state change to an unrelated project worth
  surfacing to whoever picks this up next.

## Key facts about the workbook (reference, don't re-derive)

- 23 tabs: `README`, `99_LISTS`, `00_FARM_PROFILE`, `01_STAFF`, `02_EXPENSES`,
  `03_REVENUE`, `04_LABOUR_LOG`, `05_WEATHER_LOG`, `06_FEED_INVENTORY`, `07_HEALTH_LOG`,
  `P1`–`P5` (piggery), `C1`–`C3` (poultry), `F1`–`F5` (crops).
- Row convention: row 1 = purpose/cadence note, row 2 = headers, row 3 = sample, row 4+ =
  data — **except** `00_FARM_PROFILE` and `01_STAFF`, where row 3 holds real data (see
  the bugs above). Never touch rows 1–3 when writing to the workbook itself.
- Formula-bearing columns that must stay formulas if writing to the `.xlsx` directly:
  `02_EXPENSES.total_cost`, `03_REVENUE.total_amount`, `04_LABOUR_LOG.labour_cost`,
  `P2_PIG_DAILY_LOG.closing_count`, `P3_PIG_WEIGHTS.age_days`,
  `P5_BREEDING_FARROWING.expected_farrow_date`, `F5_HARVEST_LOG.quantity_kg`. (The sync
  engine reads with `data_only=True` and assumes an already-recalculated file.)
- Recalculation status: confirmed clean via LibreOffice in a separate session — 1,876
  formulas, 0 errors. Nothing since has written new formulas to the workbook.
- Three planted findings, all confirmed queryable from both local Postgres and the real
  Supabase project:
  - Poultry batch `BRO-P02` — heatwave-linked mortality spike (worst of all batches).
  - Pig batch `PIG-B02` — disease outbreak in `07_HEALTH_LOG`, 2026-04-25→05-05.
  - Crop sale, product `Soya` (not `Soyabean`), `batch_ref='SB-PL2-25A'`, buyer Chikafu
    Grain Traders — still `payment_status='Owing'`.
- `gen_scripts/`: `generate_data.py` (full generator, seed=42), `write_workbook.py`,
  `verify.py`, `regenerate_feed_inventory.py`, `Netrisyl_Farm_Intelligence_Workbook.original_backup.xlsx`.
- `sync/`: `engine.py` (`sync_workbook_to_supabase` + 20 per-table sync functions),
  `workbook_reader.py`. `tests/`: 50 tests across 6 files plus shared fixture helpers.
- `spec-supabase-sync.md` and `.scratch/supabase-sync/issues/01`–`06` are the spec and
  tickets that drove the sync build.

## Ultimate goal (stated by user)

Build a chatbot prototype on top of this farm data, able to answer cross-domain questions
(feed cost split, P&L by domain, "what's wrong with my farm" surfacing the three planted
findings). **The data layer is now fully done, tested, and deployed**: a real Supabase
Postgres database, populated from the workbook, correctly answering the feed-cost
question. What's not built yet: the natural-language layer itself (question → SQL →
answer), and the chatbot's UI/interface.

## Suggested skills for the next session

- **mattpocock-skills:to-spec** / **to-tickets** — for the chatbot's question-answering
  layer, the same way the sync itself was spec'd and ticketed.
- **mattpocock-skills:grilling** — if the chatbot's architecture (which LLM, how it turns
  a question into SQL, how it's hosted, whether it talks to Supabase directly or through
  an API layer) needs stress-testing before committing to a spec.
- **mattpocock-skills:tdd** — for building the chatbot layer, following the same
  seam-first discipline used here.
- **code-review** or **simplify** — `sync/engine.py` has 20 near-identical per-table sync
  functions (schema + upsert + validation) that could likely collapse behind a smaller,
  table-driven abstraction now that the pattern is proven across 6 tickets. Deliberately
  not done during the TDD loop — refactoring is a separate step per the TDD skill.
- **mattpocock-skills:domain-modeling** — if formalizing the workbook's domain
  vocabulary (a `CONTEXT.md` or ADR) makes sense now that the schema has been through two
  real design fixes.
