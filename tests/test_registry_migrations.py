"""The query_log startup migration: runs once, is safe to run from many processes at once (the old per-question
CREATE/ALTER raced on a fresh database), and stays compatible with the old engine's own DDL and INSERT."""

import concurrent.futures as cf

import psycopg
import pytest

from registry.migrations import MIGRATIONS, migrate


def _columns(conn, table):
    return {r[0] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table,)).fetchall()}


def test_migrate_creates_query_log_with_every_column_and_is_idempotent(db_conn):
    first = migrate(db_conn)
    assert first == [mid for mid, _ in MIGRATIONS]
    assert {"farm_code", "question_text", "intent_source", "tool_name", "tool_arguments",
            "metric_id", "scope", "clarification_reason"} <= _columns(db_conn, "query_log")
    assert migrate(db_conn) == []                                  # second call applies nothing
    assert db_conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == len(MIGRATIONS)


def test_migrate_adds_the_v2_columns_to_an_existing_old_query_log(db_conn):
    """Production already has the table, created by the old engine, without the v2 columns."""
    db_conn.execute("""CREATE TABLE query_log (id SERIAL PRIMARY KEY, logged_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        farm_code TEXT NOT NULL, question_text TEXT NOT NULL, intent_source TEXT NOT NULL, query_id TEXT,
        failure_reason TEXT, scoped_out_reason TEXT)""")
    db_conn.execute("INSERT INTO query_log (farm_code, question_text, intent_source) VALUES ('NIS-001', 'old row', 'deterministic')")
    migrate(db_conn)
    assert {"tool_name", "tool_arguments", "metric_id", "scope", "clarification_reason"} <= _columns(db_conn, "query_log")
    assert db_conn.execute("SELECT COUNT(*) FROM query_log").fetchone()[0] == 1       # existing rows survive


def test_old_engine_ddl_and_insert_still_work_after_the_migration(db_conn):
    from chatbot.engine import Answer, _ensure_query_log_table, _log
    migrate(db_conn)
    _ensure_query_log_table(db_conn)                                # the old per-question DDL is now a no-op
    _log(db_conn, "NIS-001", "How many pigs?", Answer(text="12", intent_source="tool_fallback", tool_name="q_headcount"))
    assert db_conn.execute("SELECT tool_name FROM query_log").fetchone()[0] == "q_headcount"


def test_eight_processes_starting_at_once_do_not_race(db_conn, test_dsn):
    """The failure the eval harness hit: parallel CREATE TABLE IF NOT EXISTS on a fresh database raised
    UniqueViolation on pg_class. Under the advisory lock every migration is applied exactly once."""
    def start(_):
        with psycopg.connect(test_dsn, autocommit=True) as conn:
            return migrate(conn)

    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        applied = list(pool.map(start, range(8)))                  # raises if any worker hit an error
    flat = [mid for ids in applied for mid in ids]
    assert sorted(flat) == sorted(mid for mid, _ in MIGRATIONS)    # each applied once, by exactly one worker


def test_the_advisory_lock_is_released(db_conn, test_dsn):
    migrate(db_conn)
    with psycopg.connect(test_dsn, autocommit=True) as other:
        assert other.execute("SELECT pg_try_advisory_lock(7204117001)").fetchone()[0] is True
        other.execute("SELECT pg_advisory_unlock(7204117001)")


def test_migrate_in_transaction_can_be_limited_to_chosen_migrations_and_is_idempotent(db_conn):
    import psycopg
    from registry.migrations import migrate_in_transaction, pending
    from tests.conftest import TEST_DSN
    db_conn.close()
    conn = psycopg.connect(TEST_DSN, autocommit=False)
    try:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.commit()
        assert [m for m, _ in pending(only=("005_sync_gates", "006_shadow_mode"))] == ["005_sync_gates", "006_shadow_mode"]
        assert migrate_in_transaction(conn, only=("005_sync_gates", "006_shadow_mode")) == ["005_sync_gates", "006_shadow_mode"]
        tables = {r[0] for r in conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
        assert tables == {"schema_migrations", "sync_runs", "gate_firings", "gate_acks", "data_snapshot", "shadow_log", "wrong_answer_reports"}
        assert migrate_in_transaction(conn, only=("005_sync_gates", "006_shadow_mode")) == []
        assert [m for m, _ in pending({"005_sync_gates"})][-1] == "006_shadow_mode" and len(pending({"005_sync_gates", "006_shadow_mode"})) == 4
    finally:
        conn.close()


def test_a_failing_statement_rolls_back_the_whole_migration(db_conn, monkeypatch):
    import psycopg
    from registry import migrations
    from tests.conftest import TEST_DSN
    db_conn.close()
    monkeypatch.setattr(migrations, "MIGRATIONS", [("901_ok", ["CREATE TABLE zz_one (id INT)"]), ("902_bad", ["CREATE TABLE zz_two (id INT)", "SELECT * FROM no_such_table"])])
    conn = psycopg.connect(TEST_DSN, autocommit=False)
    try:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.commit()
        with pytest.raises(psycopg.Error):
            migrations.migrate_in_transaction(conn)
        conn.rollback()
        left = {r[0] for r in conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
        assert left == set()                                          # not even schema_migrations or zz_one survives
    finally:
        conn.close()
