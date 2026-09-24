import datetime

import openai
import pytest

from chatbot.engine import _run_tool_call, answer_question
from chatbot.tools import InvalidToolArgument, ToolCallResult, q_expenses_to_date, resolve_tool_call
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _expenses_sheet(rows):
    return {
        "header": ["date", "domain", "category", "item", "quantity", "unit",
                   "unit_cost", "total_cost", "supplier", "payment_method",
                   "batch_ref", "allocation_note", "recorded_by"],
        "sample": ["2026-09-01", "poultry", "Feed", "Broiler starter 50kg", 10,
                   "bag", 34, 340, "Profeeds Marondera", "EcoCash", "BRO-24",
                   None, "S01"],
        "rows": rows,
    }


def _expenses_fixture():
    return base_fixture(extra_sheets={
        "02_EXPENSES": _expenses_sheet([
            ["2026-01-10", "piggery", "Feed", "Pig grower 50kg", 20, "bag",
             25, 500, "Profeeds Marondera", "EcoCash", None, None, "S01"],
            ["2026-02-15", "poultry", "Feed", "Broiler starter 50kg", 10,
             "bag", 34, 340, "Profeeds Marondera", "EcoCash", None, None, "S01"],
        ]),
    })


def _seed(tmp_path, dsn, fixture=None):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, fixture or _expenses_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=dsn)


def test_expenses_to_date_question_resolves_via_tier3(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question(
        "What's the expense amount to date?", farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.intent_source == "tool_fallback"
    assert answer.tool_name == "q_expenses_to_date"
    assert "840" in answer.text  # 500 + 340


def test_expenses_to_date_respects_date_range_filter(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    # Only the 2026-01-10 expense (500) falls before this cutoff
    answer = answer_question(
        "What's the expense amount to date?", farm_code="NIS-001", dsn=test_dsn,
        date_to=datetime.date(2026, 1, 31),
    )

    assert "500" in answer.text
    assert "840" not in answer.text


def test_expenses_to_date_scoped_out_when_all_modules_inactive(tmp_path, db_conn, test_dsn):
    fixture = _expenses_fixture()
    fixture["00_FARM_PROFILE"]["rows"][0][5] = "No"  # module_piggery_active
    _seed(tmp_path, test_dsn, fixture)

    answer = answer_question(
        "What's the expense amount to date?", farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.scoped_out_reason == "piggery"


def test_q_expenses_to_date_rejects_invalid_domain_directly(db_conn):
    with pytest.raises(InvalidToolArgument):
        q_expenses_to_date(db_conn, domain="cattle")


def test_run_tool_call_handles_invalid_expense_domain_as_final_failure(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    bad_call = ToolCallResult(tool_name="q_expenses_to_date", arguments={"domain": "cattle"})
    answer = _run_tool_call(db_conn, "NIS-001", "what did we spend on cattle?", bad_call, None, None)

    assert answer.failure_reason == "invalid_tool_argument"


def test_resolve_tool_call_picks_expenses_for_canonical_phrasings():
    client = openai.OpenAI()
    for question in [
        "What's the expense amount to date?",
        "what's the expense amount to date?",  # the real logged failure, exact phrasing
        "how much have we spent so far",
    ]:
        result = resolve_tool_call(question, client)
        assert result.tool_name == "q_expenses_to_date", question
