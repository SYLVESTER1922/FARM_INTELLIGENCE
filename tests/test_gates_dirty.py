"""The gated sync end to end against the local test database: every dirty fixture, the last-good snapshot, the banner, the caveats, the email and the
acknowledgement log. Each test starts from a clean, verified baseline."""

import datetime as dt

import pytest

from gates import status, store
from gates.fixtures import DIRTY, dirty
from gates.run import gated_sync_workbook, gated_sync_workbook_object
from registry.migrations import migrate
from router import answer_question_v2
from router.llm_fake import FakeRouter, spec as S
from tests.conftest import TEST_DSN
from gates.fixtures import WORKBOOK

import psycopg

FARM = "NIS-001"
TODAY = dt.date(2026, 10, 15)
T0 = dt.datetime(2026, 10, 1, 8, 0, tzinfo=dt.timezone.utc)


@pytest.fixture
def gate_db():
    conn = psycopg.connect(TEST_DSN, autocommit=True)
    conn.execute("DROP SCHEMA public CASCADE")
    conn.execute("CREATE SCHEMA public")
    migrate(conn)
    base = gated_sync_workbook(str(WORKBOOK), FARM, TEST_DSN, now=T0, notifier=lambda s, b: None)
    assert base.outcome == "passed" and base.warnings == [] and base.blocks == [], base.detail
    yield conn
    conn.close()


def _live(conn):
    return conn.execute("SELECT COUNT(*), COALESCE(SUM(total_cost), 0) FROM expenses").fetchone()


def _run(name, **kw):
    kw.setdefault("notifier", lambda s, b: None)
    return gated_sync_workbook_object(dirty(name), FARM, TEST_DSN, **kw)


def test_the_clean_workbook_fires_no_block_and_no_warning(gate_db):
    r = gated_sync_workbook(str(WORKBOOK), FARM, TEST_DSN, notifier=lambda s, b: None)
    assert r.outcome == "passed" and not [f for f in r.firings if f.severity != "report"]          # the gate false-positive count on clean data is 0


@pytest.mark.parametrize("name", [n for n, d in DIRTY.items() if d.severity == "block"])
def test_a_block_keeps_the_last_good_data_and_says_why(gate_db, name):
    before = _live(gate_db)
    sent = []
    r = _run(name, notifier=lambda s, b: sent.append((s, b)))
    assert r.outcome == "blocked" and DIRTY[name].gate in {f.gate for f in r.blocks}
    assert _live(gate_db) == before                                                              # nothing from the bad upload is live
    assert gate_db.execute("SELECT to_regclass('staging')").fetchone()[0] is None                # the staging copy is gone
    assert len(sent) == 1 and "blocked" in sent[0][0] and r.notified
    run = gate_db.execute("SELECT outcome, notified FROM sync_runs WHERE id = %s", (r.run_id,)).fetchone()
    assert run == ("blocked", True)
    logged = gate_db.execute("SELECT gate, severity, status FROM gate_firings WHERE run_id = %s AND severity = 'block'", (r.run_id,)).fetchall()
    assert (DIRTY[name].gate, "block", "open") in logged


@pytest.mark.parametrize("name", [n for n, d in DIRTY.items() if d.severity == "warn"])
def test_a_warning_goes_live_and_is_logged(gate_db, name):
    r = _run(name)
    assert r.outcome == "passed_with_warnings" and DIRTY[name].gate in {f.gate for f in r.warnings} and r.went_live
    row = gate_db.execute("SELECT status, went_live FROM gate_firings WHERE run_id = %s AND gate = %s", (r.run_id, DIRTY[name].gate)).fetchone()
    assert row == ("open", True)
    assert not r.notified                                                                         # only blocks email


def test_a_report_only_item_is_logged_but_never_a_caveat_or_banner(gate_db):
    r = _run("feed_log_mismatch")
    assert r.outcome == "passed" and "feed_reconciliation" in {f.gate for f in r.firings}
    assert status.banner(gate_db, FARM) is None
    assert all(status.caveats(gate_db, FARM, m) == [] for m in ("feed_consumed_cost", "feed_cost_per_animal", "expenses"))
    assert gate_db.execute("SELECT COUNT(*) FROM gate_firings WHERE gate = 'feed_reconciliation' AND went_live").fetchone()[0] == 0


def test_a_live_load_replaces_the_tables_so_deleted_rows_disappear(gate_db):
    n = _live(gate_db)[0]
    _run("missing_expense_month")
    assert _live(gate_db)[0] < n
    assert gate_db.execute("SELECT COUNT(*) FROM expenses WHERE date BETWEEN '2026-05-01' AND '2026-05-31'").fetchone()[0] == 0


# ------------------------------------------------------------------------------------------------------------------------ banner
def test_the_banner_appears_on_a_block_goes_stale_after_seven_days_and_clears_on_a_pass(gate_db):
    assert status.banner(gate_db, FARM) is None
    _run("currency_invalid", now=T0 + dt.timedelta(days=1))
    assert status.banner(gate_db, FARM, now=T0 + dt.timedelta(days=2)) == "Data last verified 1 Oct 2026. A newer upload is being reviewed."
    stale = status.banner(gate_db, FARM, now=T0 + dt.timedelta(days=9))
    assert stale.startswith("⚠️ Data last verified 1 Oct 2026 (9 days ago)") and "out of date" in stale
    gated_sync_workbook(str(WORKBOOK), FARM, TEST_DSN, now=T0 + dt.timedelta(days=10), notifier=lambda s, b: None)
    assert status.banner(gate_db, FARM, now=T0 + dt.timedelta(days=10)) is None
    assert gate_db.execute("SELECT status FROM gate_firings WHERE gate = 'currency_invalid'").fetchone()[0] == "resolved"


def test_a_blocked_farm_is_still_answered_from_the_last_good_data_with_the_banner(gate_db):
    _run("currency_invalid", now=T0)
    q = "How many pigs do we have?"
    a = answer_question_v2(q, gate_db, FakeRouter(script={q: S("active_headcount", domains=["piggery"])}), today=TODAY)
    assert a.kind == "answer" and a.text.splitlines()[0].startswith(("Data last verified", "⚠️ Data last verified")) and "12" in a.text


# ---------------------------------------------------------------------------------------------------------------------- caveats
def test_a_warning_adds_a_caveat_to_the_metrics_it_affects_and_only_those(gate_db):
    _run("missing_expense_month")
    q = "What were our total expenses in May 2026?"
    a = answer_question_v2(q, gate_db, FakeRouter(script={q: S("expenses", period_phrase="May 2026")}), today=TODAY)
    assert "Note: expenses has no rows for May 2026" in a.text and "not yet reviewed" in a.text
    other = "How many pigs do we have?"
    b = answer_question_v2(other, gate_db, FakeRouter(script={other: S("active_headcount", domains=["piggery"])}), today=TODAY)
    assert "Note:" not in b.text                                                                  # headcount does not read expenses


def test_a_caveat_about_one_month_is_not_added_to_an_answer_about_another(gate_db):
    _run("missing_expense_month")
    q = "What were our total expenses in March 2026?"
    a = answer_question_v2(q, gate_db, FakeRouter(script={q: S("expenses", period_phrase="March 2026")}), today=TODAY)
    assert "Note:" not in a.text


# ------------------------------------------------------------------------------------------------------------------ acknowledgements
def test_acknowledging_a_warning_removes_its_caveat_and_is_logged(gate_db):
    r = _run("missing_expense_month")
    fid = gate_db.execute("SELECT id FROM gate_firings WHERE run_id = %s AND gate = 'month_without_rows'", (r.run_id,)).fetchone()[0]
    store.acknowledge(gate_db, fid, "Sylvester Vhashe", "May receipts were lost in a flood; farm confirmed no spend", now=T0)
    assert gate_db.execute("SELECT reviewer, reason FROM gate_acks WHERE firing_id = %s", (fid,)).fetchone()[0] == "Sylvester Vhashe"
    assert status.caveats(gate_db, FARM, "expenses") == []
    assert "Acknowledged warnings: 1" in status.data_quality_report(gate_db, FARM)
    again = _run("missing_expense_month")                                                           # the same gap in the next upload stays acknowledged
    assert gate_db.execute("SELECT status FROM gate_firings WHERE run_id = %s AND gate = 'month_without_rows'", (again.run_id,)).fetchone()[0] == "acknowledged"
    assert status.caveats(gate_db, FARM, "expenses") == []


def test_acknowledgement_needs_a_reviewer_a_reason_and_a_warning(gate_db):
    r = _run("missing_expense_month")
    fid = gate_db.execute("SELECT id FROM gate_firings WHERE run_id = %s AND gate = 'month_without_rows'", (r.run_id,)).fetchone()[0]
    for bad in (("", "reason"), ("Sylvester", "  ")):
        with pytest.raises(ValueError):
            store.acknowledge(gate_db, fid, *bad)
    with pytest.raises(PermissionError):
        store.acknowledge(gate_db, fid, "A. Farmer", "ok", allowed_reviewers=["Sylvester Vhashe"])
    blocked = _run("currency_invalid")
    bid = gate_db.execute("SELECT id FROM gate_firings WHERE run_id = %s AND severity = 'block'", (blocked.run_id,)).fetchone()[0]
    with pytest.raises(ValueError, match="only warnings"):
        store.acknowledge(gate_db, bid, "Sylvester Vhashe", "looks fine")
    assert gate_db.execute("SELECT COUNT(*) FROM gate_acks").fetchone()[0] == 0


def test_a_warning_that_no_longer_fires_is_resolved(gate_db):
    _run("missing_expense_month")
    gated_sync_workbook(str(WORKBOOK), FARM, TEST_DSN, notifier=lambda s, b: None)
    assert gate_db.execute("SELECT status FROM gate_firings WHERE gate = 'month_without_rows'").fetchone()[0] == "resolved"
    assert status.caveats(gate_db, FARM, "expenses") == []


# ------------------------------------------------------------------------------------------------------------------------ failure
def test_an_upload_that_cannot_be_loaded_is_an_error_not_a_crash_and_leaves_live_alone(gate_db):
    import openpyxl
    wb = openpyxl.load_workbook(WORKBOOK, data_only=True)
    wb["02_EXPENSES"].cell(2, 4).value = "item2"                                                    # break the header the sync reads by name
    before, sent = _live(gate_db), []
    r = gated_sync_workbook_object(wb, FARM, TEST_DSN, notifier=lambda s, b: sent.append(s))
    assert r.outcome == "error" and _live(gate_db) == before and len(sent) == 1 and "failed" in sent[0]
    assert gate_db.execute("SELECT outcome FROM sync_runs WHERE id = %s", (r.run_id,)).fetchone()[0] == "error"


def test_an_unsent_email_is_recorded_not_raised(gate_db):
    def boom(s, b):
        raise OSError("smtp down")
    r = _run("currency_invalid", notifier=boom)
    assert r.outcome == "blocked" and not r.notified and "smtp down" in r.notify_error
    assert gate_db.execute("SELECT notified, notify_error FROM sync_runs WHERE id = %s", (r.run_id,)).fetchone()[0] is False


def test_the_migration_is_idempotent(gate_db):
    assert migrate(gate_db) == []
