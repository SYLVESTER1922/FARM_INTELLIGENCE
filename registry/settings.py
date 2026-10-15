"""
Per-farm settings. A small key/value table (farm_settings, created by registry/migrations.py) with validated reads and
writes, so a setting that matters for answers (which weekday a week starts on) is configuration, not a constant in code.

    week_start                        monday ... sunday   "last week" is the previous full week from this day
    feed_reconciliation_tolerance_pct a number            tolerance for the report-only feed reconciliation check
                                                          (default 5; calibrate on the first month of real data)
"""

from registry.core import WEEKDAYS

DEFAULTS = {"week_start": "monday", "feed_reconciliation_tolerance_pct": "5"}


def _valid(key, value):
    if key == "week_start":
        return str(value).lower() in WEEKDAYS
    if key == "feed_reconciliation_tolerance_pct":
        try:
            return 0 < float(value) <= 100
        except (TypeError, ValueError):
            return False
    return False


def get_settings(conn, farm_code: str) -> dict:
    """Defaults overlaid with the farm's stored values. A stored value that fails validation is ignored (the default
    is used) so a bad row can never break answering; set_setting() refuses to write one."""
    out = dict(DEFAULTS)
    for key, value in conn.execute("SELECT key, value FROM farm_settings WHERE farm_code = %s", (farm_code,)).fetchall():
        if key in DEFAULTS and _valid(key, value):
            out[key] = str(value).lower() if key == "week_start" else str(value)
    return out


def set_setting(conn, farm_code: str, key: str, value) -> None:
    if key not in DEFAULTS:
        raise ValueError(f"unknown setting {key!r}; known: {sorted(DEFAULTS)}")
    if not _valid(key, value):
        raise ValueError(f"invalid value {value!r} for {key}")
    conn.execute("""INSERT INTO farm_settings (farm_code, key, value) VALUES (%s, %s, %s)
                    ON CONFLICT (farm_code, key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()""",
                 (farm_code, key, str(value).lower() if key == "week_start" else str(value)))


def week_start_index(settings: dict) -> int:
    """0 = Monday ... 6 = Sunday, for resolver.resolve(week_start=...)."""
    return WEEKDAYS.index(settings.get("week_start", DEFAULTS["week_start"]))
