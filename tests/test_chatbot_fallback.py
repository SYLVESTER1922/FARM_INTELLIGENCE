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


def test_llm_fallback_answers_a_rephrased_question_tier1_misses(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "00_FARM_PROFILE": _farm_profile_sheet(),
        **_poultry_mortality_data(),
    }))
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    # deliberately doesn't share enough vocabulary with any tier-1 cluster
    answer = answer_question(
        "are any of our chicken flocks dying off unusually fast this batch",
        farm_code="NIS-001",
        dsn=test_dsn,
    )

    assert "BRO-P02" in answer.text
    assert answer.intent_source == "llm_fallback"
    assert answer.query_id == "poultry_mortality_spike"


def test_llm_fallback_resolved_intent_is_still_scoped_out_when_module_inactive(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "00_FARM_PROFILE": _farm_profile_sheet(poultry="No"),
        **_poultry_mortality_data(),
    }))
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    answer = answer_question(
        "are any of our chicken flocks dying off unusually fast this batch",
        farm_code="NIS-001",
        dsn=test_dsn,
    )

    assert answer.intent_source == "llm_fallback"
    assert answer.query_id == "poultry_mortality_spike"
    assert answer.scoped_out_reason == "poultry"
    assert "BRO-P02" not in answer.text  # never leaks the underlying data
