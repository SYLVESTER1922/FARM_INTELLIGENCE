# 02: Sync piggery module (P1–P5)

**What to build:** The full piggery module — batch register, daily logs, weights, sow
register, and breeding/farrowing — synced into Supabase with referential integrity, so a
query against Postgres can answer real questions about pig batches (e.g. active batches
and their daily mortality) without touching the spreadsheet.

**Blocked by:** 01

**Status:** done

- [x] `P1_PIG_BATCHES`, `P2_PIG_DAILY_LOG`, `P3_PIG_WEIGHTS`, `P4_SOW_REGISTER`, and
      `P5_BREEDING_FARROWING` are synced via the shared engine from Ticket 01.
      (`_sync_pig_batches`, `_sync_pig_daily_log`, `_sync_pig_weights`,
      `_sync_sow_register`, `_sync_breeding_farrowing` in `sync/engine.py`)
- [x] Foreign key constraints enforce `P2`/`P3` → `P1` (`batch_code`) and `P5` → `P4`
      (`sow_tag`); `P5.litter_batch_code` resolves against `P1` where present.
      (real Postgres FK constraints; violations caught and turned into report errors
      rather than raised — see `_sync_pig_daily_log`'s `ForeignKeyViolation` handling)
- [x] Formula-derived columns (`P2.closing_count`, `P3.age_days`,
      `P5.expected_farrow_date`) are synced as their resolved values, never as formula
      text — inherent to reading the workbook with `data_only=True` against an
      already-recalculated file (per the spec's stated assumption).
- [x] A daily-log row referencing a nonexistent `batch_code` is rejected and reported.
      (`tests/test_sync_piggery.py::test_sync_rejects_daily_log_row_with_unknown_batch`)
- [x] A query against the synced tables correctly answers "which pig batches are active,
      and what's their daily mortality" for a fixture workbook.
      (`test_active_pig_batches_and_daily_mortality_are_queryable`)
- [x] Idempotency holds for all five tables (re-running the sync produces no duplicates).
      (`test_sync_is_idempotent_across_piggery_tables`)
