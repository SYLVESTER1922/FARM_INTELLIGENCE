# 06: Full-workbook end-to-end regression

**What to build:** Proof that the whole sync works against the real thing, not just test
fixtures — the actual Chiedza Mixed Farm (NIS-001) workbook, all 23 tabs, synced twice in
a row, with the three planted findings still answerable by SQL afterward. This is the
acceptance ticket for the whole feature.

**Blocked by:** 01, 02, 03, 04, 05

**Status:** done

- [x] The sync runs successfully against the complete, real
      `Netrisyl_Farm_Intelligence_Workbook.xlsx`, covering all 23 tabs.
- [x] Running the sync twice against the unchanged real workbook produces identical row
      counts across all 23 tables (no duplicates, no drift).
      (`test_full_workbook_sync_is_idempotent`)
- [x] The three planted findings remain discoverable via SQL after a real sync:
      `BRO-P02`'s heatwave-linked mortality spike, `PIG-B02`'s disease outbreak (in
      `07_HEALTH_LOG`), and `SB-PL2-25A`'s unpaid sale (`payment_status = Owing`, still
      unresolved at the window end).
      (`test_three_planted_findings_are_discoverable_after_sync`)
- [x] The sync report's per-tab row counts match the workbook's known counts (2,598 rows
      across the original 23 tabs, with `06_FEED_INVENTORY` at its corrected 105-row
      count).
      (`test_full_workbook_syncs_with_no_errors_and_known_row_counts`, checked against
      every tab's known count individually)
- [x] No validation errors are reported against the real, already-validated workbook.

**Two real bugs found and fixed by this regression** (neither was caught by the
fixture-based tests in tickets 01-05, because the fixtures shared the same wrong
assumptions the sync code did):

1. **Row 3 isn't always a discardable sample.** `00_FARM_PROFILE` and `01_STAFF` are
   singleton/registry-style tabs where the real workbook's actual data starts at row 3,
   not row 4: `00_FARM_PROFILE` has no row 4 at all (it's a one-farm-per-workbook
   singleton), and `01_STAFF`'s row 3 holds a real staff member (`S01`) referenced 286
   times by `04_LABOUR_LOG` — excluding it would have failed 286 real rows' FK checks.
   Fixed in `sync/workbook_reader.py` (`read_tab_rows` gained a `min_row` parameter) and
   `sync/engine.py` (`_sync_farm_profile` and `_sync_staff` now read from row 3; farm
   profile takes the *last* row found, so a fixture with both a sample and a real row
   still resolves correctly).
2. **`07_HEALTH_LOG`'s reference column is `batch_ref`, not `batch_code`.** I had used
   the wrong name throughout `_sync_health_log` (schema, SQL, Python) since ticket 05,
   and my own test fixtures repeated the same wrong assumption, so nothing caught it
   until this test ran against the real header row. Fixed in `sync/engine.py` and
   `tests/test_sync_shared_core.py`.
