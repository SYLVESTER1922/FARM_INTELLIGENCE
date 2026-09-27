import datetime

import openai

from chatbot.engine import answer_question
from chatbot.tools import q_mortality_rate, resolve_tool_call
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _mortality_fixture():
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
                ["2026-02-03", "PIG-B01", "Pen 1", "Pig grower", 50, 100, 0, 0, 24,
                 24, "Dry", None, "S01"],
                ["2026-02-10", "PIG-B01", "Pen 1", "Pig grower", 48, 98, 2, 0, 22,
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
                ["2026-02-03", "BRO-01", 20, 0, 0, 500, "Broiler grower", 30, 45,
                 29, "Dry", None, 0, 0, 0, None, "S02"],
                ["2026-02-10", "BRO-01", 27, 5, 0, 495, "Broiler grower", 28, 44,
                 29, "Dry", None, 0, 0, 0, None, "S02"],
            ],
        },
    })


def _seed(tmp_path, dsn, fixture=None):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, fixture or _mortality_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=dsn)


def test_farm_wide_mortality_rate_resolves_via_tier3(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question(
        "What's our mortality rate for the whole farm?", farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.tool_name == "q_mortality_rate"
    # 7 total deaths (2 pig + 5 poultry) / 517 total headcount (22+495) in
    # the default 30-day window ending at the latest data date
    # (2026-02-10) = 1.35%
    assert "1.35" in answer.text or "7" in answer.text


def test_relative_period_death_count_resolves_via_tier3(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question(
        "How many chickens died last week?", farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.tool_name == "q_mortality_rate"
    # both poultry log rows (2026-02-03, 2026-02-10) fall within the last
    # 7 days of the latest data date (2026-02-10) - 5 deaths total. Check
    # both digit and spelled-out forms - the narrator sometimes writes
    # "Five" instead of "5", a harmless phrasing choice, not a wrong number.
    assert "5" in answer.text or "five" in answer.text.lower()


def test_q_mortality_rate_period_takes_precedence_and_computes_real_window(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    result = q_mortality_rate(db_conn, domain="poultry", period="last_7_days")
    expected_start = datetime.date(2026, 2, 10) - datetime.timedelta(days=7)
    assert result["window_start"] == str(expected_start)
    assert result["deaths"] == 5


def test_resolve_tool_call_picks_mortality_rate_for_canonical_phrasings():
    client = openai.OpenAI()
    for question in [
        "What's our mortality rate for the whole farm?",
        "what's our mortality rate for the whole farm?",  # real logged failure, exact
        "How many chickens died last week?",
        "how many chickens died last week?",  # real logged failure, exact
    ]:
        result = resolve_tool_call(question, client)
        assert result.tool_name == "q_mortality_rate", question
