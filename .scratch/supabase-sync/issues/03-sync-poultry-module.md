# 03: Sync poultry module (C1–C3)

**What to build:** The full poultry module — flock register, daily logs, and weights —
synced into Supabase with referential integrity, so a query against Postgres can answer
real questions about broiler batch performance without touching the spreadsheet.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] `C1_POULTRY_BATCHES`, `C2_POULTRY_DAILY_LOG`, and `C3_POULTRY_WEIGHTS` are synced
      via the shared engine from Ticket 01.
- [ ] Foreign key constraints enforce `C2`/`C3` → `C1` (`batch_code`).
- [ ] A daily-log row referencing a nonexistent `batch_code` is rejected and reported.
- [ ] A query against the synced tables correctly answers "broiler batch performance"
      (mortality, feed use, weight trend) for a fixture workbook.
- [ ] Idempotency holds for all three tables.
