import openai

from chatbot.engine import answer_question
from chatbot.tools import resolve_tool_call
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _expense_category_fixture():
    return base_fixture(extra_sheets={
        "02_EXPENSES": {
            "header": ["date", "domain", "category", "item", "quantity", "unit",
                       "unit_cost", "total_cost", "supplier", "payment_method",
                       "batch_ref", "allocation_note", "recorded_by"],
            "sample": ["2026-09-01", "poultry", "Feed", "Broiler starter 50kg", 10,
                       "bag", 34, 340, "Profeeds Marondera", "EcoCash", None, None, "S01"],
            "rows": [
                ["2026-01-10", "piggery", "Feed", "Pig grower 50kg", 20, "bag",
                 25, 500, "Profeeds Marondera", "EcoCash", None, None, "S01"],
                ["2026-01-11", "piggery", "Vet", "Antibiotics", 1, "course",
                 40, 40, "VetPharm", "EcoCash", None, None, "S01"],
                ["2026-01-12", "poultry", "Labour", "Casual labour", 2, "day",
                 15, 30, None, "Cash", None, None, "S01"],
            ],
        },
    })


def _seed(tmp_path, dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _expense_category_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=dsn)


def test_biggest_expense_category_resolves_via_tier3_not_domain(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question(
        "What's our biggest expense category overall?", farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.tool_name == "q_expense_by_category"
    # Feed (500) is the biggest category - not "piggery", which is a
    # domain, not a category (the real bug this fixes)
    assert "Feed" in answer.text
    assert "500" in answer.text
    assert "piggery" not in answer.text.lower()
    assert "poultry" not in answer.text.lower()


def test_resolve_tool_call_picks_expense_by_category_for_canonical_phrasings():
    client = openai.OpenAI()
    for question in [
        "What's our biggest expense category overall?",
        "what's our biggest expense category overall?",  # real logged failure, exact
        "how much do we spend on feed versus labour",
    ]:
        result = resolve_tool_call(question, client)
        assert result.tool_name == "q_expense_by_category", question
