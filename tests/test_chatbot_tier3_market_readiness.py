import openai

from chatbot.engine import answer_question
from chatbot.tools import resolve_tool_call
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _market_fixture():
    return base_fixture(extra_sheets={
        "P1_PIG_BATCHES": {
            "header": ["batch_code", "pen", "breed", "start_date", "start_count",
                       "start_avg_kg", "source", "target_market_date", "status"],
            "sample": ["PIG-B99", "Pen 9", "Large White", "2026-01-01", 20, 8.0,
                       "Own farrowing", "2026-05-01", "Active"],
            "rows": [
                # overdue relative to the latest daily-log date below (2026-02-01)
                ["PIG-B01", "Pen 1", "Large White", "2025-11-01", 24, 8.5,
                 "Own farrowing", "2026-01-15", "Active"],
                # far in the future - not upcoming within 30 days
                ["PIG-B02", "Pen 2", "Large White", "2025-12-01", 24, 8.5,
                 "Own farrowing", "2026-08-01", "Active"],
            ],
        },
        "P2_PIG_DAILY_LOG": {
            "header": ["date", "batch_code", "pen", "feed_type", "feed_kg",
                       "water_litres", "deaths", "culls", "closing_count",
                       "pen_temp_c", "pen_condition", "notes", "recorded_by"],
            "sample": ["2026-09-07", "PIG-B99", "Pen 9", "Pig grower", 42, 110, 0,
                       0, 20, 24, "Dry", None, "S01"],
            "rows": [
                ["2026-02-01", "PIG-B01", "Pen 1", "Pig grower", 100, 100, 0, 0, 24,
                 24, "Dry", None, "S01"],
            ],
        },
        "C1_POULTRY_BATCHES": {
            "header": ["batch_code", "bird_type", "breed", "house",
                       "placement_date", "chicks_placed", "chick_unit_cost",
                       "hatchery", "target_off_date", "status"],
            "sample": ["BRO-99", "Broiler", "Ross 308", "House 9", "2026-08-10",
                       500, 0.55, "Irvine's Zimbabwe", "2026-09-21", "Growing"],
            "rows": [],
        },
        "C2_POULTRY_DAILY_LOG": {
            "header": ["date", "batch_code", "age_days", "deaths", "culls",
                       "closing_birds", "feed_type", "feed_kg", "water_litres",
                       "house_temp_c", "litter_condition", "lighting_hours",
                       "eggs_collected", "eggs_cracked", "eggs_dirty", "notes",
                       "recorded_by"],
            "sample": ["2026-09-01", "BRO-99", 22, 2, 0, 498, "Broiler grower",
                       58, 95, 29, "Dry", None, 0, 0, 0, None, "S02"],
            "rows": [],
        },
    })


def _seed(tmp_path, dsn, fixture=None):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, fixture or _market_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=dsn)


def test_market_readiness_resolves_via_tier3_with_real_overdue_batch(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question(
        "Which pig batches are overdue for market?", farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.tool_name == "q_market_readiness"
    assert "PIG-B01" in answer.text


def test_market_readiness_scoped_out_when_piggery_module_inactive(tmp_path, db_conn, test_dsn):
    fixture = _market_fixture()
    fixture["00_FARM_PROFILE"]["rows"][0][5] = "No"  # module_piggery_active
    _seed(tmp_path, test_dsn, fixture)

    answer = answer_question(
        "Which pig batches are overdue for market?", farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.scoped_out_reason == "piggery"


def test_resolve_tool_call_picks_market_readiness_for_canonical_phrasings():
    client = openai.OpenAI()
    for question in [
        "Which batches are ready to sell?",
        "are any pigs overdue for market",
        "upcoming off-take for poultry",
    ]:
        result = resolve_tool_call(question, client)
        assert result.tool_name == "q_market_readiness", question
