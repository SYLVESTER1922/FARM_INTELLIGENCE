"""What the app shows because of the gates: the banner, the caveats on affected metrics, and the data-quality report."""

import datetime as dt

from gates import STALE_DAYS, WARN
from render import format as fmt


def _ready(conn):
    return conn.execute("SELECT to_regclass('data_snapshot') IS NOT NULL AND to_regclass('gate_firings') IS NOT NULL").fetchone()[0]


def banner(conn, farm_code, now=None):
    """None when nothing is held back. When a newer upload is held back: "Data last verified <date>. A newer upload is being reviewed.";
    more prominent once the verified snapshot is older than STALE_DAYS."""
    if not _ready(conn):
        return None
    row = conn.execute("SELECT verified_at, held_back FROM data_snapshot WHERE farm_code = %s", (farm_code,)).fetchone()
    if row is None or not row[1]:
        return None
    verified, now = row[0], now or dt.datetime.now(dt.timezone.utc)
    when = fmt.date(verified.date().isoformat())
    age = (now - verified).days
    if age > STALE_DAYS:
        return f"⚠️ Data last verified {when} ({age} days ago). A newer upload is still being reviewed, so these figures may be out of date."
    return f"Data last verified {when}. A newer upload is being reviewed."


def caveats(conn, farm_code, metric_id, scope=None):
    """One line per live, unacknowledged warning that affects this metric (and, if the warning is about a period, overlaps the scope's period)."""
    from gates.checks import metrics_reading
    from gates.store import open_warnings
    out = []
    if not _ready(conn):
        return out
    start, end = getattr(scope, "start", None), getattr(scope, "end", None)
    for _id, gate, table, message, rows, p0, p1, key in open_warnings(conn, farm_code):
        if metric_id not in metrics_reading(table):
            continue
        if p0 and start and end and (p1 < start or p0 > end):
            continue
        out.append(f"Note: {message} (data-quality warning, not yet reviewed)")
    return out


def data_quality_report(conn, farm_code):
    """Plain-text report: the last run, live warnings, acknowledged ones, report-only items and any held-back upload."""
    if not _ready(conn):
        return "No data-quality log yet."
    lines = []
    run = conn.execute("SELECT id, finished_at, outcome FROM sync_runs WHERE farm_code = %s ORDER BY id DESC LIMIT 1", (farm_code,)).fetchone()
    lines.append("Last upload: " + (f"#{run[0]} {run[2]} at {run[1]:%Y-%m-%d %H:%M}" if run else "none"))
    for status, heading in (("open", "Warnings (live, not yet reviewed)"), ("acknowledged", "Acknowledged warnings")):
        rows = conn.execute("SELECT id, message FROM gate_firings WHERE farm_code=%s AND severity=%s AND status=%s ORDER BY id", (farm_code, WARN, status)).fetchall()
        lines += [f"{heading}: {len(rows)}"] + [f"  [{i}] {m}" for i, m in rows]
    rows = conn.execute("""SELECT message FROM gate_firings WHERE farm_code=%s AND severity='report' AND run_id = (SELECT MAX(run_id) FROM gate_firings WHERE farm_code=%s)
                           ORDER BY id""", (farm_code, farm_code)).fetchall()
    lines += [f"Report only (no banner, no caveat): {len(rows)}"] + [f"  {m[0]}" for m in rows]
    held = conn.execute("SELECT held_back, held_since FROM data_snapshot WHERE farm_code = %s", (farm_code,)).fetchone()
    if held and held[0]:
        lines.append(f"A newer upload is held back since {held[1]:%Y-%m-%d}.")
    return "\n".join(lines)
