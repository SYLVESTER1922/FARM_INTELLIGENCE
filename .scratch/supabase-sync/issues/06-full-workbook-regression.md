# 06: Full-workbook end-to-end regression

**What to build:** Proof that the whole sync works against the real thing, not just test
fixtures — the actual Chiedza Mixed Farm (NIS-001) workbook, all 23 tabs, synced twice in
a row, with the three planted findings still answerable by SQL afterward. This is the
acceptance ticket for the whole feature.

**Blocked by:** 01, 02, 03, 04, 05

**Status:** ready-for-agent

- [ ] The sync runs successfully against the complete, real
      `Netrisyl_Farm_Intelligence_Workbook.xlsx`, covering all 23 tabs.
- [ ] Running the sync twice against the unchanged real workbook produces identical row
      counts across all 23 tables (no duplicates, no drift).
- [ ] The three planted findings remain discoverable via SQL after a real sync:
      `BRO-P02`'s heatwave-linked mortality spike, `PIG-B02`'s disease outbreak (in
      `07_HEALTH_LOG`), and `SB-PL2-25A`'s unpaid sale (`payment_status = Owing`, still
      unresolved at the window end).
- [ ] The sync report's per-tab row counts match the workbook's known counts (2,598 rows
      across the original 23 tabs, with `06_FEED_INVENTORY` at its corrected 105-row
      count).
- [ ] No validation errors are reported against the real, already-validated workbook.
