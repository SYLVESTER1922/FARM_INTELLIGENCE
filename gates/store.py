"""Run, firing and acknowledgement logs (tables created by registry/migrations.py, migration 005_sync_gates). Plain functions over a connection."""

import datetime as dt

from gates import BLOCK, REPORT, WARN


def _ready(conn):
    return conn.execute("SELECT to_regclass('sync_runs') IS NOT NULL AND to_regclass('gate_firings') IS NOT NULL").fetchone()[0]


def record_run(conn, farm_code, outcome, firings, *, rows_written=None, detail=None, data_through=None, went_live=False, now=None):
    """Log one gated sync and every firing it produced. A firing whose key was acknowledged earlier and has not been cleared since keeps that
    acknowledgement (status 'acknowledged'); the same issue seen again supersedes its earlier row; open firings of an earlier run that no longer fire are marked 'resolved'. Returns the run id."""
    import json
    run_id = conn.execute(
        """INSERT INTO sync_runs (started_at, finished_at, farm_code, outcome, data_through, rows_written, detail)
           VALUES (COALESCE(%s, now()), COALESCE(%s, now()), %s, %s, %s, %s, %s) RETURNING id""",
        (now, now, farm_code, outcome, data_through, json.dumps(rows_written or {}), (detail or "")[:2000])).fetchone()[0]
    keys = {f.key for f in firings}
    for f in firings:
        prior = conn.execute(
            """SELECT status FROM gate_firings WHERE farm_code = %s AND key = %s AND severity <> 'block' ORDER BY id DESC LIMIT 1""",
            (farm_code, f.key)).fetchone()
        status = "acknowledged" if prior and prior[0] == "acknowledged" else "open"
        conn.execute("UPDATE gate_firings SET status = 'superseded' WHERE farm_code = %s AND key = %s AND status IN ('open', 'acknowledged')",
                     (farm_code, f.key))                      # one live row per issue: this run's row replaces the earlier run's
        conn.execute(
            """INSERT INTO gate_firings (fired_at, run_id, farm_code, gate, severity, tbl, message, rows_affected, period_start, period_end, key, status, went_live)
               VALUES (COALESCE(%s, now()), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (now, run_id, farm_code, f.gate, f.severity, f.table, f.message, f.rows, f.period[0] if f.period else None,
             f.period[1] if f.period else None, f.key, status, bool(went_live and f.severity == WARN)))
    # Earlier firings that did not fire this time are resolved (a block resolves when a later upload passes; so does a warning that went away).
    if outcome in ("passed", "passed_with_warnings"):
        conn.execute("""UPDATE gate_firings SET status = 'resolved'
                        WHERE farm_code = %s AND status IN ('open', 'acknowledged') AND run_id <> %s AND NOT (key = ANY(%s))""",
                     (farm_code, run_id, list(keys)))
    return run_id


def open_warnings(conn, farm_code):
    """Warnings that are live and not acknowledged, newest run only."""
    if not _ready(conn):
        return []
    return conn.execute(
        """SELECT id, gate, tbl, message, rows_affected, period_start, period_end, key FROM gate_firings
           WHERE farm_code = %s AND severity = %s AND status = 'open' AND went_live ORDER BY id""", (farm_code, WARN)).fetchall()


def acknowledge(conn, firing_id, reviewer, reason, *, allowed_reviewers=None, now=None):
    """Acknowledge a WARNING: it stays in the data-quality report but stops carrying a caveat. Logged with reviewer, reason and time.
    Blocks and report-only items cannot be acknowledged (a block clears when a later upload passes). During the pilot only the listed
    reviewers (Netrisyl) may acknowledge; `allowed_reviewers=None` accepts any named reviewer."""
    if not str(reviewer or "").strip() or not str(reason or "").strip():
        raise ValueError("an acknowledgement needs a reviewer and a reason")
    if allowed_reviewers is not None and reviewer not in allowed_reviewers:
        raise PermissionError(f"{reviewer!r} may not acknowledge warnings during the pilot")
    row = conn.execute("SELECT severity, status FROM gate_firings WHERE id = %s", (firing_id,)).fetchone()
    if row is None:
        raise ValueError(f"no gate firing {firing_id}")
    severity, status = row
    if severity != WARN:
        raise ValueError(f"only warnings can be acknowledged; this one is '{severity}'")
    if status != "open":
        raise ValueError(f"this warning is already {status}")
    conn.execute("UPDATE gate_firings SET status = 'acknowledged' WHERE id = %s", (firing_id,))
    conn.execute("INSERT INTO gate_acks (firing_id, reviewer, reason, acked_at) VALUES (%s, %s, %s, COALESCE(%s, now()))",
                 (firing_id, reviewer.strip(), reason.strip(), now))


def set_snapshot(conn, farm_code, *, passed, data_through=None, now=None):
    """After a pass the live data is the new verified snapshot; after a block the verified snapshot is unchanged and a newer upload is held back."""
    if passed:
        conn.execute(
            """INSERT INTO data_snapshot (farm_code, verified_at, data_through, held_back, held_since)
               VALUES (%s, COALESCE(%s, now()), %s, false, NULL)
               ON CONFLICT (farm_code) DO UPDATE SET verified_at = EXCLUDED.verified_at, data_through = EXCLUDED.data_through,
                                                     held_back = false, held_since = NULL""", (farm_code, now, data_through))
    else:
        conn.execute("UPDATE data_snapshot SET held_back = true, held_since = COALESCE(held_since, COALESCE(%s, now())) WHERE farm_code = %s", (now, farm_code))
