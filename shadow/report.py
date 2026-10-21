"""The disagreement report and the labels a person gives. Labels: old_right, new_right, both_right, both_wrong, unclear. A label other than
`unclear` settles a row; `new_wrong` below counts rows where the NEW engine was wrong (old_right or both_wrong), the evidence step 9 needs."""

import csv

from shadow.compare import CLASSES

LABELS = ("old_right", "new_right", "both_right", "both_wrong", "unclear")
NEW_WRONG = ("old_right", "both_wrong")


def label_row(conn, shadow_id, label, reviewer, note="", *, now=None):
    if label not in LABELS:
        raise ValueError(f"label must be one of {LABELS}")
    if not str(reviewer or "").strip():
        raise ValueError("a label needs a reviewer")
    n = conn.execute("""UPDATE shadow_log SET label = %s, label_note = %s, labelled_by = %s, labelled_at = COALESCE(%s, now())
                        WHERE id = %s RETURNING id""", (label, note, reviewer.strip(), now, shadow_id)).fetchone()
    if n is None:
        raise ValueError(f"no shadow row {shadow_id}")


def summary(conn, farm_code, since=None):
    rows = conn.execute("SELECT classification, label, new_metric FROM shadow_log WHERE farm_code = %s AND (%s::timestamptz IS NULL OR logged_at >= %s)",
                        (farm_code, since, since)).fetchall()
    by_class = {c: 0 for c in CLASSES}
    labelled = {l: 0 for l in LABELS}
    per_metric = {}
    for cls, label, metric in rows:
        by_class[cls] = by_class.get(cls, 0) + 1
        if label:
            labelled[label] += 1
        m = per_metric.setdefault(metric or "(no metric)", {"n": 0, "disagree": 0, "new_wrong": 0})
        m["n"] += 1
        m["disagree"] += cls == "disagree"
        m["new_wrong"] += label in NEW_WRONG
    total = len(rows)
    to_label = conn.execute("SELECT COUNT(*) FROM shadow_log WHERE farm_code = %s AND needs_label AND label IS NULL", (farm_code,)).fetchone()[0]
    return {"total": total, "by_class": by_class, "labelled": labelled, "to_label": to_label, "per_metric": per_metric,
            "new_wrong": sum(labelled[l] for l in NEW_WRONG)}


def text_report(conn, farm_code, since=None, show=15):
    s = summary(conn, farm_code, since)
    out = [f"Shadow runs: {s['total']}   waiting for a label: {s['to_label']}   labelled new engine wrong: {s['new_wrong']}"]
    out += [f"  {c:13} {n}" for c, n in s["by_class"].items() if n]
    out.append("Labels: " + ", ".join(f"{k} {v}" for k, v in s["labelled"].items() if v))
    pending = conn.execute("""SELECT id, classification, question, left(old_text, 160), left(new_text, 160) FROM shadow_log
                              WHERE farm_code = %s AND needs_label AND label IS NULL ORDER BY id LIMIT %s""", (farm_code, show)).fetchall()
    for i, cls, q, old, new in pending:
        out += [f"[{i}] {cls}: {q}", f"     old: {old!r}", f"     new: {new!r}"]
    return "\n".join(out)


def export_label_sheet(conn, farm_code, path):
    """A CSV of the rows waiting for a label, with blank label and note columns for a person to fill in."""
    rows = conn.execute("""SELECT id, classification, question, old_text, new_text, new_metric, new_scope::text FROM shadow_log
                           WHERE farm_code = %s AND needs_label AND label IS NULL ORDER BY id""", (farm_code,)).fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["shadow_id", "classification", "question", "old_answer", "new_answer", "new_metric", "new_scope", f"label ({'/'.join(LABELS)})", "note"])
        for r in rows:
            w.writerow([*r, "", ""])
    return len(rows)
