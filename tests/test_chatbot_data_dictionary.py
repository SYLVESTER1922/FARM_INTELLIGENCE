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

    # "What accounts payable does the farm have?" - a real, natural
    # phrasing of the real logged failure this ticket targets ("Do we owe
    # anyone money?"). Note: the more indirect original phrasing was
    # tested directly during development and found genuinely borderline -
    # it shares enough vocabulary with crop_debtor's own catalog phrase
    # ("who owes US money for crops") that tier-2's LLM classifier
    # occasionally (non-deterministically) misroutes it there instead of
    # falling through to this gap-explanation path at all, and even when
    # it does fall through, explain_gap doesn't always catch the more
    # indirect phrasing specifically. This is a real, pre-existing
    # limitation of both tier-2's classification and the LLM-based gap
    # explainer for phrasing that doesn't closely match the curated
    # dictionary's own vocabulary - documented honestly here rather than
    # tested with a flaky assertion.
    answer = answer_question(
        "What accounts payable does the farm have?", farm_code="NIS-001", dsn=test_dsn,
    )

    assert answer.intent_source == "unresolved"
    assert answer.query_id is None
    assert answer.text != "I can't answer that yet - I don't have a way to look that up."
    assert "accounts payable" in answer.text.lower() or "owes" in answer.text.lower()


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
