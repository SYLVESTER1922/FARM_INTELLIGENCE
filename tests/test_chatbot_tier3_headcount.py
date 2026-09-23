import datetime

import openai
import pytest

from chatbot.engine import _run_tool_call, answer_question
from chatbot.tools import InvalidToolArgument, ToolCallResult, q_headcount, resolve_tool_call
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _headcount_fixture():
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
            "rows": [
                ["2026-01-06", "PIG-B01", "Pen 1", "Pig grower", 50, 100, 0, 0, 24,
                 24, "Dry", None, "S01"],
                ["2026-02-10", "PIG-B01", "Pen 1", "Pig grower", 48, 98, 1, 0, 23,
                 24, "Dry", None, "S01"],
            ],
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
            "rows": [
                ["2026-01-06", "BRO-01", 20, 0, 0, 500, "Broiler grower", 30, 45,
                 29, "Dry", None, 0, 0, 0, None, "S02"],
                ["2026-02-10", "BRO-01", 55, 5, 0, 495, "Broiler grower", 28, 44,
                 29, "Dry", None, 0, 0, 0, None, "S02"],
            ],
        },
    })


def _seed(tmp_path, dsn, fixture=None):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, fixture or _headcount_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=dsn)


# ---------------------------------------------------------------------------
# Black-box, through answer_question - the primary seam
# ---------------------------------------------------------------------------

def test_headcount_question_resolves_via_tier3(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question("how many pigs do we have?", farm_code="NIS-001", dsn=test_dsn)

    assert answer.intent_source == "tool_fallback"
    assert answer.tool_name == "q_headcount"
    assert "23" in answer.text  # 24 - 1 death, as of the latest real data date


def test_headcount_respects_date_range_filter(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    # As of 2026-01-06, before the pig death on 2026-02-10
    answer = answer_question(
        "how many pigs do we have?", farm_code="NIS-001", dsn=test_dsn,
        date_to=datetime.date(2026, 1, 6),
    )

    assert "24" in answer.text
    assert "23" not in answer.text


def test_headcount_scoped_out_when_piggery_module_inactive(tmp_path, db_conn, test_dsn):
    fixture = _headcount_fixture()
    fixture["00_FARM_PROFILE"]["rows"][0][5] = "No"  # module_piggery_active
    _seed(tmp_path, test_dsn, fixture)

    answer = answer_question("how many pigs do we have?", farm_code="NIS-001", dsn=test_dsn)

    assert answer.scoped_out_reason == "piggery"
    assert "turned off" in answer.text


def test_missing_parameter_never_escalates_to_tier3(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question(
        "how does feed cost split between pigs and chickens",
        farm_code="NIS-001", dsn=test_dsn,
    )

    # Still the targeted clarifying response from ticket 02, not a tier-3 answer
    assert answer.failure_reason == "missing_parameter"
    assert answer.tool_name is None


def test_tier3_hit_logged_with_tool_name_and_arguments(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer_question("how many pigs do we have?", farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT intent_source, tool_name, tool_arguments FROM query_log "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row[0] == "tool_fallback"
    assert row[1] == "q_headcount"
    assert row[2] is not None  # a JSON object was recorded, even if empty


def test_genuinely_unrelated_question_still_falls_through_tier3_to_unresolved(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question("what's the capital of France", farm_code="NIS-001", dsn=test_dsn)

    assert answer.intent_source == "unresolved"
    assert answer.tool_name is None


# ---------------------------------------------------------------------------
# Argument validation - tested directly against the real validation code,
# not by trying to coax a real LLM into misbehaving (same precedent as
# tier-2's invalid_llm_intent case).
# ---------------------------------------------------------------------------

def test_q_headcount_rejects_invalid_domain_directly(db_conn):
    with pytest.raises(InvalidToolArgument):
        q_headcount(db_conn, domain="cattle")


def test_run_tool_call_handles_invalid_domain_as_final_failure(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    bad_call = ToolCallResult(tool_name="q_headcount", arguments={"domain": "cattle"})
    answer = _run_tool_call(db_conn, "NIS-001", "how many cattle do we have?", bad_call, None, None)

    assert answer.failure_reason == "invalid_tool_argument"
    assert answer.intent_source == "unresolved"


# ---------------------------------------------------------------------------
# Tool-selection seam - the narrow, explicitly-agreed exception (real
# OpenAI call, asserting *which* tool was picked, not the final answer).
# ---------------------------------------------------------------------------

def test_resolve_tool_call_picks_headcount_for_canonical_phrasings():
    client = openai.OpenAI()
    for question in [
        "how many pigs do we have?",
        "How many pigs do we have?",
        "how many chickens do we have right now",
    ]:
        result = resolve_tool_call(question, client)
        assert result.tool_name == "q_headcount", question


def test_resolve_tool_call_picks_no_tool_for_unrelated_question():
    client = openai.OpenAI()
    result = resolve_tool_call("what's the capital of France", client)
    assert result.tool_name is None
