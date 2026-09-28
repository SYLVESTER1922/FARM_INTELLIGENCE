import openai
import pytest

from chatbot.engine import answer_question
from chatbot.tools import InvalidToolArgument, q_revenue_breakdown, resolve_tool_call
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _revenue_fixture():
    return base_fixture(extra_sheets={
        "03_REVENUE": {
            "header": ["date", "domain", "product", "quantity", "unit",
                       "unit_price", "total_amount", "head_count",
                       "avg_weight_kg", "grade", "buyer", "channel",
                       "payment_status", "batch_ref"],
            "sample": ["2026-09-07", "piggery", "Live pig", 5, "head", 120,
                       600.0, 5, 85.0, "A", "Sample Buyer", "Farm gate",
                       "Paid", None],
            "rows": [
                ["2026-02-01", "piggery", "Live pig", 5, "head", 120,
                 600.0, 5, 85.0, "A", "Chikwanha Butchery", "Farm gate",
                 "Paid", None],
                ["2026-02-08", "piggery", "Live pig", 10, "head", 120,
                 1200.0, 10, 85.0, "A", "Chikwanha Butchery", "Farm gate",
                 "Paid", None],
                ["2026-02-15", "piggery", "Live pig", 2, "head", 120,
                 240.0, 2, 85.0, "A", "Manyame Traders", "Farm gate",
                 "Paid", None],
            ],
        },
    })


def _seed(tmp_path, dsn, fixture=None):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, fixture or _revenue_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=dsn)


def test_revenue_breakdown_resolves_via_tier3_with_real_top_buyer(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question(
        "Who's our biggest buyer for piggery?", farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.tool_name == "q_revenue_breakdown"
    assert "Chikwanha Butchery" in answer.text
    # 600 + 1200 = 1800 total for that buyer
    assert "1800" in answer.text or "1,800" in answer.text


def test_revenue_breakdown_scoped_out_when_piggery_module_inactive(tmp_path, db_conn, test_dsn):
    fixture = _revenue_fixture()
    fixture["00_FARM_PROFILE"]["rows"][0][5] = "No"  # module_piggery_active
    _seed(tmp_path, test_dsn, fixture)

    answer = answer_question(
        "Who's our biggest buyer for piggery?", farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.scoped_out_reason == "piggery"


def test_q_revenue_breakdown_rejects_missing_by():
    with pytest.raises(InvalidToolArgument):
        q_revenue_breakdown(None, by=None)


def test_q_revenue_breakdown_rejects_invalid_by():
    with pytest.raises(InvalidToolArgument):
        q_revenue_breakdown(None, by="region")


def test_resolve_tool_call_picks_revenue_breakdown_for_canonical_phrasings():
    client = openai.OpenAI()
    for question in [
        "Who's our biggest buyer?",
        "what's our best-selling product",
        "top customers for piggery",
    ]:
        result = resolve_tool_call(question, client)
        assert result.tool_name == "q_revenue_breakdown", question
