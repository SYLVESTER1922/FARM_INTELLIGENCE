import getpass

import psycopg
import pytest

TEST_DSN = f"host=localhost dbname=farm_intelligence_test user={getpass.getuser()}"


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
