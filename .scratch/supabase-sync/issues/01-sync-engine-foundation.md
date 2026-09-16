# 01: Sync engine foundation: farm profile, staff, and lists

**What to build:** A working sync from the workbook to Supabase/Postgres, proven end to
end on the smallest tabs first. A farm owner (or developer) can run the sync against the
workbook and see `00_FARM_PROFILE`, `01_STAFF`, and the `99_LISTS` dropdown vocabulary
land in Supabase as real rows, re-run it safely with no duplicates, and get a clear error
if a row references a category that doesn't exist in `99_LISTS`. This ticket also extracts
the reusable workbook-reading logic (currently duplicated ad hoc across
`gen_scripts/generate_data.py` and `gen_scripts/regenerate_feed_inventory.py`) into a
shared module the rest of the sync builds on.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] A reusable workbook-reader module exists, parsing every tab's row-1 (purpose/cadence
      note), row-2 (headers), row-3 (sample row, never touched), row-4+ (data) convention,
      and extracting the `99_LISTS` dropdown vocabulary.
- [ ] Postgres/Supabase schema exists for `00_FARM_PROFILE`, `01_STAFF`, and a reference
      table (or set of tables) mirroring `99_LISTS`.
- [ ] `syncWorkbookToSupabase(filePath, farmCode)` upserts these three tables from a
      fixture workbook, keyed on natural keys (`farm_code`, `staff_code`), and returns a
      sync report of rows written per table.
- [ ] Running the sync twice against an unchanged fixture produces identical row counts
      (idempotency).
- [ ] A row with a dropdown value not present in `99_LISTS` is rejected and reported with
      an error distinguishable from other failure types, not silently written.
- [ ] Every synced table carries a `farm_code` column.
- [ ] Tests assert on the resulting database state and the sync report, not on internal
      parsing/mapping functions in isolation.
