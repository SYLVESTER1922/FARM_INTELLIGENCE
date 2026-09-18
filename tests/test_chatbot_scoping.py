from chatbot.engine import answer_question
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook

FARM_PROFILE_HEADER = ["farm_code", "farm_name", "region_district", "currency",
                        "total_hectares", "module_piggery_active",
                        "module_poultry_active", "module_crops_active",
                        "financial_year_start"]
FARM_PROFILE_SAMPLE = ["NIS-999", "Sample Farm", "Sample District", "USD", 10,
                        "Yes", "Yes", "Yes", "2026-01-01"]


def _farm_profile_sheet(piggery="Yes", poultry="Yes", crops="Yes"):
    return {
        "header": FARM_PROFILE_HEADER,
        "sample": FARM_PROFILE_SAMPLE,
        "rows": [["NIS-001", "Chiedza Mixed Farm", "Goromonzi, Mashonaland East",
                  "USD", 45, piggery, poultry, crops, "2026-01-01"]],
    }


def _poultry_mortality_data():
    return {
        "C1_POULTRY_BATCHES": {
            "header": ["batch_code", "bird_type", "breed", "house",
                       "placement_date", "chicks_placed", "chick_unit_cost",
                       "hatchery", "target_off_date", "status"],
            "sample": ["BRO-99", "Broiler", "Ross 308", "House 9", "2026-08-10",
                       500, 0.55, "Irvine's Zimbabwe", "2026-09-21", "Growing"],
            "rows": [["BRO-P02", "Broiler", "Ross 308", "House 2", "2025-12-20",
                      520, 0.55, "Irvine's Zimbabwe", "2026-01-31", "Growing"]],
        },
        "C2_POULTRY_DAILY_LOG": {
            "header": ["date", "batch_code", "age_days", "deaths", "culls",
                       "closing_birds", "feed_type", "feed_kg", "water_litres",
                       "house_temp_c", "litter_condition", "lighting_hours",
                       "eggs_collected", "eggs_cracked", "eggs_dirty", "notes",
                       "recorded_by"],
            "sample": ["2026-09-01", "BRO-99", 22, 2, 0, 498, "Broiler grower",
                       58, 95, 29, "Dry", None, 0, 0, 0, None, "S02"],
            "rows": [["2025-12-21", "BRO-P02", 1, 42, 0, 478, "Chick mash", 10,
                      15, 33, "Dry", 23, 0, 0, 0, "Heat stress", "S02"]],
        },
    }


def test_answer_question_answers_normally_when_module_active(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "00_FARM_PROFILE": _farm_profile_sheet(poultry="Yes"),
        **_poultry_mortality_data(),
    }))
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    answer = answer_question(
        "which poultry batch has the worst mortality",
        farm_code="NIS-001",
        dsn=test_dsn,
    )

    assert "BRO-P02" in answer.text
    assert answer.intent_source == "deterministic"
    assert answer.query_id == "poultry_mortality_spike"
    assert answer.scoped_out_reason is None


def test_answer_question_scopes_out_when_module_inactive(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "00_FARM_PROFILE": _farm_profile_sheet(poultry="No"),
        **_poultry_mortality_data(),
    }))
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    answer = answer_question(
        "which poultry batch has the worst mortality",
        farm_code="NIS-001",
        dsn=test_dsn,
    )

    assert answer.intent_source == "deterministic"
    assert answer.query_id == "poultry_mortality_spike"
    assert answer.failure_reason is None
    assert answer.scoped_out_reason == "poultry"
    assert "poultry" in answer.text.lower()
    assert "turned off" in answer.text.lower() or "not active" in answer.text.lower()


def test_scoped_out_query_log_row(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "00_FARM_PROFILE": _farm_profile_sheet(poultry="No"),
        **_poultry_mortality_data(),
    }))
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    answer_question(
        "which poultry batch has the worst mortality",
        farm_code="NIS-001",
        dsn=test_dsn,
    )

    row = db_conn.execute(
        "SELECT intent_source, query_id, failure_reason, scoped_out_reason "
        "FROM query_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row == ("deterministic", "poultry_mortality_spike", None, "poultry")


def _feed_cost_data():
    return {
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
    }


def test_cross_domain_query_scoped_out_when_either_domain_inactive(tmp_path, db_conn, test_dsn):
    # piggery active, poultry inactive - a cross-domain query must still be
    # refused, not silently answered with only piggery's half of the data
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "00_FARM_PROFILE": _farm_profile_sheet(piggery="Yes", poultry="No"),
        **_feed_cost_data(),
    }))
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    answer = answer_question(
        "how does feed cost split between pigs and chickens in January 2026",
        farm_code="NIS-001",
        dsn=test_dsn,
    )

    assert answer.query_id == "feed_cost_split"
    assert answer.scoped_out_reason == "poultry"
    assert "50.00" not in answer.text  # never leaks the piggery-only partial answer
