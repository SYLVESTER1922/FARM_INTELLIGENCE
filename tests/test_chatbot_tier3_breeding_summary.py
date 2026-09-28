import openai

from chatbot.engine import answer_question
from chatbot.tools import resolve_tool_call
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _breeding_fixture():
    return base_fixture(extra_sheets={
        # breeding_farrowing.litter_batch_code REFERENCES pig_batches(batch_code)
        # - the table must exist for CREATE TABLE to succeed, even with no rows.
        "P1_PIG_BATCHES": {
            "header": ["batch_code", "pen", "breed", "start_date", "start_count",
                       "start_avg_kg", "source", "target_market_date", "status"],
            "sample": ["PIG-B99", "Pen 9", "Large White", "2026-01-01", 20, 8.0,
                       "Own farrowing", "2026-05-01", "Active"],
            "rows": [],
        },
        "P4_SOW_REGISTER": {
            "header": ["sow_tag", "breed", "date_of_birth", "parity",
                       "body_condition_1_5", "status"],
            "sample": ["SOW-99", "Large White", "2024-01-01", 2, 3, "Active"],
            "rows": [
                ["SOW-1", "Large White", "2024-01-01", 2, 3, "Active"],
                ["SOW-2", "Large White", "2024-02-01", 1, 3, "Active"],
            ],
        },
        "P5_BREEDING_FARROWING": {
            "header": ["sow_tag", "boar_tag", "service_date", "service_type",
                       "pregnancy_confirmed", "expected_farrow_date", "farrow_date",
                       "born_alive", "stillborn", "mummified",
                       "avg_birth_weight_kg", "wean_date", "weaned_count",
                       "avg_wean_weight_kg", "litter_batch_code"],
            "sample": ["SOW-99", "BOAR-1", "2026-01-01", "AI", "Yes",
                       "2026-04-25", "2026-04-25", 10, 1, 0, 1.4,
                       "2026-05-25", 9, 7.0, None],
            "rows": [
                ["SOW-1", "BOAR-1", "2026-01-01", "AI", "Yes",
                 "2026-04-25", "2026-04-25", 12, 1, 0, 1.4,
                 "2026-05-25", 11, 7.0, None],
                ["SOW-2", "BOAR-1", "2026-01-05", "AI", "Yes",
                 "2026-04-29", "2026-04-29", 8, 0, 0, 1.5,
                 "2026-05-29", 8, 7.2, None],
            ],
        },
    })


def _seed(tmp_path, dsn, fixture=None):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, fixture or _breeding_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=dsn)


def test_breeding_summary_resolves_via_tier3_with_real_totals(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question(
        "How many litters did we have and which sow had the biggest litter?",
        farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.tool_name == "q_breeding_summary"
    assert "2" in answer.text  # 2 litters
    assert "SOW-1" in answer.text  # best sow: 12 born alive vs 8
    assert "12" in answer.text


def test_breeding_summary_scoped_out_when_piggery_module_inactive(tmp_path, db_conn, test_dsn):
    fixture = _breeding_fixture()
    fixture["00_FARM_PROFILE"]["rows"][0][5] = "No"  # module_piggery_active
    _seed(tmp_path, test_dsn, fixture)

    answer = answer_question(
        "How many litters did we have this month?", farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.scoped_out_reason == "piggery"


def test_resolve_tool_call_picks_breeding_summary_for_canonical_phrasings():
    client = openai.OpenAI()
    for question in [
        "How many litters this month?",
        "what's the average litter size",
        "which sow had the biggest litter",
    ]:
        result = resolve_tool_call(question, client)
        assert result.tool_name == "q_breeding_summary", question
