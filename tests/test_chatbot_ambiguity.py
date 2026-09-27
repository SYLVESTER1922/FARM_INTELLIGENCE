from chatbot.ambiguity import has_no_real_subject
from chatbot.engine import answer_question
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def test_has_no_real_subject_true_for_bare_questions():
    for q in ["How's it doing?", "how's it doing", "How many?", "how many"]:
        assert has_no_real_subject(q) is True, q


def test_has_no_real_subject_false_for_questions_with_a_real_word():
    # domain-ambiguous, out-of-scope, and normal real questions all have
    # a real content word and must NOT be caught by this check - they
    # continue to tier-3's normal tool-calling (or its normal decline),
    # unaffected.
    for q in [
        "is something wrong with a batch",
        "who owns the company?",
        "What's the expense amount to date?",
        "what about last year?",
        "how many pigs do we have?",
        "what's the weather like today?",
    ]:
        assert has_no_real_subject(q) is False, q


def _seed(tmp_path, dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=dsn)


def test_bare_question_gets_clarification_not_a_guessed_answer(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    for q in ["How's it doing?", "How many?"]:
        answer = answer_question(q, farm_code="NIS-001", dsn=test_dsn)
        assert answer.intent_source == "needs_clarification", q
        assert answer.tool_name is None
        assert "clarify" in answer.text.lower()


def test_domain_ambiguous_question_still_reaches_normal_handling(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    # "is something wrong with a batch" is ambiguous between piggery and
    # poultry (a real, nameable subject) - this is NOT what the
    # clarification check is for; it must still resolve via tier-1's own
    # existing ambiguity handling, unaffected by this fix.
    answer = answer_question("is something wrong with a batch", farm_code="NIS-001", dsn=test_dsn)

    assert answer.intent_source == "unresolved"
    assert answer.failure_reason == "ambiguous"


def test_out_of_scope_question_still_reaches_normal_handling(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    answer = answer_question("who owns the company?", farm_code="NIS-001", dsn=test_dsn)

    assert answer.intent_source == "unresolved"
    assert answer.intent_source != "needs_clarification"
