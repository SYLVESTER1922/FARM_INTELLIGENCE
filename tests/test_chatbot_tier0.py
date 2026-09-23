from chatbot.engine import answer_question
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _seed(tmp_path, dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=dsn)


def test_bare_greeting_gets_canned_response_not_unresolved(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question("hi", farm_code="NIS-001", dsn=test_dsn)

    assert answer.intent_source == "tier0_greeting"
    assert answer.text != "I can't answer that yet - I don't have a way to look that up."
    assert answer.query_id is None
    assert answer.failure_reason is None


def test_greeting_variants_all_match(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    for greeting in ["Hi", "HI", "Hie", "hey", "Hello there", "good morning"]:
        answer = answer_question(greeting, farm_code="NIS-001", dsn=test_dsn)
        assert answer.intent_source == "tier0_greeting", greeting


def test_capability_question_gets_help_response(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    for question in ["What can you ask?", "what questions can i ask?", "help"]:
        answer = answer_question(question, farm_code="NIS-001", dsn=test_dsn)
        assert answer.intent_source == "tier0_help", question
        assert answer.query_id is None


def test_real_question_containing_a_greeting_word_is_not_hijacked(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    # No month given (missing_parameter) so tier-1 never needs to run real SQL -
    # this test only cares that tier-0 correctly yields to tier-1's real
    # matching instead of hijacking the question as a bare greeting.
    answer = answer_question(
        "hi, how does feed cost split between pigs and chickens",
        farm_code="NIS-001",
        dsn=test_dsn,
    )

    assert answer.intent_source != "tier0_greeting"
    assert answer.intent_source != "tier0_help"
    assert answer.failure_reason == "missing_parameter"


def test_tier0_greeting_logged_to_query_log(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer_question("hi", farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT intent_source, query_id, failure_reason FROM query_log "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row == ("tier0_greeting", None, None)
