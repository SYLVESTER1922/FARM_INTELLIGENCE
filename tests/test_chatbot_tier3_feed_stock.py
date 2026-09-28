import openai

from chatbot.engine import answer_question
from chatbot.tools import resolve_tool_call
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _feed_stock_fixture():
    return base_fixture(extra_sheets={
        "06_FEED_INVENTORY": {
            "header": ["date", "domain", "feed_type", "opening_kg", "received_kg",
                       "used_kg", "waste_kg", "closing_kg", "unit_cost_per_kg",
                       "supplier", "batch_ref"],
            "sample": ["2026-09-07", "piggery", "Pig grower", 500, 0, 50, 0, 450,
                       0.5, "Profeeds", None],
            "rows": [
                ["2026-02-01", "piggery", "Pig grower", 500, 0, 100, 0, 400,
                 0.5, "Profeeds", None],
                ["2026-02-02", "piggery", "Pig grower", 400, 0, 50, 0, 350,
                 0.5, "Profeeds", None],
                ["2026-02-01", "poultry", "Broiler grower", 300, 0, 100, 0, 200,
                 0.6, "Profeeds", None],
            ],
        },
    })


def _seed(tmp_path, dsn, fixture=None):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, fixture or _feed_stock_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=dsn)


def test_feed_stock_resolves_via_tier3_with_latest_closing_kg(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question(
        "How much pig feed do we have left?", farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.tool_name == "q_feed_stock"
    # latest closing_kg for piggery Pig grower is 350, not the earlier 400
    assert "350" in answer.text


def test_feed_stock_scoped_out_when_piggery_module_inactive(tmp_path, db_conn, test_dsn):
    fixture = _feed_stock_fixture()
    fixture["00_FARM_PROFILE"]["rows"][0][5] = "No"  # module_piggery_active
    _seed(tmp_path, test_dsn, fixture)

    answer = answer_question(
        "How much pig feed do we have left?", farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.scoped_out_reason == "piggery"


def test_resolve_tool_call_picks_feed_stock_for_canonical_phrasings():
    client = openai.OpenAI()
    for question in [
        "How much feed do we have left?",
        "are we running low on feed",
        "current feed stock for poultry",
    ]:
        result = resolve_tool_call(question, client)
        assert result.tool_name == "q_feed_stock", question
