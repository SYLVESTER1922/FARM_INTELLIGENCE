"""
Direct unit tests for chatbot/matcher.py's relative-period resolution -
a real bug found in production: tier-2's LLM-extracted period for "how
does feed cost split... this month" came back as "October 2023," the
model's own training-era guess at "now," not this project's real
latest-data-date concept. extract_relative_period/extract_period's
anchor_date parameter exist to make relative-period resolution
deterministic, the same "the LLM never computes a relative date itself"
principle already applied to q_mortality_rate's symbolic period enum.
"""

import datetime

from chatbot.matcher import extract_period, extract_relative_period


def test_extract_relative_period_resolves_this_month_from_anchor_date():
    anchor = datetime.date(2026, 9, 15)

    result = extract_relative_period("feed cost this month", anchor)

    assert result == {"period_start": "2026-09-01", "period_end": "2026-10-01"}


def test_extract_relative_period_resolves_last_month_from_anchor_date():
    anchor = datetime.date(2026, 9, 15)

    result = extract_relative_period("feed cost last month", anchor)

    assert result == {"period_start": "2026-08-01", "period_end": "2026-09-01"}


def test_extract_relative_period_last_month_handles_january_year_rollover():
    anchor = datetime.date(2026, 1, 10)

    result = extract_relative_period("feed cost last month", anchor)

    assert result == {"period_start": "2025-12-01", "period_end": "2026-01-01"}


def test_extract_relative_period_returns_none_without_a_relative_phrase():
    anchor = datetime.date(2026, 9, 15)

    assert extract_relative_period("feed cost split", anchor) is None


def test_extract_period_prefers_explicit_month_year_over_anchor_date():
    anchor = datetime.date(2026, 9, 15)

    result = extract_period("feed cost in January 2026", anchor_date=anchor)

    assert result == {"period_start": "2026-01-01", "period_end": "2026-02-01"}


def test_extract_period_falls_back_to_relative_when_no_explicit_month():
    anchor = datetime.date(2026, 9, 15)

    result = extract_period("feed cost this month", anchor_date=anchor)

    assert result == {"period_start": "2026-09-01", "period_end": "2026-10-01"}


def test_extract_period_returns_none_without_anchor_date_or_explicit_month():
    # backward-compatible default: no anchor_date given, "this month" is
    # unresolvable, same as before this fix - unchanged behavior for any
    # caller that doesn't pass an anchor_date.
    assert extract_period("feed cost this month") is None
