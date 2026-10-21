"""The parts of the sync gates that need no database."""

import datetime as dt

import pytest

from gates import BLOCK, WARN, checks
from gates.checks import ISO_CURRENCIES, Firing, _foreign_markers, _months, metrics_reading
from gates.notify import block_email, notify_block


def test_the_workbooks_own_currencies_are_recognised():
    assert {"USD", "ZWG"} <= ISO_CURRENCIES and "DOLLARZ" not in ISO_CURRENCIES and "ZWL" not in ISO_CURRENCIES    # ZWL was retired


@pytest.mark.parametrize("text,home,found", [
    ("Maize seed ZWL 500", "USD", {"ZWL"}), ("paid in ZiG", "USD", {"ZWG"}), ("paid in ZiG", "ZWG", set()), ("R 450 diesel", "USD", {"ZAR"}),
    ("USD 40 vet", "ZWG", {"USD"}), ("USD 40 vet", "USD", set()), ("bought in £30", "USD", {"GBP"}),
    ("TOP DRESSING 50 bags", "USD", set()), ("Stock ALL", "USD", set()), ("Feed 20kg", "USD", set()), ("Pig grower 50kg", "USD", set()),
    ("Broiler starter, 10 bags", "USD", set())])
def test_foreign_currency_markers(text, home, found):
    assert _foreign_markers(text, home) == found


def test_months_walks_year_ends():
    assert list(_months(dt.date(2025, 11, 1), dt.date(2026, 2, 14))) == [dt.date(2025, 11, 1), dt.date(2025, 12, 1), dt.date(2026, 1, 1), dt.date(2026, 2, 1)]


def test_a_firing_knows_which_metrics_it_affects():
    assert {"expenses", "profit", "feed_purchases"} <= set(Firing("g", WARN, "m", "expenses").metrics)
    assert "active_headcount" not in Firing("g", WARN, "m", "expenses").metrics
    assert {"mortality", "feed_consumed_cost"} <= set(metrics_reading("pig_daily_log"))
    assert set(metrics_reading(None)) >= {"expenses", "revenue", "profit", "labour"}              # a currency problem touches every money metric
    assert Firing("feed_reconciliation", "report", "m", "pig_daily_log", metrics=()).metrics == ()  # report-only: no metric carries a caveat


def test_duplicate_keys_are_a_block_per_table():
    out = checks.duplicate_key_gate({"expenses": ["2026-05-01, piggery, Pig grower"], "revenue": []})
    assert [(f.gate, f.severity, f.table, f.rows) for f in out] == [("duplicate_primary_key", BLOCK, "expenses", 1)]


def test_the_block_email_names_each_block_and_the_banner_people_will_see():
    subject, body = block_email("NIS-001", [Firing("currency_invalid", BLOCK, "The farm currency 'X' is not a recognised ISO currency code.")])
    assert "blocked" in subject and "NIS-001" in subject and "currency 'X'" in body and "A newer upload is being reviewed" in body


def test_notify_reports_failure_instead_of_raising():
    boom = lambda subject, body: (_ for _ in ()).throw(OSError("smtp down"))
    assert notify_block("NIS-001", [Firing("g", BLOCK, "m")], notifier=boom) == (False, "OSError: smtp down")
    assert notify_block("NIS-001", [Firing("g", BLOCK, "m")], notifier=lambda s, b: None) == (True, None)
