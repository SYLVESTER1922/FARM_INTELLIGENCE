"""
Direct unit tests for the new ui/queries.py functions backing the Chat
page's Quick Lookup widget (pen/batch) - debtor lookup needs no test here
since it reuses fetch_debtors, already exercised via the Finance page.
"""

from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook
from ui.queries import fetch_batch_summary, fetch_pen_summary


def _lookup_fixture():
    return base_fixture(extra_sheets={
        "P1_PIG_BATCHES": {
            "header": ["batch_code", "pen", "breed", "start_date", "start_count",
                       "start_avg_kg", "source", "target_market_date", "status"],
            "sample": ["PIG-B99", "Pen 9", "Large White", "2026-01-01", 20, 8.0,
                       "Own farrowing", "2026-05-01", "Active"],
            "rows": [
                ["PIG-B01", "Pen 1", "Large White", "2025-12-01", 24, 8.5,
                 "Own farrowing", "2026-05-20", "Active"],
                # a second, earlier batch that also lived in Pen 1 - pens
                # get reused, so fetch_pen_summary must return both.
                ["PIG-B00", "Pen 1", "Large White", "2025-06-01", 20, 8.0,
                 "Own farrowing", "2025-11-01", "Sold"],
            ],
        },
        "P2_PIG_DAILY_LOG": {
            "header": ["date", "batch_code", "pen", "feed_type", "feed_kg",
                       "water_litres", "deaths", "culls", "closing_count",
                       "pen_temp_c", "pen_condition", "notes", "recorded_by"],
            "sample": ["2026-09-07", "PIG-B99", "Pen 9", "Pig grower", 42, 110, 0,
                       0, 20, 24, "Dry", None, "S01"],
            "rows": [
                ["2026-01-06", "PIG-B01", "Pen 1", "Pig grower", 50, 100, 0, 0, 24,
                 24, "Dry", None, "S01"],
                ["2026-02-10", "PIG-B01", "Pen 1", "Pig grower", 48, 98, 1, 0, 23,
                 24, "Dry", None, "S01"],
            ],
        },
        "P3_PIG_WEIGHTS": {
            "header": ["date", "batch_code", "sample_size", "avg_weight_kg",
                       "min_weight_kg", "max_weight_kg", "age_days"],
            "sample": ["2026-09-07", "PIG-B99", 10, 45.0, 40.0, 50.0, 90],
            "rows": [["2026-02-10", "PIG-B01", 10, 28.5, 25.0, 32.0, 75]],
        },
        "C1_POULTRY_BATCHES": {
            "header": ["batch_code", "bird_type", "breed", "house",
                       "placement_date", "chicks_placed", "chick_unit_cost",
                       "hatchery", "target_off_date", "status"],
            "sample": ["BRO-99", "Broiler", "Ross 308", "House 9", "2026-08-10",
                       500, 0.55, "Irvine's Zimbabwe", "2026-09-21", "Growing"],
            "rows": [["BRO-01", "Broiler", "Ross 308", "House 1", "2025-12-17",
                      500, 0.55, "Irvine's Zimbabwe", "2026-01-28", "Growing"]],
        },
        "C2_POULTRY_DAILY_LOG": {
            "header": ["date", "batch_code", "age_days", "deaths", "culls",
                       "closing_birds", "feed_type", "feed_kg", "water_litres",
                       "house_temp_c", "litter_condition", "lighting_hours",
                       "eggs_collected", "eggs_cracked", "eggs_dirty", "notes",
                       "recorded_by"],
            "sample": ["2026-09-01", "BRO-99", 22, 2, 0, 498, "Broiler grower",
                       58, 95, 29, "Dry", None, 0, 0, 0, None, "S02"],
            "rows": [["2026-01-06", "BRO-01", 20, 0, 0, 500, "Broiler grower", 30,
                      45, 29, "Dry", None, 0, 0, 0, None, "S02"]],
        },
        "C3_POULTRY_WEIGHTS": {
            "header": ["date", "batch_code", "age_days", "sample_size",
                       "avg_weight_g", "uniformity_pct"],
            "sample": ["2026-09-01", "BRO-99", 22, 10, 1900, 92.0],
            "rows": [["2026-01-06", "BRO-01", 20, 10, 45, 90.0]],
        },
    })


def _seed(tmp_path, dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _lookup_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=dsn)


def test_fetch_pen_summary_returns_every_batch_ever_in_that_pen(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    rows = fetch_pen_summary(db_conn, "Pen 1")

    assert [r["batch_code"] for r in rows] == ["PIG-B01", "PIG-B00"]
    assert rows[0]["headcount"] == 23  # latest closing_count for PIG-B01


def test_fetch_pen_summary_returns_empty_for_an_unknown_pen(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    assert fetch_pen_summary(db_conn, "Pen 99") == []


def test_fetch_batch_summary_finds_a_pig_batch_with_normalized_fields(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    summary = fetch_batch_summary(db_conn, "PIG-B01")

    assert summary["domain"] == "piggery"
    assert summary["location"] == "Pen 1"
    assert summary["headcount"] == 23
    assert float(summary["avg_weight"]) == 28.5
    assert summary["weight_unit"] == "kg"


def test_fetch_batch_summary_finds_a_poultry_batch_with_normalized_fields(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    summary = fetch_batch_summary(db_conn, "BRO-01")

    assert summary["domain"] == "poultry"
    assert summary["location"] == "House 1"
    assert summary["headcount"] == 500
    assert float(summary["avg_weight"]) == 45.0
    assert summary["weight_unit"] == "g"


def test_fetch_batch_summary_returns_none_for_an_unknown_batch(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    assert fetch_batch_summary(db_conn, "NOPE-99") is None
