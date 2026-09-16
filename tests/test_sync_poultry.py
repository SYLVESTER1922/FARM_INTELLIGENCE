from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _poultry_batches_sheet(rows):
    return {
        "header": ["batch_code", "bird_type", "breed", "house", "placement_date",
                   "chicks_placed", "chick_unit_cost", "hatchery",
                   "target_off_date", "status"],
        "sample": ["BRO-99", "Broiler", "Ross 308", "House 9", "2026-08-10", 500,
                   0.55, "Irvine's Zimbabwe", "2026-09-21", "Growing"],
        "rows": rows,
    }


def test_sync_writes_poultry_batch_row(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "C1_POULTRY_BATCHES": _poultry_batches_sheet([
            ["BRO-01", "Broiler", "Ross 308", "House 1", "2026-01-10", 500, 0.55,
             "Irvine's Zimbabwe", "2026-02-21", "Growing"],
        ]),
    }))

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT bird_type, breed, chicks_placed, status FROM poultry_batches "
        "WHERE batch_code = %s",
        ("BRO-01",),
    ).fetchone()
    assert row == ("Broiler", "Ross 308", 500, "Growing")


def _poultry_daily_log_sheet(rows):
    return {
        "header": ["date", "batch_code", "age_days", "deaths", "culls",
                   "closing_birds", "feed_type", "feed_kg", "water_litres",
                   "house_temp_c", "litter_condition", "lighting_hours",
                   "eggs_collected", "eggs_cracked", "eggs_dirty", "notes",
                   "recorded_by"],
        "sample": ["2026-09-01", "BRO-99", 22, 2, 0, 498, "Broiler grower", 58,
                   95, 29, "Dry", None, 0, 0, 0, None, "S02"],
        "rows": rows,
    }


def test_sync_writes_poultry_daily_log_row(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "C1_POULTRY_BATCHES": _poultry_batches_sheet([
            ["BRO-01", "Broiler", "Ross 308", "House 1", "2026-01-10", 500, 0.55,
             "Irvine's Zimbabwe", "2026-02-21", "Growing"],
        ]),
        "C2_POULTRY_DAILY_LOG": _poultry_daily_log_sheet([
            ["2026-01-11", "BRO-01", 1, 3, 0, 497, "Chick mash", 5.2, 9, 33,
             "Dry", 23, 0, 0, 0, None, "S02"],
        ]),
    }))

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT deaths, closing_birds, feed_kg FROM poultry_daily_log "
        "WHERE batch_code = %s AND date = %s",
        ("BRO-01", "2026-01-11"),
    ).fetchone()
    assert row[0] == 3 and row[1] == 497 and float(row[2]) == 5.2


def test_sync_rejects_poultry_daily_log_row_with_unknown_batch(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "C1_POULTRY_BATCHES": _poultry_batches_sheet([]),
        "C2_POULTRY_DAILY_LOG": _poultry_daily_log_sheet([
            ["2026-01-11", "BRO-DOES-NOT-EXIST", 1, 3, 0, 497, "Chick mash", 5.2,
             9, 33, "Dry", 23, 0, 0, 0, None, "S02"],
        ]),
    }))

    report = sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    assert report.errors == [
        {"table": "poultry_daily_log", "row": "2026-01-11/BRO-DOES-NOT-EXIST",
         "field": "batch_code", "value": "BRO-DOES-NOT-EXIST",
         "reason": "no matching batch_code in poultry_batches"}
    ]
    row = db_conn.execute(
        "SELECT * FROM poultry_daily_log WHERE batch_code = %s",
        ("BRO-DOES-NOT-EXIST",),
    ).fetchone()
    assert row is None


def test_sync_writes_poultry_weight_row(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "C1_POULTRY_BATCHES": _poultry_batches_sheet([
            ["BRO-01", "Broiler", "Ross 308", "House 1", "2026-01-10", 500, 0.55,
             "Irvine's Zimbabwe", "2026-02-21", "Growing"],
        ]),
        "C3_POULTRY_WEIGHTS": {
            "header": ["date", "batch_code", "age_days", "sample_size",
                       "avg_weight_g", "uniformity_pct"],
            "sample": ["2026-09-01", "BRO-99", 22, 25, 1180, 88],
            "rows": [["2026-01-17", "BRO-01", 7, 25, 180, 90]],
        },
    }))

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT sample_size, avg_weight_g, uniformity_pct FROM poultry_weights "
        "WHERE batch_code = %s AND date = %s",
        ("BRO-01", "2026-01-17"),
    ).fetchone()
    assert row == (25, 180, 90)


def test_sync_rejects_poultry_weight_row_with_unknown_batch(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "C1_POULTRY_BATCHES": _poultry_batches_sheet([]),
        "C3_POULTRY_WEIGHTS": {
            "header": ["date", "batch_code", "age_days", "sample_size",
                       "avg_weight_g", "uniformity_pct"],
            "sample": ["2026-09-01", "BRO-99", 22, 25, 1180, 88],
            "rows": [["2026-01-17", "BRO-DOES-NOT-EXIST", 7, 25, 180, 90]],
        },
    }))

    report = sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    assert report.errors == [
        {"table": "poultry_weights", "row": "2026-01-17/BRO-DOES-NOT-EXIST",
         "field": "batch_code", "value": "BRO-DOES-NOT-EXIST",
         "reason": "no matching batch_code in poultry_batches"}
    ]


def _full_poultry_fixture():
    return base_fixture(extra_sheets={
        "C1_POULTRY_BATCHES": _poultry_batches_sheet([
            ["BRO-01", "Broiler", "Ross 308", "House 1", "2026-01-10", 500, 0.55,
             "Irvine's Zimbabwe", "2026-02-21", "Growing"],
        ]),
        "C2_POULTRY_DAILY_LOG": _poultry_daily_log_sheet([
            ["2026-01-11", "BRO-01", 1, 3, 0, 497, "Chick mash", 5.2, 9, 33,
             "Dry", 23, 0, 0, 0, None, "S02"],
            ["2026-01-12", "BRO-01", 2, 1, 0, 496, "Chick mash", 5.6, 10, 33,
             "Dry", 23, 0, 0, 0, None, "S02"],
        ]),
        "C3_POULTRY_WEIGHTS": {
            "header": ["date", "batch_code", "age_days", "sample_size",
                       "avg_weight_g", "uniformity_pct"],
            "sample": ["2026-09-01", "BRO-99", 22, 25, 1180, 88],
            "rows": [["2026-01-17", "BRO-01", 7, 25, 180, 90]],
        },
    })


def test_sync_is_idempotent_across_poultry_tables(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _full_poultry_fixture())

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    counts = {
        table: db_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("poultry_batches", "poultry_daily_log", "poultry_weights")
    }
    assert counts == {
        "poultry_batches": 1, "poultry_daily_log": 2, "poultry_weights": 1,
    }


def test_broiler_batch_performance_is_queryable(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _full_poultry_fixture())

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute("""
        SELECT b.batch_code, SUM(d.deaths) AS total_deaths,
               (SELECT avg_weight_g FROM poultry_weights w
                WHERE w.batch_code = b.batch_code ORDER BY w.date DESC LIMIT 1)
        FROM poultry_batches b
        JOIN poultry_daily_log d ON d.batch_code = b.batch_code
        WHERE b.batch_code = 'BRO-01'
        GROUP BY b.batch_code
    """).fetchone()

    assert row == ("BRO-01", 4, 180)
