import datetime

import openai

from chatbot.engine import answer_question
from chatbot.tools import resolve_tool_call
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _weather_fixture():
    return base_fixture(extra_sheets={
        "05_WEATHER_LOG": {
            "header": ["date", "rainfall_mm", "temp_min_c", "temp_max_c",
                       "humidity_pct", "event"],
            "sample": ["2026-09-01", 0, 14, 27, 48, "Normal"],
            "rows": [
                ["2026-01-08", 5, 22, 39, 30, "Heatwave"],
                ["2026-01-09", 45, 18, 24, 78, "Heavy rain"],
            ],
        },
    })


def _seed(tmp_path, dsn, fixture=None):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, fixture or _weather_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=dsn)


def test_weather_question_resolves_via_tier3_to_latest_real_date(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question("what's the weather like today?", farm_code="NIS-001", dsn=test_dsn)

    assert answer.intent_source == "tool_fallback"
    assert answer.tool_name == "q_weather"
    # "today" honestly reflects the latest real logged date's data
    # (rainfall_mm=45), not the calendar date - assert on the real number,
    # not the LLM's own paraphrasing/reformatting of the date or event text
    assert "45" in answer.text


def test_weather_respects_date_range_filter(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question(
        "what's the weather like today?", farm_code="NIS-001", dsn=test_dsn,
        date_to=datetime.date(2026, 1, 8),
    )

    # The 2026-01-08 row (temp_max_c=39), not the later 2026-01-09 row
    # (rainfall_mm=45) - assert on the real numbers, not the LLM's own
    # paraphrasing/reformatting of the date or "event" text.
    assert "39" in answer.text
    assert "45" not in answer.text


def test_weather_is_not_module_scoped(tmp_path, db_conn, test_dsn):
    # Weather is farm-wide - turning off every domain module must not
    # scope out a weather question the way a domain-specific tool would.
    fixture = _weather_fixture()
    fixture["00_FARM_PROFILE"]["rows"][0][5] = "No"  # module_piggery_active
    fixture["00_FARM_PROFILE"]["rows"][0][6] = "No"  # module_poultry_active
    fixture["00_FARM_PROFILE"]["rows"][0][7] = "No"  # module_crops_active
    _seed(tmp_path, test_dsn, fixture)

    answer = answer_question("what's the weather like today?", farm_code="NIS-001", dsn=test_dsn)

    assert answer.scoped_out_reason is None
    assert answer.tool_name == "q_weather"


def test_resolve_tool_call_picks_weather_for_canonical_phrasings():
    client = openai.OpenAI()
    for question in [
        "what's the weather like today?",
        "What's the weather like today?",  # the real logged failure, exact case
        "how much rain have we had",
    ]:
        result = resolve_tool_call(question, client)
        assert result.tool_name == "q_weather", question
