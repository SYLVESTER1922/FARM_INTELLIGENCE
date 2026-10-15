"""
Safety guard for the eval harness. The harness drops and rebuilds the
`public` schema of whatever database it is pointed at, so it refuses to run
unless DATABASE_URL names the LOCAL `farm_intelligence_test` database and
nothing else - never a Supabase/pooler DSN, never another database name.

Checked twice: once on the parsed URL, and again against the live
connection (`current_database()`, and that the server address is loopback or
a unix socket), so a DATABASE_URL that parses cleanly but is routed
somewhere unexpected is still caught.
"""

import os

import psycopg
from psycopg.conninfo import conninfo_to_dict

REQUIRED_DBNAME = "farm_intelligence_test"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", ""}


class UnsafeDatabase(SystemExit):
    pass


def _refuse(reason: str):
    raise UnsafeDatabase(
        f"REFUSING TO RUN: {reason}\n"
        f"The eval harness only runs against a local '{REQUIRED_DBNAME}' database. "
        f"Set DATABASE_URL, e.g. DATABASE_URL=postgresql://$USER@localhost/{REQUIRED_DBNAME}"
    )


def checked_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        _refuse("DATABASE_URL is not set.")
    try:
        parts = conninfo_to_dict(url)
    except Exception as e:  # malformed URL
        _refuse(f"DATABASE_URL could not be parsed ({type(e).__name__}).")

    host = parts.get("host", "")
    # A unix-socket directory (starts with "/") is local too.
    if host not in LOCAL_HOSTS and not host.startswith("/"):
        _refuse(f"host is {host!r}, not localhost.")
    if parts.get("hostaddr") not in (None, "127.0.0.1", "::1"):
        _refuse(f"hostaddr is {parts.get('hostaddr')!r}, not loopback.")
    if parts.get("dbname") != REQUIRED_DBNAME:
        _refuse(f"database name is {parts.get('dbname')!r}, not {REQUIRED_DBNAME!r}.")
    return url


def verify_live_connection(conn) -> None:
    """Second check, against the connection actually opened."""
    dbname = conn.execute("SELECT current_database()").fetchone()[0]
    if dbname != REQUIRED_DBNAME:
        _refuse(f"connected database is {dbname!r}, not {REQUIRED_DBNAME!r}.")
    addr = conn.execute("SELECT inet_server_addr()").fetchone()[0]
    # NULL means a unix-socket connection, which is local.
    if addr is not None and str(addr) not in ("127.0.0.1", "::1"):
        _refuse(f"server address is {addr}, not loopback.")


def connect_guarded() -> psycopg.Connection:
    url = checked_database_url()
    conn = psycopg.connect(url, autocommit=True)
    try:
        verify_live_connection(conn)
    except BaseException:
        conn.close()
        raise
    return conn
