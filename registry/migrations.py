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
