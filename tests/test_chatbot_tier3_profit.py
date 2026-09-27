import openai

from chatbot.engine import answer_question
from chatbot.tools import resolve_tool_call
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _profit_fixture():
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
            ],
        },
        "03_REVENUE": {
            "header": ["date", "domain", "product", "quantity", "unit",
                       "unit_price", "total_amount", "head_count", "avg_weight_kg",
                       "grade", "buyer", "channel", "payment_status", "batch_ref"],
            "sample": ["2026-09-03", "poultry", "Dressed chicken", 48, "head", 6.2,
                       297.6, 48, 2.1, None, "Local market vendor", "Market", "Paid", "BRO-24"],
            "rows": [
                ["2026-01-15", "piggery", "Live pig", 4, "head", 200.0, 800.0,
                 4, None, None, "Local abattoir", "Market", "Paid", None],
                ["2026-01-16", "poultry", "Dressed chicken", 48, "head", 6.2,
                 297.6, 48, 2.1, None, "Local market vendor", "Market", "Paid", None],
            ],
        },
    })


def _seed(tmp_path, dsn, fixture=None):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, fixture or _profit_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=dsn)


def test_piggery_profit_resolves_via_tier3(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question("Is the piggery profitable?", farm_code="NIS-001", dsn=test_dsn)

    assert answer.tool_name == "q_profit"
    # revenue 800.0 - expenses 500.0 = 300.0 profit - a real subtraction,
    # not the old bug's "expenses total, profitability cannot be
    # determined" non-answer
    assert "300" in answer.text


def test_farm_wide_profit_resolves_via_tier3(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question("What's our profit?", farm_code="NIS-001", dsn=test_dsn)

    assert answer.tool_name == "q_profit"
    # farm-wide: (800.0 + 297.6) - (500.0 + 340.0) = 257.6
    assert "257.6" in answer.text or "257.60" in answer.text


def test_resolve_tool_call_picks_profit_for_canonical_phrasings():
    client = openai.OpenAI()
    for question in [
        "Is the piggery profitable?",
        "is the piggery profitable?",  # the real logged failure, exact phrasing
        "are we making money",
    ]:
        result = resolve_tool_call(question, client)
        assert result.tool_name == "q_profit", question
