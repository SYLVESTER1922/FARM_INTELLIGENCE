"""
Rebuilds the eval fixture database from the real generated workbook via the
production sync (so the eval exercises the real schema). Read-only with
respect to the workbook and gen_scripts/. Guarded: see evals/guard.py.

    DATABASE_URL=postgresql://$USER@localhost/farm_intelligence_test \
        python -m evals.build_fixture
"""

from pathlib import Path

from evals.guard import checked_database_url, connect_guarded
from sync.engine import sync_workbook_to_supabase

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKBOOK = REPO_ROOT / "Netrisyl_Farm_Intelligence_Workbook.xlsx"
FARM_CODE = "NIS-001"


def build(verbose: bool = True):
    url = checked_database_url()
    conn = connect_guarded()  # second, live-connection check
    conn.execute("DROP SCHEMA public CASCADE")
    conn.execute("CREATE SCHEMA public")
    conn.close()

    report = sync_workbook_to_supabase(str(WORKBOOK), farm_code=FARM_CODE, dsn=url)
    if report.errors:
        raise SystemExit(f"fixture sync reported errors: {report.errors[:5]}")
    if verbose:
        total = sum(report.rows_written.values())
        print(f"fixture built from {WORKBOOK.name}: {total} rows across "
              f"{len(report.rows_written)} tables")
    return report


if __name__ == "__main__":
    build()
