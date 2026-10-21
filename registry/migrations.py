"""
One-time startup migrations for the v2 path. The old engine ran CREATE TABLE IF
NOT EXISTS and ALTER TABLE on query_log for EVERY question (chatbot/engine.py
_ensure_query_log_table), which raced under parallel requests on a fresh
database (UniqueViolation on pg_class) and takes a table lock each time.

Here the DDL runs once, at process startup, under a Postgres advisory lock so
two processes starting together cannot race, and each migration is recorded in
schema_migrations so it never runs twice. The result is compatible with the old
engine's own CREATE/ALTER (same columns), so both paths can share the table
during the strangler period.

    from registry.migrations import migrate
    migrate(conn)      # call once when the app starts, never per question
"""

_LOCK_KEY = 7_204_117_001      # arbitrary constant: "farm intelligence migrations"

MIGRATIONS = [
    ("001_query_log", [
        """CREATE TABLE IF NOT EXISTS query_log (
               id SERIAL PRIMARY KEY,
               logged_at TIMESTAMPTZ NOT NULL DEFAULT now(),
               farm_code TEXT NOT NULL,
               question_text TEXT NOT NULL,
               intent_source TEXT NOT NULL,
               query_id TEXT,
               failure_reason TEXT,
               scoped_out_reason TEXT
           )""",
        "ALTER TABLE query_log ADD COLUMN IF NOT EXISTS tool_name TEXT",
        "ALTER TABLE query_log ADD COLUMN IF NOT EXISTS tool_arguments JSONB",
    ]),
    ("002_query_log_v2", [
        # What the v2 path needs to log, so the shadow run and the eval can read it back.
        "ALTER TABLE query_log ADD COLUMN IF NOT EXISTS metric_id TEXT",
        "ALTER TABLE query_log ADD COLUMN IF NOT EXISTS scope JSONB",
        "ALTER TABLE query_log ADD COLUMN IF NOT EXISTS clarification_reason TEXT",
    ]),
    ("003_farm_settings", [
        # Per-farm settings (registry/settings.py): the first day of the week, the feed reconciliation tolerance.
        """CREATE TABLE IF NOT EXISTS farm_settings (
               farm_code TEXT NOT NULL,
               key TEXT NOT NULL,
               value TEXT NOT NULL,
               updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
               PRIMARY KEY (farm_code, key)
           )""",
    ]),
    ("004_llm_quota_log", [
        # Every insufficient_quota error from a model provider (router/alerts.py). `notified` marks the row that triggered the day's email.
        """CREATE TABLE IF NOT EXISTS llm_quota_log (
               id SERIAL PRIMARY KEY,
               logged_at TIMESTAMPTZ NOT NULL DEFAULT now(),
               day DATE NOT NULL,
               farm_code TEXT,
               provider TEXT NOT NULL,
               model TEXT NOT NULL,
               error TEXT NOT NULL,
               detail TEXT,
               notified BOOLEAN NOT NULL DEFAULT false,
               notify_error TEXT
           )""",
        "CREATE INDEX IF NOT EXISTS llm_quota_log_day ON llm_quota_log (day)",
    ]),
    ("005_sync_gates", [
        # One row per gated sync attempt (gates/run.py). `outcome`: passed | passed_with_warnings | blocked | error.
        """CREATE TABLE IF NOT EXISTS sync_runs (
               id SERIAL PRIMARY KEY,
               started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
               finished_at TIMESTAMPTZ,
               farm_code TEXT NOT NULL,
               outcome TEXT NOT NULL,
               data_through DATE,
               rows_written JSONB,
               detail TEXT,
               notified BOOLEAN NOT NULL DEFAULT false,
               notify_error TEXT
           )""",
        # Every gate firing, kept for false-positive measurement. `status`: open | acknowledged | resolved (resolved = a later run no longer fired it).
        """CREATE TABLE IF NOT EXISTS gate_firings (
               id SERIAL PRIMARY KEY,
               fired_at TIMESTAMPTZ NOT NULL DEFAULT now(),
               run_id INTEGER REFERENCES sync_runs(id),
               farm_code TEXT NOT NULL,
               gate TEXT NOT NULL,
               severity TEXT NOT NULL,
               tbl TEXT,
               message TEXT NOT NULL,
               rows_affected INTEGER NOT NULL DEFAULT 0,
               period_start DATE,
               period_end DATE,
               key TEXT NOT NULL,
               status TEXT NOT NULL DEFAULT 'open',
               went_live BOOLEAN NOT NULL DEFAULT false
           )""",
        "CREATE INDEX IF NOT EXISTS gate_firings_open ON gate_firings (farm_code, status, severity)",
        # Who acknowledged a warning, why, and when. Blocks are never acknowledged; the next passing run clears them.
        """CREATE TABLE IF NOT EXISTS gate_acks (
               id SERIAL PRIMARY KEY,
               firing_id INTEGER NOT NULL REFERENCES gate_firings(id),
               reviewer TEXT NOT NULL,
               reason TEXT NOT NULL,
               acked_at TIMESTAMPTZ NOT NULL DEFAULT now()
           )""",
        # The last snapshot that passed the gates: what is live, when it was verified, and whether a newer upload is held back.
        """CREATE TABLE IF NOT EXISTS data_snapshot (
               farm_code TEXT PRIMARY KEY,
               verified_at TIMESTAMPTZ NOT NULL,
               data_through DATE,
               held_back BOOLEAN NOT NULL DEFAULT false,
               held_since TIMESTAMPTZ
           )""",
    ]),
    ("006_shadow_mode", [
        # The new engine's answer to the same question the old engine answered (shadow/runner.py), and what a person decided about any disagreement.
        """CREATE TABLE IF NOT EXISTS shadow_log (
               id SERIAL PRIMARY KEY,
               logged_at TIMESTAMPTZ NOT NULL DEFAULT now(),
               farm_code TEXT NOT NULL,
               question TEXT NOT NULL,
               filter_from DATE,
               filter_to DATE,
               old_kind TEXT NOT NULL,
               old_intent_source TEXT,
               old_reason TEXT,
               old_text TEXT,
               new_kind TEXT NOT NULL,
               new_code TEXT,
               new_metric TEXT,
               new_scope JSONB,
               new_text TEXT,
               new_error TEXT,
               model TEXT,
               prompt_version TEXT,
               llm_seconds DOUBLE PRECISION,
               total_seconds DOUBLE PRECISION,
               cost_usd DOUBLE PRECISION,
               classification TEXT NOT NULL,
               needs_label BOOLEAN NOT NULL DEFAULT false,
               label TEXT,
               label_note TEXT,
               labelled_by TEXT,
               labelled_at TIMESTAMPTZ
           )""",
        "CREATE INDEX IF NOT EXISTS shadow_log_class ON shadow_log (farm_code, classification, needs_label)",
        # The "report wrong answer" button (any engine). `status`: new | triaged | added_to_eval | dismissed.
        """CREATE TABLE IF NOT EXISTS wrong_answer_reports (
               id SERIAL PRIMARY KEY,
               reported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
               farm_code TEXT NOT NULL,
               engine TEXT NOT NULL,
               question TEXT NOT NULL,
               answer_shown TEXT NOT NULL,
               note TEXT,
               shadow_id INTEGER REFERENCES shadow_log(id),
               status TEXT NOT NULL DEFAULT 'new'
           )""",
    ]),
]


def migrate(conn) -> list:
    """Apply any migrations not yet recorded. Idempotent and safe to call from several
    processes at once. Returns the ids applied by THIS call."""
    applied_now = []
    conn.execute("SELECT pg_advisory_lock(%s)", (_LOCK_KEY,))
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
                            id TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        done = {r[0] for r in conn.execute("SELECT id FROM schema_migrations").fetchall()}
        for mid, statements in MIGRATIONS:
            if mid in done:
                continue
            for sql in statements:
                conn.execute(sql)
            conn.execute("INSERT INTO schema_migrations (id) VALUES (%s)", (mid,))
            applied_now.append(mid)
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_KEY,))
    return applied_now
