"""The "report wrong answer" button: whoever is using the chat flags an answer they think is wrong. Stored as-is for triage; nothing here adds an eval
case (those are Sylvester's to approve), but `export_for_review` writes the reports as a CSV of draft cases."""

import csv


def record_report(conn, farm_code, question, answer_shown, note="", *, engine="old", shadow_id=None):
    if not str(question or "").strip() or not str(answer_shown or "").strip():
        raise ValueError("a report needs the question and the answer that was shown")
    if engine not in ("old", "new"):
        raise ValueError("engine must be 'old' or 'new'")
    return conn.execute(
        """INSERT INTO wrong_answer_reports (farm_code, engine, question, answer_shown, note, shadow_id) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
        (farm_code, engine, question.strip(), answer_shown, (note or "").strip()[:1000], shadow_id)).fetchone()[0]


def last_exchange(chat_history):
    """(question, answer) of the latest user turn and the assistant reply to it in a Gradio messages-style history, or (None, None)."""
    msgs = [m for m in (chat_history or []) if isinstance(m, dict)]
    for i in range(len(msgs) - 1, 0, -1):
        if msgs[i].get("role") == "assistant" and msgs[i - 1].get("role") == "user":
            return msgs[i - 1].get("content"), msgs[i].get("content")
    return None, None


def report_from_chat(dsn, farm_code, chat_history, note="", *, conn=None, engine="old"):
    """Used by the button. Returns the message to show. Never raises."""
    import psycopg
    q, a = last_exchange(chat_history)
    if not q or not a:
        return "Ask a question first, then report its answer."
    own = conn is None
    try:
        conn = conn or psycopg.connect(dsn, autocommit=True, prepare_threshold=None)
        if conn.execute("SELECT to_regclass('wrong_answer_reports')").fetchone()[0] is None:
            return "Thanks. The report could not be saved right now."
        shadow_id = conn.execute("SELECT id FROM shadow_log WHERE farm_code = %s AND question = %s ORDER BY id DESC LIMIT 1", (farm_code, q.strip())).fetchone() \
            if conn.execute("SELECT to_regclass('shadow_log')").fetchone()[0] else None
        record_report(conn, farm_code, q, a, note, engine=engine, shadow_id=shadow_id[0] if shadow_id else None)
        return "Thanks. That answer has been flagged for review."
    except Exception:
        return "Thanks. The report could not be saved right now."
    finally:
        if own and conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def export_for_review(conn, farm_code, path, status="new"):
    rows = conn.execute("SELECT id, reported_at, engine, question, answer_shown, note FROM wrong_answer_reports WHERE farm_code = %s AND status = %s ORDER BY id",
                        (farm_code, status)).fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["report_id", "reported_at", "engine", "question", "answer_shown", "note", "what_should_it_say", "approve_as_dev_case (y/n)"])
        for r in rows:
            w.writerow([*r, "", ""])
    return len(rows)
