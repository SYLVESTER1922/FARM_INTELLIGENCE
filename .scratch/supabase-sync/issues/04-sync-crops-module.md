# 04: Sync crops module (F1–F5)

**What to build:** The full crops module — plots, plantings, field operations, scouting,
and harvest — synced into Supabase with referential integrity, so a query against Postgres
can answer real questions about a planting's full input-to-harvest history without
touching the spreadsheet.

**Blocked by:** 01

**Status:** done

- [x] `F1_PLOTS`, `F2_PLANTINGS`, `F3_FIELD_OPERATIONS`, `F4_SCOUTING_LOG`, and
      `F5_HARVEST_LOG` are synced via the shared engine from Ticket 01.
      (`_sync_plots`, `_sync_plantings`, `_sync_field_operations`,
      `_sync_scouting_log`, `_sync_harvest_log` in `sync/engine.py`)
- [x] Foreign key constraints enforce `F2` → `F1` (`plot_code`) and `F3`/`F4`/`F5` → `F2`
      (`planting_code`).
      (real Postgres FK constraints; violations caught and reported, same pattern
      as tickets 02/03)
- [x] The formula-derived column `F5.quantity_kg` is synced as its resolved value, never
      as formula text — inherent to reading with `data_only=True` against an
      already-recalculated file.
- [x] A field-operation, scouting, or harvest row referencing a nonexistent
      `planting_code` is rejected and reported.
      (tested individually for all three: `test_sync_rejects_field_operation_row_with_unknown_planting`,
      `test_sync_rejects_scouting_log_row_with_unknown_planting`,
      `test_sync_rejects_harvest_log_row_with_unknown_planting`)
- [x] A query against the synced tables correctly reconstructs a planting's full
      input-to-harvest history for a fixture workbook.
      (`test_planting_input_to_harvest_history_is_queryable`)
- [x] Idempotency holds for all five tables.
      (`test_sync_is_idempotent_across_crop_tables`)
