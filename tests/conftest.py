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
