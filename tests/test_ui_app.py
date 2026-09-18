import ui.app
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook
from ui.app import GENERIC_ERROR_MESSAGE, handle_message


def _feed_cost_fixture():
    return base_fixture(extra_sheets={
        "P1_PIG_BATCHES": {
            "header": ["batch_code", "pen", "breed", "start_date", "start_count",
                       "start_avg_kg", "source", "target_market_date", "status"],
            "sample": ["PIG-B99", "Pen 9", "Large White", "2026-01-01", 20, 8.0,
                       "Own farrowing", "2026-05-01", "Active"],
            "rows": [["PIG-B01", "Pen 1", "Large White", "2025-12-01", 24, 8.5,
                      "Own farrowing", "2026-05-20", "Active"]],
        },
        "P2_PIG_DAILY_LOG": {
            "header": ["date", "batch_code", "pen", "feed_type", "feed_kg",
                       "water_litres", "deaths", "culls", "closing_count",
                       "pen_temp_c", "pen_condition", "notes", "recorded_by"],
            "sample": ["2026-09-07", "PIG-B99", "Pen 9", "Pig grower", 42, 110,
                       0, 0, 20, 24, "Dry", None, "S01"],
            "rows": [["2026-01-06", "PIG-B01", "Pen 1", "Pig grower", 50, 100,
                      0, 0, 24, 24, "Dry", None, "S01"]],
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
            "rows": [["2026-01-06", "BRO-01", 20, 0, 0, 500, "Broiler grower",
                      30, 45, 29, "Dry", None, 0, 0, 0, None, "S02"]],
        },
        "06_FEED_INVENTORY": {
            "header": ["date", "domain", "feed_type", "opening_kg",
                       "received_kg", "used_kg", "waste_kg", "closing_kg",
                       "unit_cost_per_kg", "supplier", "batch_ref"],
            "sample": ["2026-09-07", "piggery", "Pig grower", 1200, 500, 430, 5,
                       1265, 0.68, "Profeeds Marondera", None],
            "rows": [
                ["2026-01-05", "piggery", "Pig grower", 400, 250, 50, 0.5,
                 599.5, 1.00, "Profeeds Marondera", None],
                ["2026-01-05", "poultry", "Broiler grower", 300, 200, 30, 0.5,
                 469.5, 1.50, "Profeeds Marondera", None],
            ],
        },
    })


def test_handle_message_answers_a_real_question(tmp_path, db_conn, test_dsn, monkeypatch):
    monkeypatch.setenv("FARM_INTELLIGENCE_DB_DSN", test_dsn)
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _feed_cost_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    text = handle_message(
        "how does feed cost split between pigs and chickens in January 2026"
    )

    assert "50.00" in text or "50.0" in text
    assert "45.00" in text or "45.0" in text


def test_handle_message_returns_generic_message_when_dsn_env_var_missing(monkeypatch):
    monkeypatch.delenv("FARM_INTELLIGENCE_DB_DSN", raising=False)

    text = handle_message("hey")

    assert text == GENERIC_ERROR_MESSAGE


def test_handle_message_returns_generic_message_when_answer_question_raises(monkeypatch):
    monkeypatch.setenv("FARM_INTELLIGENCE_DB_DSN", "host=localhost dbname=doesnotmatter")

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated database outage")

    monkeypatch.setattr(ui.app, "answer_question", _boom)

    text = handle_message("how does feed cost split between pigs and chickens")

    assert text == GENERIC_ERROR_MESSAGE
