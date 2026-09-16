# 04: Sync crops module (F1–F5)

**What to build:** The full crops module — plots, plantings, field operations, scouting,
and harvest — synced into Supabase with referential integrity, so a query against Postgres
can answer real questions about a planting's full input-to-harvest history without
touching the spreadsheet.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] `F1_PLOTS`, `F2_PLANTINGS`, `F3_FIELD_OPERATIONS`, `F4_SCOUTING_LOG`, and
      `F5_HARVEST_LOG` are synced via the shared engine from Ticket 01.
- [ ] Foreign key constraints enforce `F2` → `F1` (`plot_code`) and `F3`/`F4`/`F5` → `F2`
      (`planting_code`).
- [ ] The formula-derived column `F5.quantity_kg` is synced as its resolved value, never
      as formula text.
- [ ] A field-operation, scouting, or harvest row referencing a nonexistent
      `planting_code` is rejected and reported.
- [ ] A query against the synced tables correctly reconstructs a planting's full
      input-to-harvest history for a fixture workbook.
- [ ] Idempotency holds for all five tables.
