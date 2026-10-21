"""
The gated sync (plan section 9, decision D8). One transaction: load the workbook into a `staging` schema with the existing sync code, run the
gates on it, and either replace the live tables (pass) or roll everything back (block). Because the load is a transaction, a block leaves the
live tables exactly as they were: that is the "last good snapshot". The outcome, every firing and the snapshot state are then logged on a
separate connection, and a block emails Sylvester.

    gated_sync_workbook(path, "NIS-001", dsn)        # .xlsx
    gated_sync_sheet(sheet_id, "NIS-001", dsn, creds_json)

Live tables are REPLACED (truncate and reload from staging), so a row deleted from the sheet disappears from the app; the earlier sync only
upserted and kept it. This function never raises: a failure is an 'error' outcome, the live tables untouched.
"""

import re
from dataclasses import dataclass, field

import psycopg

from gates import BLOCK, WARN, checks, store
from gates.notify import notify_block
from sync import engine


@dataclass
class GateResult:
    outcome: str                                    # passed | passed_with_warnings | blocked | error
    firings: list = field(default_factory=list)
    rows_written: dict = field(default_factory=dict)
    detail: str = ""
    run_id: int = None
    notified: bool = False
    notify_error: str = None

    @property
    def went_live(self):
        return self.outcome in ("passed", "passed_with_warnings")

    @property
    def blocks(self):
        return [f for f in self.firings if f.severity == BLOCK]

    @property
    def warnings(self):
        return [f for f in self.firings if f.severity == WARN]


class _Staging:
    """The connection the sync writes through. An INSERT ... ON CONFLICT that conflicts with a row of THIS load (staging starts empty) means the
    upload repeats a primary key; that is recorded for the duplicate-key gate instead of being silently merged."""

    def __init__(self, conn):
        self._conn, self.duplicates = conn, {}

    def execute(self, sql, params=None):
        m = re.match(r"\s*INSERT INTO (\w+)", sql)
        if m and "ON CONFLICT" in sql and "RETURNING" not in sql:
            cur = self._conn.execute(sql + " RETURNING (xmax = 0)", params)
            row = cur.fetchone()
            if row is None or not row[0]:
                sample = ", ".join(str(p) for p in (params or ())[:3])
                self.duplicates.setdefault(m.group(1), []).append(sample)
            return cur
        return self._conn.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _swap(conn, tables):
    """Replace the live copy of each staged table with the staging copy, in the order the sync wrote them (parents first)."""
    for t in tables:
        if conn.execute("SELECT to_regclass(%s)", (f"public.{t}",)).fetchone()[0] is None:
            conn.execute(f"CREATE TABLE public.{t} (LIKE staging.{t} INCLUDING ALL)")
    conn.execute("TRUNCATE " + ", ".join(f"public.{t}" for t in tables))
    for t in tables:
        conn.execute(f"INSERT INTO public.{t} SELECT * FROM staging.{t}")


def _tolerance(conn, farm_code):
    try:
        from registry.settings import get_settings
        return float(get_settings(conn, farm_code)["feed_reconciliation_tolerance_pct"])
    except Exception:
        return 5.0


def gated_sync_workbook_object(wb, farm_code, dsn, *, notifier=None, now=None) -> GateResult:
    from registry.core import latest_log_date
    result = GateResult("error")
    conn = psycopg.connect(dsn, autocommit=False, prepare_threshold=None)
    data_through = None
    try:
        conn.execute("DROP SCHEMA IF EXISTS staging CASCADE")
        conn.execute("CREATE SCHEMA staging")
        conn.execute("SET LOCAL search_path TO staging, public")
        stage = _Staging(conn)
        report = engine._sync_from_workbook(wb, farm_code, dsn, conn=stage)
        result.rows_written = dict(report.rows_written)
        tol = _tolerance(conn, farm_code)
        result.firings = checks.run_all(stage, farm_code, sync_errors=report.errors, duplicates=stage.duplicates, tolerance_pct=tol)
        if result.blocks:
            conn.rollback()
            result.outcome = "blocked"
            result.detail = f"{len(result.blocks)} block(s): " + "; ".join(f.gate for f in result.blocks)
        else:
            conn.execute("SET LOCAL search_path TO public")
            _swap(conn, list(report.rows_written))
            conn.execute("DROP SCHEMA staging CASCADE")
            data_through = latest_log_date(conn)
            conn.commit()
            result.outcome = "passed_with_warnings" if result.warnings else "passed"
    except Exception as e:                                           # a load that cannot finish leaves the live tables untouched
        try:
            conn.rollback()
        except Exception:
            pass
        result.outcome, result.detail = "error", f"{type(e).__name__}: {e}"[:500]
    finally:
        conn.close()
    _log(result, farm_code, dsn, data_through, notifier, now)
    return result


def _log(result, farm_code, dsn, data_through, notifier, now):
    """Record the run on a fresh connection (the staging transaction is gone). Never raises."""
    try:
        with psycopg.connect(dsn, autocommit=True, prepare_threshold=None) as log:
            if not store._ready(log):
                result.detail += " (sync gate log tables missing: run registry.migrations.migrate)"
                return
            result.run_id = store.record_run(log, farm_code, result.outcome, result.firings, rows_written=result.rows_written,
                                             detail=result.detail, data_through=data_through, went_live=result.went_live, now=now)
            if result.went_live:
                store.set_snapshot(log, farm_code, passed=True, data_through=data_through, now=now)
            elif result.outcome == "blocked":
                store.set_snapshot(log, farm_code, passed=False, now=now)
            if result.outcome in ("blocked", "error"):
                blocks = result.blocks or [checks.Firing("sync_error", BLOCK, result.detail or "the upload could not be loaded")]
                result.notified, result.notify_error = notify_block(farm_code, blocks, notifier, result.outcome)
                log.execute("UPDATE sync_runs SET notified = %s, notify_error = %s WHERE id = %s", (result.notified, result.notify_error, result.run_id))
    except Exception as e:
        result.detail += f" (logging failed: {type(e).__name__})"


def gated_sync_workbook(filepath, farm_code, dsn, **kw) -> GateResult:
    import openpyxl
    return gated_sync_workbook_object(openpyxl.load_workbook(filepath, data_only=True), farm_code, dsn, **kw)


def gated_sync_sheet(sheet_id, farm_code, dsn, creds_json, **kw) -> GateResult:
    from sync.sheets_io import load_sheets_workbook
    try:
        wb = load_sheets_workbook(sheet_id, creds_json)
    except Exception as e:                                           # Sheets hiccup: nothing was loaded, live untouched
        res = GateResult("error", detail=f"{type(e).__name__}: {e}"[:500])
        _log(res, farm_code, dsn, None, kw.get("notifier"), kw.get("now"))
        return res
    return gated_sync_workbook_object(wb, farm_code, dsn, **kw)
