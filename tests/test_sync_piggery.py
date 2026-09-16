from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def test_sync_writes_pig_batch_row(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "P1_PIG_BATCHES": {
            "header": ["batch_code", "pen", "breed", "start_date", "start_count",
                       "start_avg_kg", "source", "target_market_date", "status"],
            "sample": ["PIG-B99", "Pen 9", "Large White", "2026-01-01", 20, 8.0,
                       "Own farrowing", "2026-05-01", "Active"],
            "rows": [["PIG-B01", "Pen 1", "Large White", "2026-01-05", 24, 8.5,
                      "Own farrowing", "2026-05-20", "Active"]],
        },
    }))

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT pen, breed, start_count, status FROM pig_batches WHERE batch_code = %s",
        ("PIG-B01",),
    ).fetchone()
    assert row == ("Pen 1", "Large White", 24, "Active")


def _pig_batches_sheet(rows):
    return {
        "header": ["batch_code", "pen", "breed", "start_date", "start_count",
                   "start_avg_kg", "source", "target_market_date", "status"],
        "sample": ["PIG-B99", "Pen 9", "Large White", "2026-01-01", 20, 8.0,
                   "Own farrowing", "2026-05-01", "Active"],
        "rows": rows,
    }


def _pig_daily_log_sheet(rows):
    return {
        "header": ["date", "batch_code", "pen", "feed_type", "feed_kg",
                   "water_litres", "deaths", "culls", "closing_count",
                   "pen_temp_c", "pen_condition", "notes", "recorded_by"],
        "sample": ["2026-09-07", "PIG-B99", "Pen 9", "Pig grower", 42, 110, 0, 0,
                   20, 24, "Dry", None, "S01"],
        "rows": rows,
    }


def test_sync_writes_pig_daily_log_row(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "P1_PIG_BATCHES": _pig_batches_sheet([
            ["PIG-B01", "Pen 1", "Large White", "2026-01-05", 24, 8.5,
             "Own farrowing", "2026-05-20", "Active"],
        ]),
        "P2_PIG_DAILY_LOG": _pig_daily_log_sheet([
            ["2026-01-06", "PIG-B01", "Pen 1", "Pig starter", 8.4, 22, 0, 0,
             24, 24, "Dry", None, "S01"],
        ]),
    }))

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT feed_kg, deaths, closing_count FROM pig_daily_log "
        "WHERE batch_code = %s AND date = %s",
        ("PIG-B01", "2026-01-06"),
    ).fetchone()
    assert (float(row[0]), row[1], row[2]) == (8.4, 0, 24)


def test_sync_rejects_daily_log_row_with_unknown_batch(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "P1_PIG_BATCHES": _pig_batches_sheet([]),
        "P2_PIG_DAILY_LOG": _pig_daily_log_sheet([
            ["2026-01-06", "PIG-DOES-NOT-EXIST", "Pen 1", "Pig starter", 8.4, 22,
             0, 0, 24, 24, "Dry", None, "S01"],
        ]),
    }))

    report = sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    assert report.errors == [
        {"table": "pig_daily_log", "row": "2026-01-06/PIG-DOES-NOT-EXIST",
         "field": "batch_code", "value": "PIG-DOES-NOT-EXIST",
         "reason": "no matching batch_code in pig_batches"}
    ]
    row = db_conn.execute(
        "SELECT * FROM pig_daily_log WHERE batch_code = %s", ("PIG-DOES-NOT-EXIST",)
    ).fetchone()
    assert row is None


def test_sync_writes_pig_weight_row(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "P1_PIG_BATCHES": _pig_batches_sheet([
            ["PIG-B01", "Pen 1", "Large White", "2026-01-05", 24, 8.5,
             "Own farrowing", "2026-05-20", "Active"],
        ]),
        "P3_PIG_WEIGHTS": {
            "header": ["date", "batch_code", "sample_size", "avg_weight_kg",
                       "min_weight_kg", "max_weight_kg", "age_days"],
            "sample": ["2026-09-01", "PIG-B99", 10, 38.2, 31, 44, 92],
            "rows": [["2026-01-19", "PIG-B01", 10, 12.5, 10, 15, 14]],
        },
    }))

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT sample_size, avg_weight_kg, age_days FROM pig_weights "
        "WHERE batch_code = %s AND date = %s",
        ("PIG-B01", "2026-01-19"),
    ).fetchone()
    assert row[0] == 10 and float(row[1]) == 12.5 and row[2] == 14


def _sow_register_sheet(rows):
    return {
        "header": ["sow_tag", "breed", "date_of_birth", "parity",
                   "body_condition_1_5", "status"],
        "sample": ["SOW-99", "Landrace", "2024-03-10", 3, 3, "Lactating"],
        "rows": rows,
    }


def test_sync_writes_sow_register_row(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "P4_SOW_REGISTER": _sow_register_sheet([
            ["SOW-01", "Landrace", "2024-03-10", 3, 3, "Lactating"],
        ]),
    }))

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT breed, parity, status FROM sow_register WHERE sow_tag = %s",
        ("SOW-01",),
    ).fetchone()
    assert row == ("Landrace", 3, "Lactating")


def test_sync_writes_breeding_farrowing_row_with_litter_batch_link(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "P1_PIG_BATCHES": _pig_batches_sheet([
            ["PIG-B01", "Pen 1", "Large White", "2026-01-05", 24, 8.5,
             "Own farrowing", "2026-05-20", "Active"],
        ]),
        "P4_SOW_REGISTER": _sow_register_sheet([
            ["SOW-01", "Landrace", "2024-03-10", 3, 3, "Lactating"],
        ]),
        "P5_BREEDING_FARROWING": {
            "header": ["sow_tag", "boar_tag", "service_date", "service_type",
                       "pregnancy_confirmed", "expected_farrow_date", "farrow_date",
                       "born_alive", "stillborn", "mummified", "avg_birth_weight_kg",
                       "wean_date", "weaned_count", "avg_wean_weight_kg",
                       "litter_batch_code"],
            "sample": ["SOW-99", "BOAR-01", "2026-05-10", "Natural", "Yes",
                       "2026-09-01", None, None, None, None, None, None, None,
                       None, None],
            "rows": [["SOW-01", "BOAR-02", "2025-09-13", "Natural", "Yes",
                      "2026-01-05", "2026-01-05", 12, 1, 0, 1.4, "2026-01-26",
                      11, 7.2, "PIG-B01"]],
        },
    }))

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT born_alive, weaned_count, litter_batch_code FROM breeding_farrowing "
        "WHERE sow_tag = %s AND service_date = %s",
        ("SOW-01", "2025-09-13"),
    ).fetchone()
    assert row == (12, 11, "PIG-B01")


def _full_piggery_fixture():
    return base_fixture(extra_sheets={
        "P1_PIG_BATCHES": _pig_batches_sheet([
            ["PIG-B01", "Pen 1", "Large White", "2026-01-05", 24, 8.5,
             "Own farrowing", "2026-05-20", "Active"],
            ["PIG-B02", "Pen 2", "Landrace", "2025-11-01", 20, 8.0,
             "Own farrowing", "2026-03-15", "Sold"],
        ]),
        "P2_PIG_DAILY_LOG": _pig_daily_log_sheet([
            ["2026-01-06", "PIG-B01", "Pen 1", "Pig starter", 8.4, 22, 0, 0, 24, 24, "Dry", None, "S01"],
            ["2026-01-07", "PIG-B01", "Pen 1", "Pig starter", 8.6, 23, 1, 0, 23, 24, "Dry", None, "S01"],
            ["2025-11-05", "PIG-B02", "Pen 2", "Pig starter", 7.0, 20, 0, 0, 20, 24, "Dry", None, "S01"],
        ]),
        "P3_PIG_WEIGHTS": {
            "header": ["date", "batch_code", "sample_size", "avg_weight_kg",
                       "min_weight_kg", "max_weight_kg", "age_days"],
            "sample": ["2026-09-01", "PIG-B99", 10, 38.2, 31, 44, 92],
            "rows": [],
        },
        "P4_SOW_REGISTER": _sow_register_sheet([
            ["SOW-01", "Landrace", "2024-03-10", 3, 3, "Lactating"],
        ]),
    })


def test_sync_is_idempotent_across_piggery_tables(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _full_piggery_fixture())

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    counts = {
        table: db_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("pig_batches", "pig_daily_log", "pig_weights", "sow_register")
    }
    assert counts == {
        "pig_batches": 2, "pig_daily_log": 3, "pig_weights": 0, "sow_register": 1,
    }


def test_active_pig_batches_and_daily_mortality_are_queryable(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _full_piggery_fixture())

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    rows = db_conn.execute("""
        SELECT b.batch_code, SUM(d.deaths) AS total_deaths
        FROM pig_batches b
        JOIN pig_daily_log d ON d.batch_code = b.batch_code
        WHERE b.status = 'Active'
        GROUP BY b.batch_code
        ORDER BY b.batch_code
    """).fetchall()

    assert rows == [("PIG-B01", 1)]
