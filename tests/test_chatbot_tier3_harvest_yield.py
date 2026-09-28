import openai

from chatbot.engine import answer_question
from chatbot.tools import resolve_tool_call
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _harvest_fixture():
    return base_fixture(extra_sheets={
        "F1_PLOTS": {
            "header": ["plot_code", "plot_name", "hectares", "soil_type",
                       "irrigation_type", "gps"],
            "sample": ["PLOT-9", "Sample plot", 2.0, "Loam", "Rainfed", None],
            "rows": [
                ["PLOT-1", "North field", 2.0, "Loam", "Rainfed", None],
                ["PLOT-2", "South field", 1.0, "Sandy", "Rainfed", None],
            ],
        },
        "F2_PLANTINGS": {
            "header": ["planting_code", "plot_code", "crop", "variety", "season",
                       "planting_date", "area_ha", "seed_kg", "seed_cost",
                       "expected_harvest_date", "expected_yield_tons_ha", "status"],
            "sample": ["PLANT-99", "PLOT-9", "Maize", "SC627", "2025/26",
                       "2025-11-01", 2.0, 20, 40.0, "2026-04-01", 5.0, "Harvested"],
            "rows": [
                ["PLANT-1", "PLOT-1", "Maize", "SC627", "2025/26",
                 "2025-11-01", 2.0, 20, 40.0, "2026-04-01", 5.0, "Harvested"],
                ["PLANT-2", "PLOT-2", "Maize", "SC627", "2025/26",
                 "2025-11-01", 1.0, 10, 20.0, "2026-04-01", 5.0, "Harvested"],
            ],
        },
        "F5_HARVEST_LOG": {
            "header": ["date", "planting_code", "bags", "quantity_kg",
                       "moisture_pct", "grade", "field_loss_kg",
                       "storage_location", "labour_hours"],
            "sample": ["2026-09-07", "PLANT-99", 40, 2000, 12.5, "A",
                       20, "Shed 1", 8],
            "rows": [
                # PLOT-1: 8000kg / 2.0ha = 4000 kg/ha (better)
                ["2026-04-05", "PLANT-1", 160, 8000, 12.5, "A", 50, "Shed 1", 20],
                # PLOT-2: 1000kg / 1.0ha = 1000 kg/ha (worse)
                ["2026-04-05", "PLANT-2", 20, 1000, 12.5, "B", 10, "Shed 1", 10],
            ],
        },
    })


def _seed(tmp_path, dsn, fixture=None):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, fixture or _harvest_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=dsn)


def test_harvest_yield_resolves_via_tier3_with_real_per_hectare_figures(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question(
        "Which plot had the best yield per hectare?", farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.tool_name == "q_harvest_yield"
    assert "PLOT-1" in answer.text
    assert "4000" in answer.text or "4,000" in answer.text


def test_harvest_yield_scoped_out_when_crops_module_inactive(tmp_path, db_conn, test_dsn):
    fixture = _harvest_fixture()
    fixture["00_FARM_PROFILE"]["rows"][0][7] = "No"  # module_crops_active
    _seed(tmp_path, test_dsn, fixture)

    answer = answer_question(
        "Which plot had the best yield per hectare?", farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.scoped_out_reason == "crops"


def test_resolve_tool_call_picks_harvest_yield_for_canonical_phrasings():
    client = openai.OpenAI()
    for question in [
        "Which plot yields best per hectare?",
        "how efficient was our maize harvest",
        "yield per hectare by plot",
    ]:
        result = resolve_tool_call(question, client)
        assert result.tool_name == "q_harvest_yield", question
