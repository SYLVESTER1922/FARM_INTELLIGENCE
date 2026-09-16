# Spec: Sync Netrisyl Farm Intelligence Workbook to Supabase

## Problem Statement

The farm owner's operational data — piggery, poultry, and crop records for Chiedza Mixed
Farm (NIS-001) — lives entirely in a 23-tab Google Sheets workbook. A prototype already
showed that a relational store can answer cross-domain questions (like "how does feed cost
split between pigs and chickens") once the schema is right, but there is no actual path
today from "data entered in the spreadsheet" to "data a chatbot can query." Every time the
farm owner updates the sheet, there's no repeatable way to get that update into a database.

## Solution

Build a sync that reads the whole workbook and loads it into Supabase (Postgres), using a
schema that mirrors the workbook's own tabs and columns, preserving the
shared-core-plus-domain-module design already validated by the prototype (shared-core
tables carry a `domain` column as the cross-domain join key; `06_FEED_INVENTORY` logs at
`domain + feed_type + week` grain, not just `domain + week`). The sync is the single,
testable boundary between the spreadsheet and everything downstream of it, and can be
re-run safely whenever the workbook changes.

## User Stories

1. As a farm owner, I want my Google Sheets workbook data available in a queryable
   database, so that a chatbot can answer questions about my farm without me exporting or
   copying data manually.
2. As a farm owner, I want to re-run the sync after I update the sheet, so that the
   chatbot always reflects my latest entries.
3. As a developer, I want the sync to fail loudly and specifically when a row references an
   invalid dropdown value, so that bad data entry doesn't silently corrupt the database.
4. As a developer, I want the sync to be idempotent, so that running it twice against the
   same workbook doesn't create duplicate rows.
5. As a developer, I want each tab's natural key (`batch_code`, `planting_code`,
   `staff_code`, `sow_tag`, or a composite key like `date + domain + feed_type` for weekly
   logs) enforced as a unique constraint, so upserts behave predictably.
6. As a developer, I want the sync to preserve the shared-core-plus-domain-module schema
   validated by the prototype, so cross-domain joins work without ad hoc reshaping at query
   time.
7. As a chatbot backend, I want a `domain` column on every shared-core table (expenses,
   revenue, labour log, feed inventory), so I can filter and group cross-domain questions.
8. As a chatbot backend, I want `06_FEED_INVENTORY` synced at `domain + feed_type + week`
   grain, so feed-cost queries resolve without leaving usage unpriced.
9. As a farm owner, I want the sync to cover all 23 tabs across core, piggery, poultry, and
   crops, so no module is left unqueryable.
10. As a developer, I want dropdown-constrained columns (`domain`, `category`,
    `payment_status`, `feed_type`, and the rest of the `99_LISTS` vocabulary) validated
    against `99_LISTS` at sync time, so invalid categories are caught before they reach the
    database.
11. As a farm owner, I want date-typed columns (`date`, `service_date`,
    `expected_farrow_date`, etc.) converted to real Postgres date/timestamp types, so date
    arithmetic and range queries work correctly — the raw workbook has at least one
    text-typed date cell today (`P5_BREEDING_FARROWING.expected_farrow_date`) that the sync
    must not carry forward as text.
12. As a developer, I want formula-derived columns (`total_cost`, `total_amount`,
    `labour_cost`, `closing_count`, `age_days`, `expected_farrow_date`, `quantity_kg`)
    synced as their resolved values, never as formula strings, so the database only ever
    contains queryable data.
13. As a chatbot backend, I want referential integrity enforced at the database level
    (daily logs to batch/planting registers, expenses/revenue to `batch_ref`), so a broken
    reference is caught at sync time rather than silently producing nulls in a join.
14. As a farm owner, I want a sync report (rows written per tab, any validation errors)
    after each run, so I know the sync succeeded before trusting the chatbot's answers.
15. As a developer, I want the sync tested against a known fixture workbook, so its
    correctness doesn't depend on manually spot-checking every run.
16. As a developer, I want the sync's tests to assert on the resulting database state and
    on cross-domain query results, not on internal sync implementation details, so the
    tests stay valid if the sync's internals change.
17. As a farm owner, I want the sync to key data by `farm_code` (from `00_FARM_PROFILE`)
    rather than assume a single farm forever, so the design doesn't need reworking when a
    second farm onboards.
18. As a developer, I want `99_LISTS` dropdown values synced into their own reference
    table(s), so the database enforces the same category vocabulary the spreadsheet's data
    validation does.
19. As a chatbot backend, I want a documented, stable mapping from workbook tab names to
    database table names, so queries written against the database don't need to guess at
    naming.
20. As a developer, I want the sync's failure modes (missing `99_LISTS` value, broken
    `batch_ref`, malformed date) distinguishable from each other in the sync report, so a
    farm owner or developer knows exactly what to fix.
21. As a chatbot backend, I want `00_FARM_PROFILE`'s `module_piggery_active` /
    `module_poultry_active` / `module_crops_active` flags synced faithfully, so a
    downstream chatbot can refuse to answer for a module the farm has switched off (the
    workbook's own stated purpose for that row).
22. As a farm owner, I want the three known "findings" batches/records (the poultry
    mortality spike, the piggery disease outbreak, the unpaid crop debtor) to remain
    discoverable via SQL after sync, so the chatbot demo continues to work end to end.

## Implementation Decisions

- **Seam**: a single entry point, `syncWorkbookToSupabase(filePath, farmCode)`, is the one
  tested boundary. It orchestrates reading all 23 tabs and upserting them; nothing calls
  into per-tab sync functions independently from outside this seam.
- **Schema shape**: one Postgres table per workbook tab, columns matching the tab's header
  row 1:1 (already snake_case in the workbook, e.g. `batch_code`, `feed_type`).
- **`06_FEED_INVENTORY` grain**: `domain + feed_type + week_start_date`, not
  `domain + week_start_date`. This came directly out of the prototype
  (`prototype/supabase-domain-join-test` branch, `prototype_supabase_sync.py`): joining on
  `domain + feed_type` against a domain-only feed_inventory grain left most daily-log usage
  unpriced. The workbook itself was already fixed to this grain (commit `21bd86e` on
  `main`, via `gen_scripts/regenerate_feed_inventory.py`) — the sync just needs to preserve
  it, not re-derive it.
- **Cross-domain join key**: shared-core tables (`02_EXPENSES`, `03_REVENUE`,
  `04_LABOUR_LOG`, `06_FEED_INVENTORY`) keep `domain` as a plain column, used as the primary
  filter/group key for cross-domain questions.
- **Domain-module anchors**: `P1`–`P5` (piggery), `C1`–`C3` (poultry), `F1`–`F5` (crops)
  each anchor on their own natural key (`batch_code`, `planting_code`, `sow_tag`); shared-
  core tables reference these via `batch_ref` (nullable — not every expense or revenue line
  ties to a batch).
- **Dropdown validation**: every categorical column is checked against its `99_LISTS`
  column at sync time; a row with a value not present there is rejected and reported, not
  silently written.
- **Formula handling**: formula-bearing columns
  (`02_EXPENSES.total_cost`, `03_REVENUE.total_amount`, `04_LABOUR_LOG.labour_cost`,
  `P2_PIG_DAILY_LOG.closing_count`, `P3_PIG_WEIGHTS.age_days`,
  `P5_BREEDING_FARROWING.expected_farrow_date`, `F5_HARVEST_LOG.quantity_kg`) are synced
  using their resolved values from an already-recalculated workbook, never as raw formula
  text.
- **Referential integrity**: enforced via foreign key constraints from daily-log/weight/
  scouting/harvest tables to their anchor registers, and from `batch_ref` columns to
  whichever registry's `batch_code`/`planting_code` matches.
- **Idempotency**: every table has a natural-key (or composite-key) unique constraint; the
  sync performs upsert-on-conflict rather than append-only inserts.
- **Multi-farm readiness**: every table carries a `farm_code` column (sourced from
  `00_FARM_PROFILE`), rather than assuming a single-farm schema, so a second farm can be
  onboarded later without a schema redesign — this is the only forward-looking allowance in
  scope; no actual multi-tenancy (auth, isolation) is being built now.
- **Database target**: Supabase/Postgres. The prototype used SQLite purely as a stand-in to
  validate the join design (no Docker/Homebrew/Postgres was available on the dev machine at
  the time) — the real sync targets actual Postgres/Supabase, not SQLite.

## Testing Decisions

- Tests operate at the `syncWorkbookToSupabase` seam: feed in a fixture workbook, run the
  sync against a real (test) Postgres instance, then assert on the resulting database rows
  and on a small set of cross-domain SQL queries — not on internal parsing/mapping
  functions in isolation.
- **Prior art**: `prototype_supabase_sync.py` (branch `prototype/supabase-domain-join-test`)
  is the closest existing precedent — its strict-vs-relaxed join comparison and its
  three-finding spot-checks (poultry mortality spike, piggery disease outbreak, unpaid crop
  debtor) should become real test assertions against the actual sync, not just prototype
  output.
- **Fixture**: the already-generated Chiedza Mixed Farm workbook (or a trimmed-down subset
  of it) serves as the primary test fixture, since it already has known, documented
  findings baked in to assert against.
- **Negative-path tests**: a row with an invalid dropdown value must produce a reported
  error without being written; a daily-log row referencing a nonexistent `batch_code` must
  be caught the same way.
- **Idempotency test**: running the sync twice against an unchanged workbook produces
  identical row counts (no duplicates, no drift).

## Out of Scope

- The chatbot's natural-language layer (question → SQL → answer). This spec is only about
  getting the data into a queryable database.
- Multi-farm tenancy, auth, or per-farm schema isolation — only a `farm_code` column is in
  scope, not actual multi-tenant support.
- Live/real-time sync (e.g. a Google Sheets webhook triggering automatic re-sync) — the
  sync is manually triggered against a current `.xlsx` export.
- Writing back from the database to the spreadsheet — sync is one-directional, sheet to
  database only.
- Production Supabase concerns (RLS policies, auth, edge functions, deployment/ops).
- Recalculating the workbook's own formulas — already handled and confirmed clean
  separately (1,876 formulas, 0 errors, per `handoff-farm-intelligence-app.md`). The sync
  assumes it receives an already-recalculated file.

## Further Notes

- This spec builds directly on two settled decisions from this project's history and
  treats them as given, not open for re-litigation during implementation: the
  shared-core-plus-domain-module join design (validated on
  `prototype/supabase-domain-join-test`), and the `06_FEED_INVENTORY` grain fix (`main`,
  commit `21bd86e`).
- The full workbook schema (23 tabs, the row-1/row-2/row-3/row-4+ convention, the list of
  formula-bearing columns) is already documented in `handoff-farm-intelligence-app.md` at
  the project root — refer to it rather than re-deriving the schema from the workbook again.
- No issue tracker is configured for this project (solo/two-person prototype stage), so
  this spec is a standalone file, not published anywhere. If the project grows a team
  workflow later, running `/setup-matt-pocock-skills` and republishing this spec to a
  tracker with the `ready-for-agent` label would be the natural next step.
