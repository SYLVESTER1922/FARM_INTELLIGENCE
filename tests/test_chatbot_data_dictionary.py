from chatbot.engine import answer_question
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _seed(tmp_path, dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=dsn)


def test_accounts_payable_question_gets_honest_specific_refusal(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question(
        "What accounts payable does the farm have?", farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.intent_source == "unresolved"
    assert answer.query_id is None
    assert answer.text != "I can't answer that yet - I don't have a way to look that up."
    assert "accounts payable" in answer.text.lower() or "owes" in answer.text.lower()


def test_original_indirect_owing_phrasing_now_reliably_gets_specific_refusal(
    tmp_path, db_conn, test_dsn
):
    # "Do we owe anyone money?" - the real, original logged failure this
    # ticket first targeted. Originally documented here as genuinely
    # borderline/flaky: it shares enough vocabulary with crop_debtor's own
    # catalog phrase ("who owes US money for crops") that tier-2's LLM
    # classifier occasionally misrouted it there (fixed separately in
    # 6d3e063 - 2 example phrases per catalog entry instead of 1, plus
    # phrase reordering), and even when it correctly fell through,
    # explain_gap didn't always catch the indirect phrasing specifically
    # (fixed here - see data_dictionary.py's explain_gap docstring for
    # what actually fixed it, and why a first attempt didn't). Both fixes
    # together made this reliable - verified across 9 repeated real calls
    # (3 phrasings x 3 trials) before trusting a non-flaky assertion here.
    _seed(tmp_path, test_dsn)

    for question in ["Do we owe anyone money?", "Do we owe anyone?", "Are we owing anyone?"]:
        answer = answer_question(question, farm_code="NIS-001", dsn=test_dsn)
        assert answer.query_id is None, question
        assert "accounts payable" in answer.text.lower(), (question, answer.text)


def test_genuinely_out_of_scope_question_still_refuses_cleanly(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question("who owns the company?", farm_code="NIS-001", dsn=test_dsn)

    assert answer.intent_source == "unresolved"
    # not a crash, not a fabricated answer - some honest refusal text either way
    assert answer.text
    assert answer.query_id is None


def test_data_dictionary_never_surfaces_raw_table_or_column_names(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question(
        "What accounts payable does the farm have?", farm_code="NIS-001", dsn=test_dsn,
    )

    # the curated dictionary describes concepts in farm-owner language,
    # never the underlying Postgres schema
    for leaked_name in ["pig_daily_log", "poultry_daily_log", "farm_profile",
                         "closing_count", "query_log"]:
        assert leaked_name not in answer.text
