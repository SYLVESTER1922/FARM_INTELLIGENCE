"""
Step 7 measurements, no model calls: (1) the gates' false-positive count on the clean workbook, and (2) for every dirty fixture, whether the gates
caught it and what the answers to the gold-spec dev questions look like afterwards. An answer is

    unchanged          the same figures as on the clean workbook (a block leaves the last good data live)
    changed, flagged   different figures, but a banner or a caveat on that metric and period says so
    changed, SILENT    different figures with nothing saying so: the wrong answers this step must drive to zero

    DATABASE_URL=postgresql://$USER@localhost/farm_intelligence_test python -m evals.dirty_report
"""

import collections
import json

from evals.case_specs import SPECS
from evals.cases_dev import CASES
from evals.guard import checked_database_url, connect_guarded
from gates import status
from gates.fixtures import DIRTY, WORKBOOK, dirty
from gates.run import gated_sync_workbook, gated_sync_workbook_object
from registry import compute
from registry.migrations import migrate

FARM = "NIS-001"
ZT = {c.id for c in CASES if c.zt}


def _fingerprint(result):
    return json.dumps([result.status, result.figures, result.rows], default=str, sort_keys=True)


def _answers(conn):
    return {cid: _fingerprint(compute(metric, conn, scope)) for cid, (metric, scope) in sorted(SPECS.items())}


def _fresh(url):
    conn = connect_guarded()
    conn.execute("DROP SCHEMA public CASCADE")
    conn.execute("CREATE SCHEMA public")
    migrate(conn)
    return conn


def main():
    url = checked_database_url()
    noop = lambda s, b: None
    conn = _fresh(url)
    clean = gated_sync_workbook(str(WORKBOOK), FARM, url, notifier=noop)
    counts = collections.Counter(f.severity for f in clean.firings)
    print(f"CLEAN WORKBOOK: outcome {clean.outcome}; block {counts['block']}, warn {counts['warn']}, report-only {counts['report']}  "
          f"(gate false positives that block or caveat: {counts['block'] + counts['warn']})")
    baseline = _answers(conn)
    print(f"gold-spec dev questions examined per fixture: {len(baseline)} ({sum(1 for c in baseline if c in ZT)} zero-tolerance)\n")
    print(f"{'fixture':24} {'expected gate':22} {'outcome':21} caught  unchanged  flagged  SILENT (zero-tolerance silent)")
    tot = collections.Counter()
    for name, d in DIRTY.items():
        conn = _fresh(url)
        gated_sync_workbook(str(WORKBOOK), FARM, url, notifier=noop)                      # the last good snapshot
        r = gated_sync_workbook_object(dirty(name), FARM, url, notifier=noop)
        fired = {f.gate for f in r.firings}
        caught = (d.gate in fired) if d.gate else not any(f.severity != "report" for f in r.firings)
        banner = status.banner(conn, FARM)
        c = collections.Counter()
        for cid, fp in _answers(conn).items():
            if fp == baseline[cid]:
                c["unchanged"] += 1
                continue
            metric, scope = SPECS[cid]
            flagged = bool(banner or status.caveats(conn, FARM, metric, scope))
            c["flagged" if flagged else "silent"] += 1
            if not flagged and cid in ZT:
                c["silent_zt"] += 1
        tot.update(c)
        print(f"{name:24} {d.gate or '-':22} {r.outcome:21} {'yes' if caught else 'NO ':6} {c['unchanged']:9} {c['flagged']:8} {c['silent']:6} ({c['silent_zt']})")
    n = tot["unchanged"] + tot["flagged"] + tot["silent"]
    print(f"\nacross {len(DIRTY)} fixtures x {len(baseline)} questions = {n} answers: silent-wrong {tot['silent']} ({100 * tot['silent'] / n:.2f}%), "
          f"of which zero-tolerance {tot['silent_zt']}")


if __name__ == "__main__":
    main()
