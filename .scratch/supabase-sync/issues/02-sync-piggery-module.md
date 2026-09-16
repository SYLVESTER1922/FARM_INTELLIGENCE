# 02: Sync piggery module (P1–P5)

**What to build:** The full piggery module — batch register, daily logs, weights, sow
register, and breeding/farrowing — synced into Supabase with referential integrity, so a
query against Postgres can answer real questions about pig batches (e.g. active batches
and their daily mortality) without touching the spreadsheet.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] `P1_PIG_BATCHES`, `P2_PIG_DAILY_LOG`, `P3_PIG_WEIGHTS`, `P4_SOW_REGISTER`, and
      `P5_BREEDING_FARROWING` are synced via the shared engine from Ticket 01.
- [ ] Foreign key constraints enforce `P2`/`P3` → `P1` (`batch_code`) and `P5` → `P4`
      (`sow_tag`); `P5.litter_batch_code` resolves against `P1` where present.
- [ ] Formula-derived columns (`P2.closing_count`, `P3.age_days`,
      `P5.expected_farrow_date`) are synced as their resolved values, never as formula
      text.
- [ ] A daily-log row referencing a nonexistent `batch_code` is rejected and reported.
- [ ] A query against the synced tables correctly answers "which pig batches are active,
      and what's their daily mortality" for a fixture workbook.
- [ ] Idempotency holds for all five tables (re-running the sync produces no duplicates).
