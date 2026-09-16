# Handoff: Farm Intelligence App

Session focus: turning a 23-tab Netrisyl Farm Intelligence Google Sheets workbook into a
populated demo dataset, validating its schema design for a future chatbot/Supabase backend,
and fixing a data-model issue the validation surfaced.

## Repo state

- Working dir: `/Users/vharsh/Farm-Intelligence-App` — git repo, initialized this session.
- `main` branch, 2 commits:
  - `d4cdbaa` — initial workbook + 12 months of synthetic data + generation scripts.
  - `21bd86e` — fix to `06_FEED_INVENTORY` grain (see below).
- Throwaway branch `prototype/supabase-domain-join-test` (`447dbec`) — holds the SQLite
  prototype that found the feed_inventory issue. Deliberately not merged into `main`
  (per this repo's prototype convention: prototypes are a primary source kept on their
  own branch, not folded into main).
- Working tree is clean as of end of session.

## What's been done, in order

1. **Grilled the synthetic-data plan** (via `/grill-me`). Locked scope: trailing 12 months
   (Oct 2025–Sep 2026, ending "today" = 2026-09-15), specific batch/plot counts per module,
   a 4-person staff roster (S01–S04), and three deliberately planted findings (see below).
   Full spec was given inline by the user in chat, not saved to a separate file.

2. **Populated the workbook** via a forked subagent writing directly into the `.xlsx` with
   openpyxl (formulas preserved, not hardcoded). Two redirects were needed mid-task: the
   agent first burned time on an unrelated "formula-engine speed test," and later needed to
   be told to work inside the project folder instead of `/tmp`. End result: 2,598 rows
   across 23 tabs, seed=42. Full generation logic: `gen_scripts/generate_data.py`.

   **Recalculation gap — now resolved.** At the time this doc was first written, no real
   spreadsheet engine had recalculated the file (`/mnt/skills/public/xlsx/scripts/recalc.py`
   doesn't exist on this machine — bare macOS host, not the expected container — and there
   was no LibreOffice/Excel to shell out to; formula correctness had only been checked by a
   manual Python replica of each formula's logic in `gen_scripts/verify.py`). This has since
   been run separately, via LibreOffice in a different Claude session, against the fully
   populated workbook: **1,876 formulas recalculated, 0 errors.** No further action needed
   here.

3. **Ran `/prototype`** to test whether the workbook's "shared-core-plus-domain-module"
   table design supports real cross-domain SQL joins (motivated by the eventual Supabase
   sync). No Docker/Homebrew/Postgres/Supabase CLI exists on this machine and installing
   Homebrew system-wide was judged too much footprint for a throwaway test, so the
   prototype used SQLite as a stand-in. **Finding**: joining `06_FEED_INVENTORY` to
   `P2_PIG_DAILY_LOG`/`C2_POULTRY_DAILY_LOG` on `(domain, feed_type)` left most usage
   unpriced, because `06_FEED_INVENTORY` only ever tracked one `feed_type` per domain per
   year, while the daily logs record every growth-stage feed_type. Full writeup and query:
   see branch `prototype/supabase-domain-join-test`, file `prototype_supabase_sync.py`.

4. **Fixed the data model** (not the query, per user's explicit instruction). Rewrote
   `06_FEED_INVENTORY` at `domain + feed_type + week` grain (105 rows, up from 75) via a
   new targeted script, `gen_scripts/regenerate_feed_inventory.py`, which reads the *live*
   daily logs as source of truth. Verified the join now resolves with 0 kg unpriced.
   `gen_scripts/generate_data.py` was also updated so a future full regeneration stays
   consistent with this fix. Confirmed all other 22 tabs are byte-identical before/after —
   only `06_FEED_INVENTORY`'s data and the sheet's own CADENCE note changed. Committed as
   `21bd86e` on `main`.

## Open items — unresolved, don't assume either way

- **`~/.claude/settings.json` question never answered.** Mid-session, a request came in to
  set `permissions.blockReadsOutsideWorkingDirectories` from `true` to `false` (a global,
  not project-scoped, sandboxing setting). It surfaced while a background subagent was
  stuck, but the task completed without needing the change, so it was left at `true`. The
  user never confirmed whether they still want it changed — ask before touching it, since
  it weakens a security boundary for all future sessions on this machine, not just this
  project.
- **Possible leftover file.** A duplicate `Netrisyl_Farm_Intelligence_Workbook_generated.xlsx`
  was flagged mid-session as safe to delete (identical to the live file at that point), but
  the user never confirmed and it wasn't checked again afterward. Verify whether it's still
  in the project root before assuming either way.
- **Office lock file seen once.** A `~$Netrisyl_Farm_Intelligence_Workbook.xlsx` lock file
  was observed at one point, suggesting Excel may have had the workbook open concurrently
  with automated edits. Worth a sanity check for corruption if that's still the case.

## Key facts about the workbook (reference, don't re-derive)

- 23 tabs: `README`, `99_LISTS`, `00_FARM_PROFILE`, `01_STAFF`, `02_EXPENSES`,
  `03_REVENUE`, `04_LABOUR_LOG`, `05_WEATHER_LOG`, `06_FEED_INVENTORY`, `07_HEALTH_LOG`,
  `P1`–`P5` (piggery), `C1`–`C3` (poultry), `F1`–`F5` (crops).
- Row convention on every tab: row 1 = purpose/cadence/entered-by note, row 2 = headers,
  row 3 = sample row, row 4+ = data. **Never touch rows 1–3.**
- Formula-bearing columns that must stay formulas, never hardcoded values:
  `02_EXPENSES.total_cost`, `03_REVENUE.total_amount`, `04_LABOUR_LOG.labour_cost`,
  `P2_PIG_DAILY_LOG.closing_count`, `P3_PIG_WEIGHTS.age_days`,
  `P5_BREEDING_FARROWING.expected_farrow_date`, `F5_HARVEST_LOG.quantity_kg`.
- Three planted findings for the eventual chatbot demo:
  - Poultry batch `BRO-P02` — heatwave-linked mortality spike (8.1% vs ~0% for other batches).
  - Pig batch `PIG-B02` — disease outbreak in `07_HEALTH_LOG`, 2026-04-25→05-05.
  - Crop sale `SB-PL2-25A` (soyabean, to Chikafu Grain Traders, 2026-03-28) — still
    `payment_status = Owing` at window end (2026-09-15).
- `gen_scripts/` contents: `generate_data.py` (full 23-tab generator, seed=42),
  `write_workbook.py`, `verify.py`, `regenerate_feed_inventory.py` (targeted, tab-scoped
  regenerator), and `Netrisyl_Farm_Intelligence_Workbook.original_backup.xlsx` (pristine
  template before any generation, kept for reference).

## Ultimate goal (stated by user, not yet built)

Build a chatbot prototype on top of this farm data, eventually synced into Supabase, able
to answer cross-domain questions (e.g. "how does feed cost split between pigs and
chickens," P&L by domain, "what's wrong with my farm" surfacing the three planted findings).
Nothing beyond the SQLite prototype and the workbook itself has been built toward this yet.

## Suggested skills for the next session

- **mattpocock-skills:prototype** — if the next step is testing another design question
  before committing to real code (e.g. the P&L-by-domain join, or a chatbot UI mockup).
- **mattpocock-skills:domain-modeling** — if formalizing the workbook's domain model/
  vocabulary (a CONTEXT.md or ADR) makes sense now that the schema has been through one
  real design fix.
- **mattpocock-skills:tdd** — once real chatbot/sync implementation code (not a throwaway
  prototype) starts getting built.
- **mattpocock-skills:grilling** — if the user wants to stress-test the next phase (e.g. an
  actual Supabase migration plan, or chatbot architecture) before building it.
