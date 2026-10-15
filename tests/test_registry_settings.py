"""Per-farm settings: validated reads and writes, defaults, and the week start feeding the resolver."""

import datetime as dt

import pytest

from registry.migrations import migrate
from registry.settings import DEFAULTS, get_settings, set_setting, week_start_index
from resolver import resolve
from registry import REGISTRY


@pytest.fixture
def conn(db_conn):
    migrate(db_conn)
    return db_conn


def test_defaults_apply_when_nothing_is_stored(conn):
    assert get_settings(conn, "NIS-001") == DEFAULTS
    assert week_start_index(get_settings(conn, "NIS-001")) == 0               # Monday


def test_a_stored_week_start_changes_what_last_week_means(conn):
    set_setting(conn, "NIS-001", "week_start", "Sunday")                      # case-insensitive, stored lower-case
    settings = get_settings(conn, "NIS-001")
    assert settings["week_start"] == "sunday"
    r = resolve("feed cost last week", REGISTRY["feed_consumed_cost"], today=dt.date(2026, 10, 15),
                week_start=week_start_index(settings))
    assert (r.scope.start, r.scope.end) == (dt.date(2026, 10, 4), dt.date(2026, 10, 10))


def test_settings_are_per_farm(conn):
    set_setting(conn, "NIS-001", "week_start", "saturday")
    assert get_settings(conn, "OTHER-9")["week_start"] == "monday"


def test_setting_twice_updates_not_duplicates(conn):
    set_setting(conn, "NIS-001", "week_start", "sunday")
    set_setting(conn, "NIS-001", "week_start", "monday")
    assert conn.execute("SELECT COUNT(*) FROM farm_settings").fetchone()[0] == 1
    assert get_settings(conn, "NIS-001")["week_start"] == "monday"


@pytest.mark.parametrize("key,value", [("week_start", "funday"), ("week_start", ""), ("feed_reconciliation_tolerance_pct", "0"),
                                       ("feed_reconciliation_tolerance_pct", "abc"), ("feed_reconciliation_tolerance_pct", "150"),
                                       ("nonsense", "x")])
def test_an_invalid_setting_is_refused_on_write(conn, key, value):
    with pytest.raises(ValueError):
        set_setting(conn, "NIS-001", key, value)


def test_a_bad_stored_value_falls_back_to_the_default_instead_of_breaking_answers(conn):
    conn.execute("INSERT INTO farm_settings (farm_code, key, value) VALUES ('NIS-001', 'week_start', 'funday')")
    assert get_settings(conn, "NIS-001")["week_start"] == "monday"


def test_the_reconciliation_tolerance_is_a_per_farm_setting_defaulting_to_5(conn):
    assert get_settings(conn, "NIS-001")["feed_reconciliation_tolerance_pct"] == "5"
    set_setting(conn, "NIS-001", "feed_reconciliation_tolerance_pct", "12.5")
    assert get_settings(conn, "NIS-001")["feed_reconciliation_tolerance_pct"] == "12.5"


def test_the_weekday_lists_in_the_registry_and_the_resolver_agree():
    from registry.core import WEEKDAYS as registry_days
    from resolver.periods import WEEKDAYS as resolver_days
    assert registry_days == resolver_days
