import openai

from chatbot.engine import answer_question
from chatbot.tools import resolve_tool_call
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _health_fixture():
    return base_fixture(extra_sheets={
        "P1_PIG_BATCHES": {
            "header": ["batch_code", "pen", "breed", "start_date", "start_count",
                       "start_avg_kg", "source", "target_market_date", "status"],
            "sample": ["PIG-B99", "Pen 9", "Large White", "2026-01-01", 20, 8.0,
                       "Own farrowing", "2026-05-01", "Active"],
            "rows": [
                ["PIG-B01", "Pen 1", "Large White", "2025-12-01", 24, 8.5,
                 "Own farrowing", "2026-05-20", "Active"],
            ],
        },
        "07_HEALTH_LOG": {
            "header": ["date", "domain", "batch_ref", "animal_tag", "event_type",
                       "symptom", "diagnosis", "product", "dose",
                       "animals_treated", "cost", "withdrawal_until", "outcome",
                       "administered_by"],
            "sample": ["2026-09-07", "piggery", "PIG-B99", None, "Treatment",
                       "Cough", "Respiratory infection", "Amoxicillin", "5ml",
                       3, 15.0, "2026-09-14", "Recovered", "S01"],
            "rows": [
                ["2026-02-01", "piggery", "PIG-B01", None, "Treatment",
                 "Cough", "Respiratory infection", "Amoxicillin", "5ml",
                 3, 15.0, "2026-02-08", "Recovered", "S01"],
                ["2026-02-05", "piggery", "PIG-B01", None, "Vaccination",
                 None, None, "PRRS vaccine", "2ml",
                 24, 30.0, None, None, "S01"],
            ],
        },
    })


def _seed(tmp_path, dsn, fixture=None):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, fixture or _health_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=dsn)


def test_health_cost_summary_resolves_via_tier3_with_real_totals(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question(
        "How much have we spent on vet care for piggery?", farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.tool_name == "q_health_cost_summary"
    # 15.0 + 30.0 = 45.0 total cost, across a Treatment and a Vaccination event
    assert "45" in answer.text
    assert "Treatment" in answer.text
    assert "Vaccination" in answer.text


def test_health_cost_summary_scoped_out_when_piggery_module_inactive(tmp_path, db_conn, test_dsn):
    fixture = _health_fixture()
    fixture["00_FARM_PROFILE"]["rows"][0][5] = "No"  # module_piggery_active
    _seed(tmp_path, test_dsn, fixture)

    answer = answer_question(
        "How much have we spent on vet care for piggery?", farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.scoped_out_reason == "piggery"


def test_resolve_tool_call_picks_health_cost_summary_for_canonical_phrasings():
    client = openai.OpenAI()
    for question in [
        "How much have we spent on vet care this month?",
        "health events this month for piggery",
        "vet cost trend",
    ]:
        result = resolve_tool_call(question, client)
        assert result.tool_name == "q_health_cost_summary", question
