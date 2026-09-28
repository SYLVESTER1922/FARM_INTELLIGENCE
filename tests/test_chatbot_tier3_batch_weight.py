import openai
import pytest

from chatbot.engine import answer_question
from chatbot.tools import InvalidToolArgument, q_batch_weight, resolve_tool_call
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _weight_fixture():
    return base_fixture(extra_sheets={
        "P1_PIG_BATCHES": {
            "header": ["batch_code", "pen", "breed", "start_date", "start_count",
                       "start_avg_kg", "source", "target_market_date", "status"],
            "sample": ["PIG-B99", "Pen 9", "Large White", "2026-01-01", 20, 8.0,
                       "Own farrowing", "2026-05-01", "Active"],
            "rows": [
                ["PIG-B01", "Pen 1", "Large White", "2025-12-01", 24, 8.5,
                 "Own farrowing", "2026-05-20", "Active"],
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
                ["2026-02-20", "PIG-B01", "Pen 1", "Pig grower", 100, 100, 0, 0, 24,
                 24, "Dry", None, "S01"],
            ],
        },
        "P3_PIG_WEIGHTS": {
            "header": ["date", "batch_code", "sample_size", "avg_weight_kg",
                       "min_weight_kg", "max_weight_kg", "age_days"],
            "sample": ["2026-09-07", "PIG-B99", 10, 45.0, 40.0, 50.0, 90],
            "rows": [
                ["2026-01-15", "PIG-B01", 10, 20.0, 18.0, 22.0, 45],
                ["2026-02-15", "PIG-B01", 10, 28.5, 25.0, 32.0, 75],
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
        "C3_POULTRY_WEIGHTS": {
            "header": ["date", "batch_code", "sample_size", "avg_weight_g", "recorded_by"],
            "sample": ["2026-09-01", "BRO-99", 10, 1900, "S02"],
            "rows": [],
        },
    })


def _seed(tmp_path, dsn, fixture=None):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, fixture or _weight_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=dsn)


def test_batch_weight_resolves_via_tier3_with_latest_sample(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question(
        "What's the average weight of batch PIG-B01?", farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.tool_name == "q_batch_weight"
    # latest sample is 28.5kg (2026-02-15), not the earlier 20.0kg
    assert "28.5" in answer.text
    assert "20.0" not in answer.text


def test_batch_weight_scoped_out_when_piggery_module_inactive(tmp_path, db_conn, test_dsn):
    fixture = _weight_fixture()
    fixture["00_FARM_PROFILE"]["rows"][0][5] = "No"  # module_piggery_active
    _seed(tmp_path, test_dsn, fixture)

    answer = answer_question(
        "What's the average weight of batch PIG-B01?", farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.scoped_out_reason == "piggery"


def test_q_batch_weight_rejects_neither_domain_nor_batch_code():
    with pytest.raises(InvalidToolArgument):
        q_batch_weight(None, domain=None, batch_code=None)


def test_q_batch_weight_rejects_invalid_domain():
    with pytest.raises(InvalidToolArgument):
        q_batch_weight(None, domain="cattle")


def test_resolve_tool_call_picks_batch_weight_for_canonical_phrasings():
    client = openai.OpenAI()
    for question in [
        "What's the average weight of batch PIG-B01?",
        "how heavy are the pigs right now",
        "current growth weight for batch PIG-B01",
    ]:
        result = resolve_tool_call(question, client)
        assert result.tool_name == "q_batch_weight", question
