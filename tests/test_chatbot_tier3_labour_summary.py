import openai

from chatbot.engine import answer_question
from chatbot.tools import resolve_tool_call
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _labour_fixture():
    return base_fixture(
        staff_rows=[["S01", "Tendai Moyo", "Herdsman", "piggery", "Daily", 15, "Yes"]],
        extra_sheets={
            "04_LABOUR_LOG": {
                "header": ["date", "staff_code", "domain", "task", "hours",
                           "overtime_hours", "labour_cost", "batch_ref"],
                "sample": ["2026-09-07", "S99", "piggery", "Feeding", 8, 0, 12.0, None],
                "rows": [
                    ["2026-02-01", "S01", "piggery", "Feeding", 8, 2, 15.0, None],
                    ["2026-02-02", "S01", "piggery", "Cleaning", 6, 0, 9.0, None],
                ],
            },
        },
    )


def _seed(tmp_path, dsn, fixture=None):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, fixture or _labour_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=dsn)


def test_labour_summary_resolves_via_tier3_with_real_totals(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question(
        "What's our total labour cost for piggery?", farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.tool_name == "q_labour_summary"
    # 15.0 + 9.0 = 24.0
    assert "24" in answer.text


def test_labour_summary_scoped_out_when_piggery_module_inactive(tmp_path, db_conn, test_dsn):
    fixture = _labour_fixture()
    fixture["00_FARM_PROFILE"]["rows"][0][5] = "No"  # module_piggery_active
    _seed(tmp_path, test_dsn, fixture)

    answer = answer_question(
        "What's our total labour cost for piggery?", farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.scoped_out_reason == "piggery"


def test_resolve_tool_call_picks_labour_summary_for_canonical_phrasings():
    client = openai.OpenAI()
    for question in [
        "What's our total labour cost this month?",
        "how many labour hours did we use",
        "overtime hours for piggery",
    ]:
        result = resolve_tool_call(question, client)
        assert result.tool_name == "q_labour_summary", question
