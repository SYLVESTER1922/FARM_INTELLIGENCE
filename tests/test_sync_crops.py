from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _plots_sheet(rows):
    return {
        "header": ["plot_code", "plot_name", "hectares", "soil_type",
                   "irrigation_type", "gps"],
        "sample": ["P9", "Sample field", 6, "Clay loam", "Sprinkler", None],
        "rows": rows,
    }


def test_sync_writes_plot_row(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "F1_PLOTS": _plots_sheet([
            ["P3", "River field", 6, "Clay loam", "Sprinkler", None],
        ]),
    }))

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT plot_name, hectares, soil_type FROM plots WHERE plot_code = %s",
        ("P3",),
    ).fetchone()
    assert row[0] == "River field" and float(row[1]) == 6 and row[2] == "Clay loam"


def _plantings_sheet(rows):
    return {
        "header": ["planting_code", "plot_code", "crop", "variety", "season",
                   "planting_date", "area_ha", "seed_kg", "seed_cost",
                   "expected_harvest_date", "expected_yield_tons_ha", "status"],
        "sample": ["MZ-P9-2025A", "P9", "Maize", "SC637", "2025 Summer",
                   "2025-11-15", 6, 150, 210, "2026-04-15", 5.5, "Growing"],
        "rows": rows,
    }


def test_sync_writes_planting_row(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "F1_PLOTS": _plots_sheet([
            ["P3", "River field", 6, "Clay loam", "Sprinkler", None],
        ]),
        "F2_PLANTINGS": _plantings_sheet([
            ["MZ-P3-2025A", "P3", "Maize", "SC637", "2025 Summer", "2025-11-15",
             6, 150, 210, "2026-04-15", 5.5, "Growing"],
        ]),
    }))

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT crop, season, status FROM plantings WHERE planting_code = %s",
        ("MZ-P3-2025A",),
    ).fetchone()
    assert row == ("Maize", "2025 Summer", "Growing")


def test_sync_rejects_planting_row_with_unknown_plot(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "F1_PLOTS": _plots_sheet([]),
        "F2_PLANTINGS": _plantings_sheet([
            ["MZ-P3-2025A", "PLOT-DOES-NOT-EXIST", "Maize", "SC637",
             "2025 Summer", "2025-11-15", 6, 150, 210, "2026-04-15", 5.5,
             "Growing"],
        ]),
    }))

    report = sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    assert report.errors == [
        {"table": "plantings", "row": "MZ-P3-2025A", "field": "plot_code",
         "value": "PLOT-DOES-NOT-EXIST", "reason": "no matching plot_code in plots"}
    ]


def _field_operations_sheet(rows):
    return {
        "header": ["date", "planting_code", "op_type", "product", "rate",
                   "quantity", "unit", "input_cost", "labour_hours",
                   "machine_hours", "irrigation_mm", "notes", "recorded_by"],
        "sample": ["2025-12-01", "MZ-P9-2025A", "Top dressing", "AN",
                   "150 kg/ha", 900, "kg", 540, 12, 2, 0, None, "S03"],
        "rows": rows,
    }


def test_sync_writes_field_operation_row(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "F1_PLOTS": _plots_sheet([
            ["P3", "River field", 6, "Clay loam", "Sprinkler", None],
        ]),
        "F2_PLANTINGS": _plantings_sheet([
            ["MZ-P3-2025A", "P3", "Maize", "SC637", "2025 Summer", "2025-11-15",
             6, 150, 210, "2026-04-15", 5.5, "Growing"],
        ]),
        "F3_FIELD_OPERATIONS": _field_operations_sheet([
            ["2025-12-01", "MZ-P3-2025A", "Top dressing", "AN", "150 kg/ha",
             900, "kg", 540, 12, 2, 0, None, "S03"],
        ]),
    }))

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT op_type, input_cost FROM field_operations "
        "WHERE planting_code = %s AND date = %s",
        ("MZ-P3-2025A", "2025-12-01"),
    ).fetchone()
    assert row[0] == "Top dressing" and float(row[1]) == 540


def test_sync_rejects_field_operation_row_with_unknown_planting(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "F1_PLOTS": _plots_sheet([]),
        "F2_PLANTINGS": _plantings_sheet([]),
        "F3_FIELD_OPERATIONS": _field_operations_sheet([
            ["2025-12-01", "PLANTING-DOES-NOT-EXIST", "Top dressing", "AN",
             "150 kg/ha", 900, "kg", 540, 12, 2, 0, None, "S03"],
        ]),
    }))

    report = sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    assert report.errors == [
        {"table": "field_operations", "row": "2025-12-01/PLANTING-DOES-NOT-EXIST",
         "field": "planting_code", "value": "PLANTING-DOES-NOT-EXIST",
         "reason": "no matching planting_code in plantings"}
    ]


def _scouting_log_sheet(rows):
    return {
        "header": ["date", "planting_code", "growth_stage", "issue_type",
                   "issue_name", "severity_1_5", "incidence_pct",
                   "soil_moisture", "action_taken", "scouted_by"],
        "sample": ["2026-01-12", "MZ-P9-2025A", "V6", "Pest", "Fall armyworm",
                   2, 8, "Moist", "Spot-sprayed affected rows", "S03"],
        "rows": rows,
    }


def test_sync_writes_scouting_log_row(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "F1_PLOTS": _plots_sheet([
            ["P3", "River field", 6, "Clay loam", "Sprinkler", None],
        ]),
        "F2_PLANTINGS": _plantings_sheet([
            ["MZ-P3-2025A", "P3", "Maize", "SC637", "2025 Summer", "2025-11-15",
             6, 150, 210, "2026-04-15", 5.5, "Growing"],
        ]),
        "F4_SCOUTING_LOG": _scouting_log_sheet([
            ["2026-01-12", "MZ-P3-2025A", "V6", "Pest", "Fall armyworm", 2, 8,
             "Moist", "Spot-sprayed affected rows", "S03"],
        ]),
    }))

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT issue_type, issue_name, severity_1_5 FROM scouting_log "
        "WHERE planting_code = %s AND date = %s",
        ("MZ-P3-2025A", "2026-01-12"),
    ).fetchone()
    assert row == ("Pest", "Fall armyworm", 2)


def test_sync_rejects_scouting_log_row_with_unknown_planting(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "F1_PLOTS": _plots_sheet([]),
        "F2_PLANTINGS": _plantings_sheet([]),
        "F4_SCOUTING_LOG": _scouting_log_sheet([
            ["2026-01-12", "PLANTING-DOES-NOT-EXIST", "V6", "Pest",
             "Fall armyworm", 2, 8, "Moist", "Spot-sprayed affected rows", "S03"],
        ]),
    }))

    report = sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    assert report.errors == [
        {"table": "scouting_log", "row": "2026-01-12/PLANTING-DOES-NOT-EXIST",
         "field": "planting_code", "value": "PLANTING-DOES-NOT-EXIST",
         "reason": "no matching planting_code in plantings"}
    ]


def _harvest_log_sheet(rows):
    return {
        "header": ["date", "planting_code", "bags", "quantity_kg", "moisture_pct",
                   "grade", "field_loss_kg", "storage_location", "labour_hours"],
        "sample": ["2026-04-20", "MZ-P9-2025A", 66, 3300, 12.5, "A", 40,
                   "Silo 1", 20],
        "rows": rows,
    }


def test_sync_writes_harvest_log_row(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "F1_PLOTS": _plots_sheet([
            ["P3", "River field", 6, "Clay loam", "Sprinkler", None],
        ]),
        "F2_PLANTINGS": _plantings_sheet([
            ["MZ-P3-2025A", "P3", "Maize", "SC637", "2025 Summer", "2025-11-15",
             6, 150, 210, "2026-04-15", 5.5, "Growing"],
        ]),
        "F5_HARVEST_LOG": _harvest_log_sheet([
            ["2026-04-20", "MZ-P3-2025A", 66, 3300, 12.5, "A", 40, "Silo 1", 20],
        ]),
    }))

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT bags, quantity_kg, grade FROM harvest_log "
        "WHERE planting_code = %s AND date = %s",
        ("MZ-P3-2025A", "2026-04-20"),
    ).fetchone()
    assert row[0] == 66 and float(row[1]) == 3300 and row[2] == "A"


def test_sync_rejects_harvest_log_row_with_unknown_planting(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "F1_PLOTS": _plots_sheet([]),
        "F2_PLANTINGS": _plantings_sheet([]),
        "F5_HARVEST_LOG": _harvest_log_sheet([
            ["2026-04-20", "PLANTING-DOES-NOT-EXIST", 66, 3300, 12.5, "A", 40,
             "Silo 1", 20],
        ]),
    }))

    report = sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    assert report.errors == [
        {"table": "harvest_log", "row": "2026-04-20/PLANTING-DOES-NOT-EXIST",
         "field": "planting_code", "value": "PLANTING-DOES-NOT-EXIST",
         "reason": "no matching planting_code in plantings"}
    ]


def _full_crops_fixture():
    return base_fixture(extra_sheets={
        "F1_PLOTS": _plots_sheet([
            ["P3", "River field", 6, "Clay loam", "Sprinkler", None],
        ]),
        "F2_PLANTINGS": _plantings_sheet([
            ["MZ-P3-2025A", "P3", "Maize", "SC637", "2025 Summer", "2025-11-15",
             6, 150, 210, "2026-04-15", 5.5, "Growing"],
        ]),
        "F3_FIELD_OPERATIONS": _field_operations_sheet([
            ["2025-11-10", "MZ-P3-2025A", "Land prep", None, None, None, "kg",
             210, 8, 3, 0, None, "S03"],
            ["2025-12-01", "MZ-P3-2025A", "Top dressing", "AN", "150 kg/ha",
             900, "kg", 540, 12, 2, 0, None, "S03"],
        ]),
        "F4_SCOUTING_LOG": _scouting_log_sheet([
            ["2026-01-12", "MZ-P3-2025A", "V6", "Pest", "Fall armyworm", 2, 8,
             "Moist", "Spot-sprayed affected rows", "S03"],
        ]),
        "F5_HARVEST_LOG": _harvest_log_sheet([
            ["2026-04-20", "MZ-P3-2025A", 66, 3300, 12.5, "A", 40, "Silo 1", 20],
        ]),
    })


def test_sync_is_idempotent_across_crop_tables(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _full_crops_fixture())

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    counts = {
        table: db_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("plots", "plantings", "field_operations", "scouting_log",
                       "harvest_log")
    }
    assert counts == {
        "plots": 1, "plantings": 1, "field_operations": 2, "scouting_log": 1,
        "harvest_log": 1,
    }


def test_planting_input_to_harvest_history_is_queryable(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _full_crops_fixture())

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    plot = db_conn.execute(
        "SELECT plot_name FROM plots p JOIN plantings pl ON pl.plot_code = p.plot_code "
        "WHERE pl.planting_code = %s", ("MZ-P3-2025A",),
    ).fetchone()
    op_count = db_conn.execute(
        "SELECT COUNT(*) FROM field_operations WHERE planting_code = %s",
        ("MZ-P3-2025A",),
    ).fetchone()[0]
    issue_count = db_conn.execute(
        "SELECT COUNT(*) FROM scouting_log WHERE planting_code = %s",
        ("MZ-P3-2025A",),
    ).fetchone()[0]
    harvest = db_conn.execute(
        "SELECT bags, quantity_kg FROM harvest_log WHERE planting_code = %s",
        ("MZ-P3-2025A",),
    ).fetchone()

    assert plot == ("River field",)
    assert op_count == 2
    assert issue_count == 1
    assert harvest[0] == 66 and float(harvest[1]) == 3300
