import getpass
import os

import psycopg
import pytest

TEST_DSN = f"host=localhost dbname=farm_intelligence_test user={getpass.getuser()}"

_OPENAI_KEY_PATH = os.path.expanduser("~/.openai_api_key")
if "OPENAI_API_KEY" not in os.environ and os.path.exists(_OPENAI_KEY_PATH):
    with open(_OPENAI_KEY_PATH) as f:
        os.environ["OPENAI_API_KEY"] = f.read().strip()


@pytest.fixture
def test_dsn():
    return TEST_DSN


@pytest.fixture
def db_conn():
    conn = psycopg.connect(TEST_DSN, autocommit=True)
    conn.execute("DROP SCHEMA public CASCADE")
    conn.execute("CREATE SCHEMA public")
    yield conn
    conn.close()


def _rebuild_farm_db(conn):
    from pathlib import Path
    from sync.engine import sync_workbook_to_supabase

    conn.execute("DROP SCHEMA public CASCADE")
    conn.execute("CREATE SCHEMA public")
    workbook = Path(__file__).parent.parent / "Netrisyl_Farm_Intelligence_Workbook.xlsx"
    report = sync_workbook_to_supabase(str(workbook), farm_code="NIS-001", dsn=TEST_DSN)
    assert report.errors == []


@pytest.fixture(scope="module")
def farm_db():
    """The real generated workbook (Netrisyl_Farm_Intelligence_Workbook.xlsx), synced ONCE per test module into
    the local test database through the production sync - the same data the eval harness uses. Read-only on
    the workbook. READ-ONLY for tests: a test that changes data must use `mutable_farm_db`. Module-scoped:
    don't combine with the function-scoped db_conn, which drops the schema."""
    conn = psycopg.connect(TEST_DSN, autocommit=True)
    _rebuild_farm_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def mutable_farm_db(farm_db):
    """For tests that modify data: yields the same connection, then rebuilds pristine data afterwards so
    nothing leaks into the next test."""
    yield farm_db
    _rebuild_farm_db(farm_db)
