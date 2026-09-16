from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _fixture_with_staff(staff_rows, lists=None):
    return base_fixture(staff_rows=staff_rows, lists=lists)


def test_sync_writes_farm_profile_row(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _fixture_with_staff([]))

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT farm_name, total_hectares FROM farm_profile WHERE farm_code = %s",
        ("NIS-001",),
    ).fetchone()
    assert row == ("Chiedza Mixed Farm", 45)


def test_sync_is_idempotent_for_farm_profile(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _fixture_with_staff([]))

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    count = db_conn.execute(
        "SELECT COUNT(*) FROM farm_profile WHERE farm_code = %s", ("NIS-001",)
    ).fetchone()[0]
    assert count == 1


def test_sync_returns_a_report_of_rows_written(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _fixture_with_staff([]))

    report = sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    assert report.rows_written["farm_profile"] == 1


def test_sync_writes_staff_rows(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _fixture_with_staff([
        ["S01", "Tendai Moyo", "Pig attendant", "piggery", "Daily", 12, "Yes"],
        ["S02", "Rudo Chirwa", "Poultry attendant", "poultry", "Daily", 12, "Yes"],
    ]))

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT full_name, role, rate FROM staff WHERE staff_code = %s", ("S01",)
    ).fetchone()
    assert row == ("Tendai Moyo", "Pig attendant", 12)


def test_sync_writes_list_values(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _fixture_with_staff([], lists={
        "DOMAIN": ["piggery", "poultry", "crops"],
        "FEED_TYPE": ["Pig starter", "Pig grower"],
    }))

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    values = db_conn.execute(
        "SELECT value FROM list_values WHERE list_name = %s ORDER BY value",
        ("DOMAIN",),
    ).fetchall()
    assert [v[0] for v in values] == ["crops", "piggery", "poultry"]


def test_sync_rejects_staff_row_with_invalid_domain(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _fixture_with_staff(
        [["S01", "Tendai Moyo", "Pig attendant", "not-a-real-domain", "Daily", 12, "Yes"]],
        lists={"DOMAIN": ["piggery", "poultry", "crops", "shared"]},
    ))

    report = sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    assert report.errors == [
        {"table": "staff", "row": "S01", "field": "primary_domain",
         "value": "not-a-real-domain", "reason": "not in 99_LISTS[DOMAIN]"}
    ]
    row = db_conn.execute(
        "SELECT * FROM staff WHERE staff_code = %s", ("S01",)
    ).fetchone()
    assert row is None


def test_sync_rejects_staff_row_with_invalid_role(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _fixture_with_staff(
        [["S01", "Tendai Moyo", "Not A Real Role", "piggery", "Daily", 12, "Yes"]],
        lists={"DOMAIN": ["piggery", "poultry", "crops", "shared"],
               "ROLE": ["Pig attendant", "Poultry attendant", "Field hand", "Supervisor"]},
    ))

    report = sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    assert report.errors == [
        {"table": "staff", "row": "S01", "field": "role",
         "value": "Not A Real Role", "reason": "not in 99_LISTS[ROLE]"}
    ]
    row = db_conn.execute(
        "SELECT * FROM staff WHERE staff_code = %s", ("S01",)
    ).fetchone()
    assert row is None
