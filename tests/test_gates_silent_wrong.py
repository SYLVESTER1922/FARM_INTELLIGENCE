"""The step 7 safety property, on the real workbook: after any dirty upload, no answer to a gold-spec dev question changes without a banner or a caveat
saying so (silent wrong answers: zero), and every dirty fixture is caught by the gate it was built to trip."""

import collections

from evals.case_specs import SPECS
from gates import status
from gates.fixtures import DIRTY, WORKBOOK, dirty
from gates.run import gated_sync_workbook, gated_sync_workbook_object
from registry import compute
from registry.migrations import migrate
from tests.conftest import TEST_DSN

import json
import psycopg

FARM = "NIS-001"


def _fp(conn):
    return {cid: json.dumps([r.status, r.figures, r.rows], default=str, sort_keys=True)
            for cid, (m, sc) in SPECS.items() for r in [compute(m, conn, sc)]}


def test_no_dirty_upload_changes_an_answer_silently():
    noop = lambda s, b: None
    conn = psycopg.connect(TEST_DSN, autocommit=True)
    try:
        conn.execute("DROP SCHEMA public CASCADE"); conn.execute("CREATE SCHEMA public"); migrate(conn)
        gated_sync_workbook(str(WORKBOOK), FARM, TEST_DSN, notifier=noop)
        baseline = _fp(conn)
        silent, missed = collections.Counter(), []
        for name, d in DIRTY.items():
            conn.execute("DROP SCHEMA public CASCADE"); conn.execute("CREATE SCHEMA public"); migrate(conn)
            gated_sync_workbook(str(WORKBOOK), FARM, TEST_DSN, notifier=noop)
            r = gated_sync_workbook_object(dirty(name), FARM, TEST_DSN, notifier=noop)
            if d.gate and d.gate not in {f.gate for f in r.firings}:
                missed.append(name)
            banner = status.banner(conn, FARM)
            for cid, fp in _fp(conn).items():
                m, sc = SPECS[cid]
                if fp != baseline[cid] and not (banner or status.caveats(conn, FARM, m, sc)):
                    silent[name] += 1
        assert not missed, missed
        assert not silent, dict(silent)
    finally:
        conn.close()
