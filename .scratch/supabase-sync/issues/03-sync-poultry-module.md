# 03: Sync poultry module (C1–C3)

**What to build:** The full poultry module — flock register, daily logs, and weights —
synced into Supabase with referential integrity, so a query against Postgres can answer
real questions about broiler batch performance without touching the spreadsheet.

**Blocked by:** 01

**Status:** done

- [x] `C1_POULTRY_BATCHES`, `C2_POULTRY_DAILY_LOG`, and `C3_POULTRY_WEIGHTS` are synced
      via the shared engine from Ticket 01.
      (`_sync_poultry_batches`, `_sync_poultry_daily_log`, `_sync_poultry_weights`
      in `sync/engine.py`)
- [x] Foreign key constraints enforce `C2`/`C3` → `C1` (`batch_code`).
      (real Postgres FK constraints; violations caught and reported, same pattern
      as the piggery module in ticket 02)
- [x] A daily-log row referencing a nonexistent `batch_code` is rejected and reported.
      (`tests/test_sync_poultry.py::test_sync_rejects_poultry_daily_log_row_with_unknown_batch`,
      and the same proven for `poultry_weights` too)
- [x] A query against the synced tables correctly answers "broiler batch performance"
      (mortality, feed use, weight trend) for a fixture workbook.
      (`test_broiler_batch_performance_is_queryable`)
- [x] Idempotency holds for all three tables.
      (`test_sync_is_idempotent_across_poultry_tables`)
