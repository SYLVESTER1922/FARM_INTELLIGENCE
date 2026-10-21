"""
Sync gates and data-quality (plan section 9, decision D8). A sync first loads a staging copy; gates run on it; the live tables are replaced
only on a pass. See gates/run.py (the gated sync), gates/checks.py (the gates), gates/status.py (banner and caveats), gates/store.py
(firing, run and acknowledgement logs), gates/notify.py (email on a block) and gates/fixtures.py (deliberately dirty workbooks).
"""

BLOCK, WARN, REPORT = "block", "warn", "report"
STALE_DAYS = 7
