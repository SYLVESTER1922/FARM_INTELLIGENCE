import openai

from chatbot.engine import answer_question
from chatbot.tools import resolve_tool_call
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _expenses_by_domain_fixture():
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
                ["2026-01-12", "poultry", "Feed", "Broiler starter 50kg", 10, "bag",
                 34, 340, "Profeeds Marondera", "EcoCash", None, None, "S01"],
                ["2026-01-14", "crops", "Seed", "Maize seed 10kg", 5, "bag",
                 20, 100, "Seed Co", "EcoCash", None, None, "S01"],
            ],
        },
    })


def _seed(tmp_path, dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _expenses_by_domain_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=dsn)


def test_compare_domains_resolves_via_tier3_with_all_three_totals(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question(
        "Compare piggery and poultry costs this year", farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.tool_name == "q_expenses_by_domain"
    # the real bug this tool fixes: the old tool only ever returned ONE
    # domain's total and admitted "poultry costs not provided" - now both
    # real figures must appear together
    assert "500" in answer.text
    assert "340" in answer.text


def test_resolve_tool_call_picks_expenses_by_domain_for_canonical_phrasings():
    client = openai.OpenAI()
    for question in [
        "Compare piggery and poultry costs this year",
        "compare piggery and poultry costs this year",  # real logged failure, exact
        "which domain costs more, piggery or poultry",
    ]:
        result = resolve_tool_call(question, client)
        assert result.tool_name == "q_expenses_by_domain", question
