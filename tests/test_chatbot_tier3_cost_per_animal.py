import openai
import pytest

from chatbot.engine import answer_question
from chatbot.tools import InvalidToolArgument, q_cost_per_animal, resolve_tool_call
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _cost_per_animal_fixture():
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
            "sample": ["2026-09-07", "PIG-B99", "Pen 9", "Pig grower", 42, 110, 0,
                       0, 20, 24, "Dry", None, "S01"],
            "rows": [["2026-01-06", "PIG-B01", "Pen 1", "Pig grower", 50, 100, 0,
                      0, 20, 24, "Dry", None, "S01"]],
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
        "02_EXPENSES": {
            "header": ["date", "domain", "category", "item", "quantity", "unit",
                       "unit_cost", "total_cost", "supplier", "payment_method",
                       "batch_ref", "allocation_note", "recorded_by"],
            "sample": ["2026-09-01", "poultry", "Feed", "Broiler starter 50kg", 10,
                       "bag", 34, 340, "Profeeds Marondera", "EcoCash", None, None, "S01"],
            "rows": [["2026-01-10", "piggery", "Feed", "Pig grower 50kg", 20, "bag",
                      25, 500, "Profeeds Marondera", "EcoCash", None, None, "S01"]],
        },
    })


def _seed(tmp_path, dsn, fixture=None):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, fixture or _cost_per_animal_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=dsn)


def test_cost_per_pig_resolves_via_tier3_with_a_real_division(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question("What's the cost per pig?", farm_code="NIS-001", dsn=test_dsn)

    assert answer.tool_name == "q_cost_per_animal"
    # 500 total expenses / 20 headcount = 25.0 - the real division must
    # appear, not just the raw total restated (the bug this tool fixes:
    # the old narration claimed a calculation "based on" the total without
    # ever dividing).
    assert "25" in answer.text


def test_q_cost_per_animal_rejects_missing_domain():
    with pytest.raises(InvalidToolArgument):
        q_cost_per_animal(None, domain=None)


def test_q_cost_per_animal_rejects_invalid_domain():
    with pytest.raises(InvalidToolArgument):
        q_cost_per_animal(None, domain="cattle")


def test_resolve_tool_call_picks_cost_per_animal_for_canonical_phrasings():
    client = openai.OpenAI()
    for question in [
        "What's the cost per pig?",
        "what's the cost per pig?",  # the real logged failure, exact phrasing
        "cost per bird",
    ]:
        result = resolve_tool_call(question, client)
        assert result.tool_name == "q_cost_per_animal", question
