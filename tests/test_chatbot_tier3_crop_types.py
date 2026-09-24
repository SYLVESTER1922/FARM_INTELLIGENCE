import datetime

import openai

from chatbot.engine import answer_question
from chatbot.tools import resolve_tool_call
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _plots_sheet(rows):
    return {
        "header": ["plot_code", "plot_name", "hectares", "soil_type",
                   "irrigation_type", "gps"],
        "sample": ["P9", "Sample field", 6, "Clay loam", "Sprinkler", None],
        "rows": rows,
    }


def _plantings_sheet(rows):
    return {
        "header": ["planting_code", "plot_code", "crop", "variety", "season",
                   "planting_date", "area_ha", "seed_kg", "seed_cost",
                   "expected_harvest_date", "expected_yield_tons_ha", "status"],
        "sample": ["MZ-P9-2025A", "P9", "Maize", "SC637", "2025 Summer",
                   "2025-11-15", 6, 150, 210, "2026-04-15", 5.5, "Growing"],
        "rows": rows,
    }


def _crop_types_fixture():
    return base_fixture(extra_sheets={
        "F1_PLOTS": _plots_sheet([
            ["P1", "North field", 10, "Clay loam", "Sprinkler", None],
            ["P2", "South field", 5, "Sandy loam", "Rain-fed", None],
        ]),
        "F2_PLANTINGS": _plantings_sheet([
            ["MZ-P1-2026A", "P1", "Maize", "SC637", "2026 Summer",
             "2026-01-10", 10, 250, 350, "2026-06-15", 5.5, "Growing"],
            ["SB-P2-2026A", "P2", "Soya", "SC Squire", "2026 Summer",
             "2026-02-15", 5, 100, 200, "2026-07-01", 2.5, "Growing"],
        ]),
    })


def _seed(tmp_path, dsn, fixture=None):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, fixture or _crop_types_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=dsn)


def test_crop_types_question_resolves_via_tier3(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question("What crops do we have?", farm_code="NIS-001", dsn=test_dsn)

    assert answer.intent_source == "tool_fallback"
    assert answer.tool_name == "q_crop_types"
    assert "Maize" in answer.text
    assert "Soya" in answer.text


def test_crop_types_respects_date_range_filter(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question(
        "What crops do we have?", farm_code="NIS-001", dsn=test_dsn,
        date_from=datetime.date(2026, 1, 1), date_to=datetime.date(2026, 1, 31),
    )

    assert "Maize" in answer.text
    assert "Soya" not in answer.text


def test_crop_types_scoped_out_when_crops_module_inactive(tmp_path, db_conn, test_dsn):
    fixture = _crop_types_fixture()
    fixture["00_FARM_PROFILE"]["rows"][0][7] = "No"  # module_crops_active
    _seed(tmp_path, test_dsn, fixture)

    answer = answer_question("What crops do we have?", farm_code="NIS-001", dsn=test_dsn)

    assert answer.scoped_out_reason == "crops"


def test_resolve_tool_call_picks_crop_types_for_canonical_phrasings():
    client = openai.OpenAI()
    for question in [
        "What crops do we have?",
        "what crops do we have ?",  # the real logged failure, exact phrasing
        "which crops are we growing",
    ]:
        result = resolve_tool_call(question, client)
        assert result.tool_name == "q_crop_types", question
