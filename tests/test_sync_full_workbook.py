"""
Acceptance test for the whole spec: runs the sync against the real,
fully-populated Chiedza Mixed Farm workbook (all 23 tabs), not a
fixture. Fixtures proved the mechanism; this proves it holds against
actual production-shaped data.
"""

from pathlib import Path

from sync.engine import sync_workbook_to_supabase

REAL_WORKBOOK = Path(__file__).parent.parent / "Netrisyl_Farm_Intelligence_Workbook.xlsx"

# Known row counts per tab, from the original generation (seed=42) and the
# 06_FEED_INVENTORY grain fix (commit 21bd86e) - the ground truth to check
# the sync against, not just whatever the sync happens to produce.
EXPECTED_ROWS_WRITTEN = {
    "staff": 4,  # S01-S04; S01 lives at row 3, a real FK-referenced staff
                 # member, not a discardable sample - see workbook_reader.py
    "pig_batches": 4,
    "pig_daily_log": 529,
    "pig_weights": 37,
    "sow_register": 3,
    "breeding_farrowing": 3,
    "poultry_batches": 4,
    "poultry_daily_log": 172,
    "poultry_weights": 24,
    "plots": 3,
    "plantings": 5,
    "field_operations": 30,
    "scouting_log": 42,
    "harvest_log": 4,
    "feed_inventory": 105,
    "weather_log": 350,
    "labour_log": 1143,
    "expenses": 143,
    "revenue": 10,
    "health_log": 14,
}


def test_full_workbook_syncs_with_no_errors_and_known_row_counts(db_conn, test_dsn):
    report = sync_workbook_to_supabase(str(REAL_WORKBOOK), farm_code="NIS-001", dsn=test_dsn)

    assert report.errors == []
    for table, expected in EXPECTED_ROWS_WRITTEN.items():
        assert report.rows_written[table] == expected, (
            f"{table}: expected {expected} rows written, got "
            f"{report.rows_written[table]}"
        )


def test_full_workbook_sync_is_idempotent(db_conn, test_dsn):
    sync_workbook_to_supabase(str(REAL_WORKBOOK), farm_code="NIS-001", dsn=test_dsn)
    sync_workbook_to_supabase(str(REAL_WORKBOOK), farm_code="NIS-001", dsn=test_dsn)

    counts = {
        table: db_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in EXPECTED_ROWS_WRITTEN
    }
    assert counts == EXPECTED_ROWS_WRITTEN


def test_three_planted_findings_are_discoverable_after_sync(db_conn, test_dsn):
    sync_workbook_to_supabase(str(REAL_WORKBOOK), farm_code="NIS-001", dsn=test_dsn)

    # Finding 1: poultry batch BRO-P02 has an elevated-mortality outlier
    # (heatwave-linked) versus the farm's other broiler batches.
    mortality = db_conn.execute("""
        SELECT b.batch_code,
               ROUND(100.0 * SUM(d.deaths) / b.chicks_placed, 1) AS mortality_pct
        FROM poultry_batches b
        JOIN poultry_daily_log d ON d.batch_code = b.batch_code
        GROUP BY b.batch_code, b.chicks_placed
        ORDER BY mortality_pct DESC
    """).fetchall()
    worst_batch, worst_pct = mortality[0]
    assert worst_batch == "BRO-P02"
    assert float(worst_pct) > 5  # a real outlier, not noise
    assert all(float(pct) < 2 for code, pct in mortality[1:])

    # Finding 2: pig batch PIG-B02 has a disease outbreak in health_log,
    # with matching vet costs.
    outbreak = db_conn.execute("""
        SELECT event_type, outcome, cost FROM health_log
        WHERE batch_ref = 'PIG-B02' AND domain = 'piggery'
        ORDER BY date
    """).fetchall()
    assert len(outbreak) >= 3
    assert any(row[0] == "Treatment" for row in outbreak)

    # Finding 3: crop sale SB-PL2-25A is unpaid (Owing), unresolved at
    # the end of the data window.
    debtor = db_conn.execute("""
        SELECT payment_status FROM revenue
        WHERE batch_ref = 'SB-PL2-25A' OR product = 'Soyabean'
    """).fetchall()
    assert ("Owing",) in debtor
