from chatbot.engine import answer_question
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _feed_cost_fixture():
    return base_fixture(extra_sheets={
        "P1_PIG_BATCHES": {
            "header": ["batch_code", "pen", "breed", "start_date", "start_count",
                       "start_avg_kg", "source", "target_market_date", "status"],
            "sample": ["PIG-B99", "Pen 9", "Large White", "2026-01-01", 20, 8.0,
                       "Own farrowing", "2026-05-01", "Active"],
            "rows": [["PIG-B01", "Pen 1", "Large White", "2025-12-01", 24, 8.5,
                      "Own farrowing", "2026-05-20", "Active"]],
        },
        "P2_PIG_DAILY_LOG": {
            "header": ["date", "batch_code", "pen", "feed_type", "feed_kg",
                       "water_litres", "deaths", "culls", "closing_count",
                       "pen_temp_c", "pen_condition", "notes", "recorded_by"],
            "sample": ["2026-09-07", "PIG-B99", "Pen 9", "Pig grower", 42, 110, 0,
                       0, 20, 24, "Dry", None, "S01"],
            "rows": [
                ["2026-01-06", "PIG-B01", "Pen 1", "Pig grower", 50, 100, 0, 0, 24,
                 24, "Dry", None, "S01"],
            ],
        },
        "C1_POULTRY_BATCHES": {
            "header": ["batch_code", "bird_type", "breed", "house",
                       "placement_date", "chicks_placed", "chick_unit_cost",
                       "hatchery", "target_off_date", "status"],
            "sample": ["BRO-99", "Broiler", "Ross 308", "House 9", "2026-08-10",
                       500, 0.55, "Irvine's Zimbabwe", "2026-09-21", "Growing"],
            "rows": [["BRO-01", "Broiler", "Ross 308", "House 1", "2025-12-17",
                      500, 0.55, "Irvine's Zimbabwe", "2026-01-28", "Growing"]],
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
                ["2026-01-06", "BRO-01", 20, 0, 0, 500, "Broiler grower", 30, 45,
                 29, "Dry", None, 0, 0, 0, None, "S02"],
            ],
        },
        "06_FEED_INVENTORY": {
            "header": ["date", "domain", "feed_type", "opening_kg", "received_kg",
                       "used_kg", "waste_kg", "closing_kg", "unit_cost_per_kg",
                       "supplier", "batch_ref"],
            "sample": ["2026-09-07", "piggery", "Pig grower", 1200, 500, 430, 5,
                       1265, 0.68, "Profeeds Marondera", None],
            "rows": [
                ["2026-01-05", "piggery", "Pig grower", 400, 250, 50, 0.5,
                 599.5, 1.00, "Profeeds Marondera", None],
                ["2026-01-05", "poultry", "Broiler grower", 300, 200, 30, 0.5,
                 469.5, 1.50, "Profeeds Marondera", None],
            ],
        },
    })


def _seed(tmp_path, dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _feed_cost_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=dsn)


def test_answer_question_answers_feed_cost_split(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question(
        "how does feed cost split between pigs and chickens in January 2026",
        farm_code="NIS-001",
        dsn=test_dsn,
    )

    assert "50.00" in answer.text or "50.0" in answer.text  # piggery: 50kg * $1.00/kg
    assert "45.00" in answer.text or "45.0" in answer.text  # poultry: 30kg * $1.50/kg
    assert answer.intent_source == "deterministic"
    assert answer.query_id == "feed_cost_split"


def test_answer_question_returns_unresolved_for_unrelated_question(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question(
        "what's the capital of France",
        farm_code="NIS-001",
        dsn=test_dsn,
    )

    assert answer.intent_source == "unresolved"
    assert answer.failure_reason == "no_match"
    assert answer.query_id is None
    assert answer.text == "I can't answer that yet - I don't have a way to look that up."


def test_answer_question_returns_missing_parameter_when_no_month_given(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question(
        "how does feed cost split between pigs and chickens",
        farm_code="NIS-001",
        dsn=test_dsn,
    )

    assert answer.intent_source == "unresolved"
    assert answer.failure_reason == "missing_parameter"
    assert answer.query_id is None


def test_answer_question_logs_query_log_row_for_success(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer_question(
        "how does feed cost split between pigs and chickens in January 2026",
        farm_code="NIS-001",
        dsn=test_dsn,
    )

    row = db_conn.execute(
        "SELECT farm_code, question_text, intent_source, query_id, "
        "failure_reason, scoped_out_reason FROM query_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row == (
        "NIS-001",
        "how does feed cost split between pigs and chickens in January 2026",
        "deterministic", "feed_cost_split", None, None,
    )


def test_query_log_write_failure_never_breaks_the_answer(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)
    # prime query_log (created lazily by answer_question) before sabotaging it
    answer_question(
        "how does feed cost split between pigs and chickens in January 2026",
        farm_code="NIS-001",
        dsn=test_dsn,
    )
    db_conn.execute("ALTER TABLE query_log DROP COLUMN farm_code")

    answer = answer_question(
        "how does feed cost split between pigs and chickens in January 2026",
        farm_code="NIS-001",
        dsn=test_dsn,
    )

    assert "50.00" in answer.text or "50.0" in answer.text
    assert answer.intent_source == "deterministic"
