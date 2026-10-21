"""Step 6: the capability catalog is generated from the registry, and the schema is checked against it (plan sections 4 and 8)."""

import datetime as dt
import pathlib
import re

import pytest

from catalog import BY_CODE, KNOWN, UNEXPOSED
from catalog.build import CATALOG_PATH, catalog_markdown, help_text, limits_text, metrics_by_group
from registry import REGISTRY
from render.templates import TITLES
from router import answer_question_v2, crosscheck, refusals
from router.llm_fake import FakeRouter, spec as S
from router.spec import REFUSALS

REPO = pathlib.Path(__file__).resolve().parent.parent


def test_every_table_is_exposed_by_a_metric_or_explicitly_marked_unexposed(farm_db):
    tables = {r[0] for r in farm_db.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'").fetchall()}
    exposed = {t for m in REGISTRY.values() for t in m.sources}
    assert exposed <= tables, exposed - tables                                  # no metric reads a table that does not exist
    missing = tables - exposed - set(UNEXPOSED)
    assert not missing, f"tables no metric reads and nobody has marked as unexposed: {sorted(missing)}"
    assert not (exposed & set(UNEXPOSED)), "a table is both exposed and marked unexposed"
    assert set(UNEXPOSED) <= tables, "an unexposed entry names a table that is not in the schema"


def test_unexposed_entries_have_a_class_and_a_reason():
    for table, (cls, why) in UNEXPOSED.items():
        assert cls in ("internal", "tracked_no_metric") and why.strip(), table


def test_every_tracked_but_unread_table_has_a_refusal_that_says_it_is_recorded():
    claimed = {t for u in KNOWN if u.kind == "tracked_no_metric" for t in u.tables}
    assert claimed == {t for t, (cls, _) in UNEXPOSED.items() if cls == "tracked_no_metric"}       # one refusal per unread table, and back
    for u in KNOWN:
        if u.kind == "tracked_no_metric":
            assert re.search(r"\b(recorded|logged)\b", u.text) and "can't answer" in u.text and u.tables, u.code
            assert not re.search(r"\b(isn't|aren't|not) (recorded|tracked|logged)\b", u.text), u.code     # never denies what IS recorded


def test_every_not_tracked_refusal_says_what_to_log_or_what_exists():
    for u in KNOWN:
        if u.kind == "not_tracked":
            assert len(u.text) > 30 and u.text.endswith("."), u.code
    for code in ("accounts_payable", "current_sickness", "payroll_history"):                  # fixable by logging something: say what
        assert "To answer this, log" in BY_CODE[code].text, code


def test_the_curated_list_is_the_routers_vocabulary():
    assert set(REFUSALS) == {"none", "out_of_scope", *BY_CODE}
    assert set(refusals.NAMED) == {*BY_CODE, "out_of_scope"}
    for u in KNOWN:
        assert refusals.text(u.code) == u.text and (refusals.kind(u.code) == "claim") == (u.kind == "not_tracked")
        assert u.cues is None or u.cues.pattern
    assert set(crosscheck.NEAR_METRIC) == {u.code for u in KNOWN if u.near_metric}
    assert all(m in REGISTRY for m in crosscheck.NEAR_METRIC.values())


def test_help_lists_every_metric_and_is_generated_not_written():
    text = help_text()
    for _, metrics in metrics_by_group():
        for m in metrics:
            assert TITLES[m.id].lower() in text, m.id
    assert {m.id for _, ms in metrics_by_group() for m in ms} == set(REGISTRY)           # every metric belongs to a listed group
    assert "pigs" in text and "last month" in text


def test_limits_text_names_both_classes():
    text = limits_text()
    assert text.startswith("Not recorded on this farm:") and "Recorded, but I can't answer questions about it yet:" in text


def test_the_committed_catalog_is_up_to_date():
    assert CATALOG_PATH.read_text() == catalog_markdown(), "run `python -m catalog.build`"
    md = CATALOG_PATH.read_text()
    for m in REGISTRY.values():
        assert f"`{m.id}`" in md and m.answers in md and m.does_not_answer in md
    for u in KNOWN:
        assert f"**{u.code}**" in md
    for table in UNEXPOSED:
        assert f"`{table}`" in md


def test_the_new_path_does_not_use_the_old_dictionary_or_explain_gap():
    for pkg in ("router", "catalog", "render", "resolver", "registry"):
        for path in (REPO / pkg).glob("*.py"):
            src = path.read_text()
            assert "data_dictionary" not in src and "explain_gap" not in src and "DATA_DICTIONARY" not in src, path
            assert "chatbot.grounding" not in src and "chatbot import grounding" not in src, path


@pytest.mark.parametrize("phrase", ["help", "What can I ask?", "what can you answer", "What do you track?"])
def test_help_questions_are_answered_from_the_catalog_without_the_llm(farm_db, phrase):
    llm = FakeRouter()
    a = answer_question_v2(phrase, farm_db, llm)
    assert (a.kind, a.code, a.text) == ("answer", "help", help_text()) and llm.calls == []


def test_what_cant_you_answer_is_answered_from_the_curated_list(farm_db):
    a = answer_question_v2("What can't you answer?", farm_db, FakeRouter())
    assert a.code == "help" and a.text == limits_text()


@pytest.mark.parametrize("code,question", [
    ("staff_info", "How many staff do we have?"), ("crop_scouting", "Which plots had pests last month?"),
    ("field_operations", "When was the maize irrigated?"), ("payroll_history", "Show me the payroll history"),
])
def test_recorded_but_unread_data_is_named_not_denied(farm_db, code, question):
    a, = [answer_question_v2(question, farm_db, FakeRouter(script={question: S("none", refusal=code)}))]
    assert (a.kind, a.code, a.claim) == ("refusal", code, code == "payroll_history")
    assert a.text == BY_CODE[code].text
    if BY_CODE[code].kind == "tracked_no_metric":
        assert re.search(r"\b(recorded|logged)\b", a.text) and "isn't recorded" not in a.text


def test_a_recorded_data_claim_without_the_users_words_is_a_question_to_the_nearest_metric(farm_db):
    q = "How are things looking in the fields?"
    a = answer_question_v2(q, farm_db, FakeRouter(script={q: S("none", refusal="crop_scouting")}))
    assert a.code == "claim_or_metric" and "Crops planted" in a.text and "I can't answer questions about them yet" in a.text


@pytest.mark.parametrize("question", [
    "What is the pay rate for each worker?", "How much does Tendai earn?", "What is Tendai's salary?", "Show me salary per employee",
    "What is the hourly rate of our staff?", "What are the wages for each labourer this month?"])
def test_per_person_pay_is_refused_by_policy_whatever_the_model_picked(farm_db, question):
    a = answer_question_v2(question, farm_db, FakeRouter(script={question: S("labour")}))
    assert (a.kind, a.code, a.claim) == ("refusal", "staff_pay", False) and a.text == BY_CODE["staff_pay"].text
    assert "total labour cost" in a.text and not re.search(r"\b(isn't|aren't|not) (recorded|tracked)\b", a.text)


@pytest.mark.parametrize("question", [
    "What was our total labour cost last month?", "How much did we spend on salaries in August 2026?",
    "How many hours of overtime were worked in August 2026?", "What did we pay in wages this year?"])
def test_total_labour_cost_is_still_answered(farm_db, question):
    a = answer_question_v2(question, farm_db, FakeRouter(script={question: S("labour")}), today=dt.date(2026, 10, 15))
    assert a.kind in ("answer", "clarify") and a.code != "staff_pay"


def test_the_staff_pay_refusal_is_listed_in_what_the_bot_cannot_do():
    assert "Not shown, by choice: what an individual person is paid" in limits_text()
    assert BY_CODE["staff_pay"].kind == "policy" and not BY_CODE["staff_pay"].claim
