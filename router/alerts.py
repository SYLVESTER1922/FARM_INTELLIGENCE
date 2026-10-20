"""
Quota alerts (plan section 23). An `insufficient_quota` error means the model provider's account has no credit: every question fails
until someone tops it up, and waiting does not help. Each occurrence is written to `llm_quota_log`; the FIRST one each day (Africa/Harare
calendar day) also sends one email, so a stalled bot is noticed without flooding the inbox.

Email settings come from the environment, never from code or the repo:
    ALERT_SMTP_HOST, ALERT_SMTP_PORT (default 587), ALERT_SMTP_USER, ALERT_SMTP_PASSWORD, ALERT_EMAIL_FROM, ALERT_EMAIL_TO
If they are not set the occurrence is still logged, with the reason the email was not sent, and the next occurrence tries again.
Nothing here can break a reply: every failure is swallowed after being recorded.
"""

import logging
import os
import smtplib
from email.message import EmailMessage

from resolver.periods import harare_today

log = logging.getLogger("router.alerts")


def smtp_notifier(env=None):
    """A function (subject, body) -> None that sends through SMTP using the ALERT_* settings, or None if they are incomplete."""
    env = os.environ if env is None else env
    host, to = env.get("ALERT_SMTP_HOST"), env.get("ALERT_EMAIL_TO")
    if not (host and to):
        return None
    sender = env.get("ALERT_EMAIL_FROM") or env.get("ALERT_SMTP_USER") or to

    def send(subject, body):
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, sender, to
        msg.set_content(body)
        with smtplib.SMTP(host, int(env.get("ALERT_SMTP_PORT", "587")), timeout=15) as s:
            s.starttls()
            if env.get("ALERT_SMTP_USER"):
                s.login(env["ALERT_SMTP_USER"], env.get("ALERT_SMTP_PASSWORD", ""))
            s.send_message(msg)

    return send


def _table_exists(conn):
    return conn.execute("SELECT to_regclass('llm_quota_log')").fetchone()[0] is not None


def report_quota_error(conn, llm_result, *, farm_code=None, notifier=None, today=None) -> dict:
    """Log one insufficient_quota error and, if it is the first of the day, email about it. Returns what happened (for tests and logs)."""
    out = {"logged": False, "emailed": False, "reason": None}
    try:
        if not _table_exists(conn):
            out["reason"] = "llm_quota_log missing (run registry.migrations.migrate at startup)"
            log.error("LLM quota exhausted (%s %s); %s", llm_result.provider, llm_result.model, out["reason"])
            return out
        day = today or harare_today()
        row_id = conn.execute(
            """INSERT INTO llm_quota_log (day, farm_code, provider, model, error, detail)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (day, farm_code, llm_result.provider or "unknown", llm_result.model or "unknown", llm_result.error,
             (llm_result.detail or "")[:300])).fetchone()[0]
        out["logged"] = True
        # Claim the day's email: only one row per day can flip notified to true.
        claimed = conn.execute(
            """UPDATE llm_quota_log SET notified = true
               WHERE id = %s AND NOT EXISTS (SELECT 1 FROM llm_quota_log WHERE day = %s AND notified)
               RETURNING id""", (row_id, day)).fetchone()
        if not claimed:
            return out
        notify = notifier if notifier is not None else smtp_notifier()
        if notify is None:
            conn.execute("UPDATE llm_quota_log SET notified = false, notify_error = %s WHERE id = %s",
                         ("email not configured (ALERT_SMTP_HOST / ALERT_EMAIL_TO)", row_id))
            out["reason"] = "email not configured"
            log.error("LLM quota exhausted (%s %s); email not configured", llm_result.provider, llm_result.model)
            return out
        try:
            notify(f"[Farm Intelligence] {llm_result.provider} account out of credit",
                   f"The {llm_result.provider} account used for question routing ({llm_result.model}) returned "
                   f"'insufficient quota' on {day}. Until credit is added the chatbot cannot answer new questions "
                   f"(only a few exact phrases still work).\n\nAdd credit, or turn on billing alerts and auto-recharge, in the "
                   f"provider's billing settings. This email is sent once per day; every occurrence is in the llm_quota_log table.\n\n"
                   f"Provider message: {(llm_result.detail or 'none')[:300]}\n")
            out["emailed"] = True
        except Exception as e:                       # the next occurrence tries again
            conn.execute("UPDATE llm_quota_log SET notified = false, notify_error = %s WHERE id = %s",
                         (f"{type(e).__name__}: {e}"[:300], row_id))
            out["reason"] = f"email failed: {type(e).__name__}"
            log.error("LLM quota exhausted; the alert email failed: %s", type(e).__name__)
    except Exception as e:                           # never let an alert break a reply
        out["reason"] = f"alert failed: {type(e).__name__}"
        log.error("quota alert failed: %s", type(e).__name__)
    return out
