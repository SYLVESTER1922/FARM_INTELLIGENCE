from chatbot.engine import answer_question
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _poultry_mortality_fixture():
    """Two poultry batches; BRO-P02 has a clear mortality outlier."""
    return base_fixture(extra_sheets={
        "C1_POULTRY_BATCHES": {
            "header": ["batch_code", "bird_type", "breed", "house",
                       "placement_date", "chicks_placed", "chick_unit_cost",
                       "hatchery", "target_off_date", "status"],
            "sample": ["BRO-99", "Broiler", "Ross 308", "House 9", "2026-08-10",
                       500, 0.55, "Irvine's Zimbabwe", "2026-09-21", "Growing"],
            "rows": [
                ["BRO-P01", "Broiler", "Ross 308", "House 1", "2025-12-01", 500,
                 0.55, "Irvine's Zimbabwe", "2026-01-12", "Growing"],
                ["BRO-P02", "Broiler", "Ross 308", "House 2", "2025-12-20", 520,
                 0.55, "Irvine's Zimbabwe", "2026-01-31", "Growing"],
            ],
        },
        "C2_POULTRY_DAILY_LOG": {
            "header": ["date", "batch_code", "age_days", "deaths", "culls",
                       "closing_birds", "feed_type", "feed_kg", "water_litres",
                       "house_temp_c", "litter_condition", "lighting_hours",
                       "eggs_collected", "eggs_cracked", "eggs_dirty", "notes",
                       "recorded_by"],
            "sample": ["2026-09-01", "BRO-99", 22, 2, 0, 498, "Broiler grower",
                       58, 95, 29, "Dry", None, 0, 0, 0, None, "S02"],
            "rows": [
                # BRO-P01: near-zero mortality
                ["2025-12-02", "BRO-P01", 1, 1, 0, 499, "Chick mash", 10, 15, 33,
                 "Dry", 23, 0, 0, 0, None, "S02"],
                # BRO-P02: heavy mortality
                ["2025-12-21", "BRO-P02", 1, 42, 0, 478, "Chick mash", 10, 15,
                 33, "Dry", 23, 0, 0, 0, "Heat stress", "S02"],
            ],
        },
    })


def test_answer_question_answers_poultry_mortality_spike(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _poultry_mortality_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    answer = answer_question(
        "which poultry batch has the worst mortality",
        farm_code="NIS-001",
        dsn=test_dsn,
    )

    assert "BRO-P02" in answer.text
    assert answer.intent_source == "deterministic"
    assert answer.query_id == "poultry_mortality_spike"


def _piggery_disease_fixture():
    """One pig batch (PIG-B02) has a treated health event; another doesn't."""
    return base_fixture(extra_sheets={
        "P1_PIG_BATCHES": {
            "header": ["batch_code", "pen", "breed", "start_date", "start_count",
                       "start_avg_kg", "source", "target_market_date", "status"],
            "sample": ["PIG-B99", "Pen 9", "Large White", "2026-01-01", 20, 8.0,
                       "Own farrowing", "2026-05-01", "Active"],
            "rows": [
                ["PIG-B01", "Pen 1", "Large White", "2025-12-01", 24, 8.5,
                 "Own farrowing", "2026-05-20", "Active"],
                ["PIG-B02", "Pen 2", "Landrace", "2025-12-01", 20, 8.5,
                 "Own farrowing", "2026-05-20", "Active"],
            ],
        },
        "07_HEALTH_LOG": {
            "header": ["date", "domain", "batch_ref", "animal_tag", "event_type",
                       "symptom", "diagnosis", "product", "dose",
                       "animals_treated", "cost", "withdrawal_until", "outcome",
                       "administered_by"],
            "sample": ["2026-08-20", "poultry", "BRO-99", None, "Vaccination",
                       "None", None, "Newcastle LaSota", "1 drop/bird", 500, 18,
                       None, "Ongoing", "S02"],
            "rows": [
                ["2026-04-25", "piggery", "PIG-B02", None, "Inspection",
                 "Diarrhoea", "Suspected bacterial enteritis", None, None, 20,
                 15, None, "Ongoing", "S01"],
                ["2026-04-27", "piggery", "PIG-B02", None, "Treatment",
                 "Diarrhoea", "Bacterial enteritis", "Oxytetracycline LA",
                 "1ml/10kg", 8, 38, "2026-05-18", "Recovered", "S01"],
            ],
        },
    })


def test_answer_question_answers_piggery_disease_outbreak(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _piggery_disease_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    answer = answer_question(
        "is there a disease outbreak in the piggery",
        farm_code="NIS-001",
        dsn=test_dsn,
    )

    assert "PIG-B02" in answer.text
    assert answer.intent_source == "deterministic"
    assert answer.query_id == "piggery_disease_outbreak"


def _crop_debtor_fixture():
    """One crop sale is unpaid; another (same buyer) is paid, to rule out
    the query just matching on buyer name."""
    return base_fixture(extra_sheets={
        "F1_PLOTS": {
            "header": ["plot_code", "plot_name", "hectares", "soil_type",
                       "irrigation_type", "gps"],
            "sample": ["P9", "Sample field", 6, "Clay loam", "Sprinkler", None],
            "rows": [["P2", "Back field", 4, "Sandy loam", "Rainfed", None]],
        },
        "F2_PLANTINGS": {
            "header": ["planting_code", "plot_code", "crop", "variety", "season",
                       "planting_date", "area_ha", "seed_kg", "seed_cost",
                       "expected_harvest_date", "expected_yield_tons_ha",
                       "status"],
            "sample": ["MZ-P9-2025A", "P9", "Maize", "SC637", "2025 Summer",
                       "2025-11-15", 6, 150, 210, "2026-04-15", 5.5, "Growing"],
            "rows": [["SB-PL2-25A", "P2", "Groundnuts", "Nyanga", "2025 Summer",
                      "2025-11-20", 4, 80, 120, "2026-03-15", 1.8, "Harvested"]],
        },
        "03_REVENUE": {
            "header": ["date", "domain", "product", "quantity", "unit",
                       "unit_price", "total_amount", "head_count",
                       "avg_weight_kg", "grade", "buyer", "channel",
                       "payment_status", "batch_ref"],
            "sample": ["2026-09-03", "poultry", "Dressed chicken", 48, "head",
                       6.2, 297.6, 48, 2.1, None, "Local market vendor",
                       "Market", "Paid", "BRO-24"],
            "rows": [
                ["2026-03-28", "crops", "Soya", 1000, "bag", 12, 12000, None,
                 None, "A", "Chikafu Grain Traders", "Market", "Owing",
                 "SB-PL2-25A"],
                ["2026-04-05", "crops", "Maize grain", 500, "bag", 10, 5000,
                 None, None, "A", "Chikafu Grain Traders", "Market", "Paid",
                 "SB-PL2-25A"],
            ],
        },
    })


def test_answer_question_answers_crop_debtor(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _crop_debtor_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    answer = answer_question(
        "which crop sales are unpaid",
        farm_code="NIS-001",
        dsn=test_dsn,
    )

    assert "Chikafu Grain Traders" in answer.text
    assert answer.intent_source == "deterministic"
    assert answer.query_id == "crop_debtor"


def test_answer_question_returns_ambiguous_for_overlapping_question(tmp_path, db_conn, test_dsn):
    # Deliberately vague - a real farm owner could mean either poultry
    # mortality or a piggery disease when asking this. No fixture data
    # needed: ambiguity is resolved before any SQL runs.
    build_workbook(tmp_path / "fixture.xlsx", base_fixture())
    sync_workbook_to_supabase(str(tmp_path / "fixture.xlsx"), farm_code="NIS-001", dsn=test_dsn)

    answer = answer_question(
        "is something wrong with a batch",
        farm_code="NIS-001",
        dsn=test_dsn,
    )

    assert answer.intent_source == "unresolved"
    assert answer.failure_reason == "ambiguous"
    assert answer.query_id is None
