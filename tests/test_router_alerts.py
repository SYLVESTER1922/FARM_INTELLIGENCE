"""Quota alerts: every insufficient_quota error is logged; the first of each Harare day sends one email; nothing can break a reply."""

import datetime as dt

import pytest

from registry.migrations import migrate
from router import alerts, answer_question_v2
from router.llm import LLMResult
from router.llm_fake import FakeRouter

D1, D2 = dt.date(2026, 10, 19), dt.date(2026, 10, 20)


def quota(model="gpt-4.1"):
    return LLMResult(error="InsufficientQuota", provider="openai", model=model, detail="You have no credits remaining.")


class Outbox:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def __call__(self, subject, body):
        if self.fail:
            raise ConnectionError("smtp down")
        self.sent.append((subject, body))


def rows(conn):
    return conn.execute("SELECT day, notified, notify_error FROM llm_quota_log ORDER BY id").fetchall()


def test_every_occurrence_is_logged_but_only_the_first_of_the_day_sends_an_email(db_conn):
    migrate(db_conn)
    box = Outbox()
    outs = [alerts.report_quota_error(db_conn, quota(), notifier=box, today=D1) for _ in range(3)]
    assert [o["emailed"] for o in outs] == [True, False, False] and all(o["logged"] for o in outs)
    assert len(box.sent) == 1 and "out of credit" in box.sent[0][0] and "auto-recharge" in box.sent[0][1]
    assert [r[1] for r in rows(db_conn)] == [True, False, False]
    alerts.report_quota_error(db_conn, quota(), notifier=box, today=D2)               # a new day, a new email
    assert len(box.sent) == 2


def test_the_email_never_contains_a_key_and_names_the_model(db_conn):
    migrate(db_conn)
    box = Outbox()
    alerts.report_quota_error(db_conn, quota("gpt-4o-mini"), notifier=box, today=D1)
    body = box.sent[0][1]
    assert "gpt-4o-mini" in body and "sk-" not in body


def test_without_email_settings_it_is_logged_with_the_reason_and_tried_again_next_time(db_conn, monkeypatch):
    for k in ("ALERT_SMTP_HOST", "ALERT_EMAIL_TO"):
        monkeypatch.delenv(k, raising=False)
    migrate(db_conn)
    o = alerts.report_quota_error(db_conn, quota(), today=D1)
    assert o["logged"] and not o["emailed"] and "not configured" in o["reason"]
    assert rows(db_conn)[0][1] is False and "not configured" in rows(db_conn)[0][2]
    box = Outbox()
    assert alerts.report_quota_error(db_conn, quota(), notifier=box, today=D1)["emailed"]        # configured later the same day: sent


def test_a_failed_email_is_recorded_and_retried_by_the_next_occurrence(db_conn):
    migrate(db_conn)
    o = alerts.report_quota_error(db_conn, quota(), notifier=Outbox(fail=True), today=D1)
    assert o["logged"] and not o["emailed"] and "ConnectionError" in o["reason"] and "smtp down" in rows(db_conn)[0][2]
    box = Outbox()
    assert alerts.report_quota_error(db_conn, quota(), notifier=box, today=D1)["emailed"] and len(box.sent) == 1


def test_a_missing_table_is_survivable(db_conn):
    o = alerts.report_quota_error(db_conn, quota(), notifier=Outbox(), today=D1)
    assert not o["logged"] and "missing" in o["reason"]


def test_smtp_settings_come_from_the_environment_only():
    assert alerts.smtp_notifier({}) is None
    assert alerts.smtp_notifier({"ALERT_SMTP_HOST": "smtp.example.test"}) is None              # no recipient
    assert callable(alerts.smtp_notifier({"ALERT_SMTP_HOST": "smtp.example.test", "ALERT_EMAIL_TO": "ops@example.test"}))


def test_the_reply_is_honest_and_the_alert_fires_once_per_question(farm_db):
    seen = []
    a = answer_question_v2("What was our feed cost last month?", farm_db, FakeRouter(error="InsufficientQuota"),
                           today=D1, quota_alert=lambda conn, res, **kw: seen.append((res.error, kw)))
    assert (a.kind, a.code) == ("refusal", "llm_unavailable") and "busy" not in a.text         # not "try again in a minute"
    assert seen == [("InsufficientQuota", {"farm_code": "NIS-001"})]
    answer_question_v2("What was our feed cost last month?", farm_db, FakeRouter(error="RateLimitError"), today=D1,
                       quota_alert=lambda *a, **k: pytest.fail("a rate limit is not a quota error"))


def test_an_alert_that_raises_cannot_break_the_reply(farm_db):
    # the real hook swallows its own errors (here the "connection" is not even a connection)
    out = alerts.report_quota_error(object(), quota(), notifier=Outbox(), today=D1)
    assert not out["logged"] and "alert failed" in out["reason"]


def test_an_exhausted_account_is_recognised_under_either_error_code():
    from router.llm_openai import is_quota_error

    class E(Exception):
        def __init__(self, code=None, body=None):
            self.code, self.body = code, body

    assert is_quota_error(E("insufficient_quota"))
    assert is_quota_error(E("credit_balance_exhausted"))
    assert is_quota_error(E(None, {"error": {"code": "credit_balance_exhausted", "type": "insufficient_quota"}}))
    assert not is_quota_error(E("rate_limit_exceeded", {"error": {"code": "rate_limit_exceeded", "type": "requests"}}))
    assert not is_quota_error(E())
