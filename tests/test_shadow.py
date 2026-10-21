"""Shadow mode (step 8): the new engine runs beside the old one and logs to its own table; the user's answer is untouched. All local: the test database
and the scripted FakeRouter, no model call, no live connection."""

import csv
import dataclasses
import datetime as dt

import pytest

from registry.migrations import migrate
from router.llm_fake import FakeRouter, spec as S
from shadow import compare, enabled, report, reports, runner, sample
from tests.conftest import TEST_DSN

FARM = "NIS-001"
TODAY = dt.date(2026, 10, 15)


@dataclasses.dataclass
class Old:
    text: str
    intent_source: str = "deterministic"
    failure_reason: str = None
    scoped_out_reason: str = None


@pytest.fixture
def db(farm_db):
    migrate(farm_db)
    for t in ("wrong_answer_reports", "shadow_log", "query_log"):
        farm_db.execute(f"DELETE FROM {t}")
    yield farm_db


def run(db, question, old, script, **kw):
    kw.setdefault("env", {})
    return runner.run_shadow(TEST_DSN, FARM, question, old, llm=FakeRouter(script=script), today=TODAY, conn=db, **kw)


def row(db, i):
    cols = ["classification", "needs_label", "new_kind", "new_code", "new_metric", "old_kind", "new_error", "new_text"]
    return dict(zip(cols, db.execute(f"SELECT {', '.join(cols)} FROM shadow_log WHERE id = %s", (i,)).fetchone()))


# ------------------------------------------------------------------------------------------------------------ comparing
def test_numbers_ignore_dates_years_batch_codes_and_commas():
    assert compare.numbers("PIG-B02 had 4 deaths of 26 on 15 Sep 2026, cost $1,234.50 in 2026. Data through 2026-09-15.") == {4.0, 26.0, 1234.5}
    assert compare.numbers("") == set() and compare.numbers(None) == set()


@pytest.mark.parametrize("old_kind,old_text,new_kind,new_text,want", [
    ("answer", "You have 12 pigs", "answer", "Total: 12 animals\n12 piggery", "agree"),
    ("answer", "You have 12 pigs", "answer", "13 pigs", "disagree"),
    ("answer", "12 pigs and 3 sows", "answer", "12 pigs", "agree"),                      # one set inside the other
    ("answer", "12 pigs and 3 sows", "answer", "12 pigs and 4 sows", "disagree"),
    ("answer", "Lots of pigs", "answer", "12 pigs", "unclear"),
    ("answer", "12 pigs", "clarify", "Which part of the farm?", "new_asks"),
    ("answer", "12 pigs", "refusal", "I don't show what individuals are paid", "new_refuses"),
    ("refuse", "I can't", "answer", "12 pigs", "old_misses"),
    ("clarify", "Which one?", "answer", "12 pigs", "old_misses"),
    ("refuse", "I can't", "refusal", "I can't", "both_decline"),
    ("answer", "12", "error", None, "new_error")])
def test_classification(old_kind, old_text, new_kind, new_text, want):
    assert compare.classify(old_kind, old_text, new_kind, new_text) == want


def test_what_needs_a_person():
    assert {c for c in compare.CLASSES if compare.needs_label(c)} == {"disagree", "new_asks", "new_refuses", "old_misses", "unclear", "new_error"}
    assert not compare.needs_label("agree") and not compare.needs_label("both_decline")


def test_the_old_engines_outcome_is_read_from_its_own_fields():
    assert compare.old_outcome(Old("x"))[0] == "answer"
    assert compare.old_outcome(Old("x", "tier0_help"))[0] == "answer"
    assert compare.old_outcome(Old("x", "needs_clarification"))[0] == "clarify"
    assert compare.old_outcome(Old("x", "unresolved")) == ("refuse", "unresolved")
    assert compare.old_outcome(Old("x", "deterministic", scoped_out_reason="not_tracked")) == ("refuse", "not_tracked")


# ----------------------------------------------------------------------------------------------------------- running
Q = "How many pigs do we have?"
HEAD = {Q: S("active_headcount", domains=["piggery"])}


def test_agreement_is_logged_without_needing_a_label(db):
    i = run(db, Q, Old("We have 12 pigs."), HEAD)
    r = row(db, i)
    assert (r["classification"], r["needs_label"], r["new_kind"], r["new_metric"], r["old_kind"]) == ("agree", False, "answer", "active_headcount", "answer")
    assert "12" in r["new_text"]


def test_a_disagreement_is_logged_and_waits_for_a_label(db):
    i = run(db, Q, Old("We have 13 pigs."), HEAD)
    assert (row(db, i)["classification"], row(db, i)["needs_label"]) == ("disagree", True)


def test_a_question_the_old_engine_missed_and_the_new_one_answers(db):
    i = run(db, Q, Old("I don't understand.", "unresolved"), HEAD)
    assert row(db, i)["classification"] == "old_misses"


def test_the_new_engine_asking_where_the_old_one_answered(db):
    q = "feed cost for pigs"
    i = run(db, q, Old("Feed cost is $123.45"), {q: S("feed_consumed_cost", domains=["poultry"])})
    r = row(db, i)
    assert (r["classification"], r["new_kind"], r["new_code"]) == ("new_asks", "clarify", "disagree_domain")


def test_the_new_engine_crashing_is_logged_not_raised(db):
    class Broken:
        def route(self, *a, **k):
            raise RuntimeError("boom")
    i = runner.run_shadow(TEST_DSN, FARM, Q, Old("12 pigs"), llm=Broken(), today=TODAY, conn=db, env={})
    r = row(db, i)
    assert (r["classification"], r["new_kind"], r["needs_label"]) == ("new_error", "error", True) and "boom" in r["new_error"]


def test_shadow_writes_only_to_its_own_table(db):
    counts = lambda: [db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("query_log", "expenses", "revenue", "pig_daily_log", "farm_profile")]
    before = counts()
    run(db, Q, Old("We have 12 pigs."), HEAD)
    assert counts() == before


def test_the_dashboard_date_range_reaches_the_new_engine(db):
    q = "What are our total expenses?"
    i = run(db, q, Old("Total $3,000"), {q: S("expenses")}, date_from=dt.date(2026, 3, 1), date_to=dt.date(2026, 3, 31))
    assert "1–31 Mar 2026 (dashboard date filter)" in row(db, i)["new_text"].splitlines()[0]
    assert db.execute("SELECT filter_from, filter_to FROM shadow_log WHERE id = %s", (i,)).fetchone() == (dt.date(2026, 3, 1), dt.date(2026, 3, 31))


# ---------------------------------------------------------------------------------------------------------------- bounds
def test_sampling_and_the_daily_ceiling_bound_the_runs(db):
    assert run(db, Q, Old("12"), HEAD, env={"SHADOW_SAMPLE": "0"}) is None
    assert db.execute("SELECT COUNT(*) FROM shadow_log").fetchone()[0] == 0
    env = {"SHADOW_DAILY_LIMIT": "2"}
    assert run(db, Q, Old("12"), HEAD, env=env) and run(db, Q, Old("12"), HEAD, env=env)
    assert run(db, Q, Old("12"), HEAD, env=env) is None
    assert db.execute("SELECT COUNT(*) FROM shadow_log").fetchone()[0] == 2


def test_a_missing_table_skips_quietly(db):
    db.execute("DROP TABLE wrong_answer_reports")
    db.execute("DROP TABLE shadow_log")
    assert run(db, Q, Old("12"), HEAD) is None
    from registry.migrations import MIGRATIONS
    db.execute("DELETE FROM schema_migrations WHERE id = '006_shadow_mode'")
    migrate(db)


def test_it_is_off_unless_switched_on(monkeypatch):
    monkeypatch.delenv("SHADOW_MODE", raising=False)
    assert not enabled() and runner.submit(TEST_DSN, FARM, Q, Old("12")) is None
    assert enabled({"SHADOW_MODE": "1"}) and not enabled({"SHADOW_MODE": "0"})


def test_submit_returns_at_once_and_the_row_appears(db, monkeypatch):
    monkeypatch.setenv("SHADOW_MODE", "1")
    monkeypatch.setattr(runner, "_make_llm", lambda env=None: FakeRouter(script=HEAD))
    fut = runner.submit(TEST_DSN, FARM, Q, Old("We have 12 pigs."), today=TODAY)
    assert fut is not None
    runner.wait()
    assert db.execute("SELECT classification FROM shadow_log").fetchone()[0] == "agree"


# ----------------------------------------------------------------------------------------------------------------- the app
def test_the_user_always_gets_the_old_answer_whatever_shadow_mode_does(monkeypatch):
    from ui import app
    seen = []
    monkeypatch.setenv("FARM_INTELLIGENCE_DB_DSN", TEST_DSN)
    monkeypatch.setattr(app, "answer_question", lambda *a, **k: Old("OLD ANSWER 12"))
    monkeypatch.setattr(runner, "submit", lambda *a, **k: seen.append((a, k)))
    monkeypatch.delenv("SHADOW_MODE", raising=False)
    assert app.handle_message(Q) == "OLD ANSWER 12" and seen == []                               # off: nothing scheduled
    monkeypatch.setenv("SHADOW_MODE", "1")
    assert app.handle_message(Q, "2026-03-01", "2026-03-31") == "OLD ANSWER 12"
    (args, kwargs), = seen
    assert args[2] == Q and args[3].text == "OLD ANSWER 12" and kwargs["date_from"] == dt.date(2026, 3, 1)
    monkeypatch.setattr(runner, "submit", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("pool gone")))
    assert app.handle_message(Q) == "OLD ANSWER 12"                                              # a shadow failure changes nothing


def test_the_report_button_is_hidden_unless_shadow_mode_or_the_pilot_switch_is_on(monkeypatch):
    from ui import app
    for env, want in ((None, False), ("SHADOW_MODE", True), ("REPORT_BUTTON", True)):
        monkeypatch.delenv("SHADOW_MODE", raising=False)
        monkeypatch.delenv("REPORT_BUTTON", raising=False)
        if env:
            monkeypatch.setenv(env, "1")
        demo = app.build_interface()
        assert [c.visible for c in demo.blocks.values() if getattr(c, "value", None) == "🚩 Report wrong answer"] == [want]


# ----------------------------------------------------------------------------------------------------------- labelling
def test_labels_and_the_disagreement_report(db, tmp_path):
    a = run(db, Q, Old("We have 13 pigs."), HEAD)
    b = run(db, Q, Old("We have 12 pigs."), HEAD)
    c = run(db, Q, Old("I don't understand.", "unresolved"), HEAD)
    s = report.summary(db, FARM)
    assert s["total"] == 3 and s["to_label"] == 2 and s["by_class"]["agree"] == 1 and s["by_class"]["disagree"] == 1
    assert "[%d] disagree" % a in report.text_report(db, FARM)
    assert report.export_label_sheet(db, FARM, tmp_path / "labels.csv") == 2
    assert list(csv.reader(open(tmp_path / "labels.csv", encoding="utf-8")))[0][0] == "shadow_id"
    report.label_row(db, a, "old_right", "Sylvester Vhashe", "the old count is right: a batch was sold")
    report.label_row(db, c, "new_right", "Sylvester Vhashe")
    s = report.summary(db, FARM)
    assert s["to_label"] == 0 and s["new_wrong"] == 1 and s["labelled"]["new_right"] == 1 and s["per_metric"]["active_headcount"]["new_wrong"] == 1
    for bad in (("nonsense", "x"), ("old_right", " ")):
        with pytest.raises(ValueError):
            report.label_row(db, b, *bad)
    with pytest.raises(ValueError):
        report.label_row(db, 999999, "old_right", "x")


# ---------------------------------------------------------------------------------------------------- report wrong answer
HIST = [{"role": "user", "content": "How many pigs do we have?"}, {"role": "assistant", "content": "We have 14 pigs."},
        {"role": "user", "content": "And chickens?"}, {"role": "assistant", "content": "500"}]


def test_the_latest_exchange_is_what_gets_reported():
    assert reports.last_exchange(HIST) == ("And chickens?", "500")
    assert reports.last_exchange([]) == (None, None) and reports.last_exchange([{"role": "user", "content": "hi"}]) == (None, None)


def test_a_wrong_answer_report_is_saved_and_linked_to_the_shadow_row(db, tmp_path):
    sid = run(db, "And chickens?", Old("500"), {"And chickens?": S("active_headcount", domains=["poultry"])})
    msg = reports.report_from_chat(TEST_DSN, FARM, HIST, "there are 509", conn=db)
    assert msg.startswith("Thanks. That answer has been flagged")
    assert db.execute("SELECT engine, question, answer_shown, note, shadow_id, status FROM wrong_answer_reports").fetchone() == ("old", "And chickens?", "500", "there are 509", sid, "new")
    assert reports.export_for_review(db, FARM, tmp_path / "r.csv") == 1
    assert "what_should_it_say" in open(tmp_path / "r.csv", encoding="utf-8").read()


def test_reporting_with_nothing_to_report_or_a_broken_database_is_polite_not_an_error(db):
    assert reports.report_from_chat(TEST_DSN, FARM, [], conn=db) == "Ask a question first, then report its answer."
    db.execute("DROP TABLE wrong_answer_reports")
    assert "could not be saved" in reports.report_from_chat(TEST_DSN, FARM, HIST, conn=db)
    db.execute("DELETE FROM schema_migrations WHERE id = '006_shadow_mode'")
    db.execute("DROP TABLE shadow_log")
    migrate(db)
    with pytest.raises(ValueError):
        reports.record_report(db, FARM, "", "answer")
    with pytest.raises(ValueError):
        reports.record_report(db, FARM, "q", "a", engine="both")


# ---------------------------------------------------------------------------------------------------- query_log sampling
def _log(db, q, src="deterministic", fail=None, scoped=None, n=1):
    for _ in range(n):
        db.execute("INSERT INTO query_log (farm_code, question_text, intent_source, failure_reason, scoped_out_reason) VALUES (%s,%s,%s,%s,%s)",
                   (FARM, q, src, fail, scoped))


def test_the_sample_drops_written_questions_and_puts_old_engine_misses_first(db, tmp_path):
    _log(db, "How many pigs do we have?")                                       # a written dev question
    _log(db, "how many PIGS do we have")                                        # the same, differently typed
    _log(db, "what is the weather on mars", "unresolved", fail="no match", n=3)
    _log(db, "pigs total today please")
    _log(db, "any chickens left?")
    _log(db, "tell me about the tractor", "deterministic", scoped="not_tracked")
    items = sample.sample_query_log(db, FARM, n=10, seed=1)
    qs = [i["question"] for i in items]
    assert "How many pigs do we have?" not in qs and "how many PIGS do we have" not in qs
    assert set(qs[:2]) == {"what is the weather on mars", "tell me about the tractor"}        # the misses first
    assert [i["times_asked"] for i in items if i["question"] == "what is the weather on mars"] == [3]
    assert qs == [i["question"] for i in sample.sample_query_log(db, FARM, n=10, seed=1)]       # seeded: the same sample every time
    assert len(sample.sample_query_log(db, FARM, n=3)) == 3
    assert sample.export_sample(items, tmp_path / "s.csv") == len(items)
    assert "add_to_dev_set" in open(tmp_path / "s.csv", encoding="utf-8").read()
