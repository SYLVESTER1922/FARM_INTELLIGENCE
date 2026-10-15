"""The scope resolver is pure code, so every rule is tested exactly: periods, the five precedence rules, snapshots, domains,
aggregation and grain, and the things it must refuse to guess. No database, no LLM."""

import datetime as dt

import pytest

from registry import REGISTRY
from resolver import all_time_scope, resolve
from resolver.lexicon import domain_words_in
from resolver.periods import extract_periods, fmt_range, harare_today

D = dt.date
TODAY = D(2026, 10, 15)                       # a Thursday
AUG = (D(2026, 8, 1), D(2026, 8, 31))
FEED, HEADCOUNT, RECEIVABLES = REGISTRY["feed_consumed_cost"], REGISTRY["active_headcount"], REGISTRY["receivables"]


def res(q, metric=FEED, **kw):
    return resolve(q, metric, today=TODAY, **kw)


def span(r):
    return r.scope.start, r.scope.end


# ---------------------------------------------------------------------------------- relative and explicit periods
@pytest.mark.parametrize("phrase,start,end", [
    ("last month", D(2026, 9, 1), D(2026, 9, 30)),
    ("this month", D(2026, 10, 1), D(2026, 10, 31)),
    ("last week", D(2026, 10, 5), D(2026, 10, 11)),             # the previous Monday to Sunday
    ("this week", D(2026, 10, 12), D(2026, 10, 18)),
    ("last quarter", D(2026, 7, 1), D(2026, 9, 30)),
    ("this quarter", D(2026, 10, 1), D(2026, 12, 31)),
    ("this year", D(2026, 1, 1), D(2026, 12, 31)),
    ("last year", D(2025, 1, 1), D(2025, 12, 31)),
    ("year to date", D(2026, 1, 1), TODAY),
    ("ytd", D(2026, 1, 1), TODAY),
    ("yesterday", D(2026, 10, 14), D(2026, 10, 14)),
    ("in the last 30 days", D(2026, 9, 16), TODAY),
    ("over the past 7 days", D(2026, 10, 9), TODAY),
    ("in the last 2 weeks", D(2026, 10, 2), TODAY),
    ("in the last 3 months", D(2026, 7, 16), TODAY),
    ("in August 2026", D(2026, 8, 1), D(2026, 8, 31)),
    ("in aug 2026", D(2026, 8, 1), D(2026, 8, 31)),
    ("in agust 2026", D(2026, 8, 1), D(2026, 8, 31)),           # a typo next to a year still resolves
    ("in February 2024", D(2024, 2, 1), D(2024, 2, 29)),        # leap year
    ("Q2 2026", D(2026, 4, 1), D(2026, 6, 30)),
    ("q4 2025", D(2025, 10, 1), D(2025, 12, 31)),
    ("in 2026", D(2026, 1, 1), D(2026, 12, 31)),
    ("2026-08", D(2026, 8, 1), D(2026, 8, 31)),
    ("since March 2026", D(2026, 3, 1), TODAY),
    ("since 2025", D(2025, 1, 1), TODAY),
    ("from January 2026 to March 2026", D(2026, 1, 1), D(2026, 3, 31)),
    ("between March and May 2026", D(2026, 3, 1), D(2026, 5, 31)),
    ("from November to February 2026", D(2025, 11, 1), D(2026, 2, 28)),
])
def test_period_phrases(phrase, start, end):
    r = res(f"What was our feed cost {phrase}?")
    assert r.ok and span(r) == (start, end) and r.period_source == "question", r.unresolved


def test_last_month_in_january_is_december_of_the_previous_year():
    r = resolve("feed cost last month", FEED, today=D(2027, 1, 20))
    assert span(r) == (D(2026, 12, 1), D(2026, 12, 31))


def test_the_calendar_date_not_the_data_date_anchors_relative_periods():
    """Decision D2: today is 2026-10-15 even though the data stops at 2026-09-15."""
    assert span(res("feed cost this month")) == (D(2026, 10, 1), D(2026, 10, 31))


def test_harare_today_uses_the_farm_timezone():
    late_utc = dt.datetime(2026, 10, 14, 23, 30, tzinfo=dt.timezone.utc)      # already the 15th in Harare (UTC+2)
    assert harare_today(late_utc) == D(2026, 10, 15)


def test_period_labels():
    assert res("feed cost last month").period_label == "last month (September 2026)"
    assert res("feed cost in March 2026").period_label == "March 2026"
    assert res("feed cost last week").period_label == "last week (5–11 Oct 2026)"
    assert fmt_range(*AUG) == "1–31 Aug 2026"
    assert fmt_range(D(2026, 8, 1), D(2026, 10, 15)) == "1 Aug 2026 – 15 Oct 2026"


# ---------------------------------------------------------------------------------- the five precedence rules
def test_rule_1_a_named_period_wins_over_the_filter():
    r = res("What was our feed cost in March 2026?", dashboard_filter=AUG)
    assert (r.period_source, span(r), r.filter_applied) == ("question", (D(2026, 3, 1), D(2026, 3, 31)), False)


@pytest.mark.parametrize("q", ["What's our feed cost all time?", "What's our total feed cost overall?",
                               "What were our feed costs ever?", "feed cost since we started", "feed cost all-time",
                               "lifetime feed cost"])
def test_rule_2_explicit_scope_words_override_the_filter(q):
    r = res(q, dashboard_filter=AUG)
    assert (r.period_source, r.all_time_reason, span(r), r.filter_applied) == ("all_time", "explicit_words", (None, None), False)


def test_rule_3_no_period_and_a_filter_applies_the_filter_and_offers_the_hint():
    r = res("What's our total feed cost?", dashboard_filter=AUG)
    assert (r.period_source, span(r), r.filter_applied, r.offer_all_time_hint) == ("filter", AUG, True, True)
    assert r.period_label == "1–31 Aug 2026 (dashboard date filter)"


def test_rule_4_no_period_and_no_filter_is_all_recorded_time():
    r = res("What's our total feed cost?")
    assert (r.period_source, r.all_time_reason, span(r), r.offer_all_time_hint) == ("all_time", "no_period", (None, None), False)


def test_rule_5_snapshot_questions_ignore_the_filter():
    r = res("How many pigs do we have?", HEADCOUNT, dashboard_filter=AUG)
    assert (r.period_source, r.scope.as_of, span(r), r.filter_applied) == ("snapshot", None, (None, None), False)


def test_a_snapshot_with_a_named_past_period_is_as_of_the_end_of_it():
    r = res("How many pigs did we have in March 2026?", HEADCOUNT)
    assert (r.period_source, r.scope.as_of) == ("question", D(2026, 3, 31))


def test_a_snapshot_never_looks_into_the_future():
    assert res("How many pigs this year?", HEADCOUNT).scope.as_of == TODAY


def test_today_and_now_do_not_turn_a_snapshot_into_a_range():
    r = res("How many pigs do we have today?", HEADCOUNT)
    assert r.ok and r.period_source == "snapshot" and span(r) == (None, None)


def test_a_balance_ignores_the_filter_like_a_snapshot():
    r = res("Who is owing us?", RECEIVABLES, dashboard_filter=AUG)
    assert (r.period_source, span(r)) == ("snapshot", (None, None))
    assert span(res("Who owed us money in March 2026?", RECEIVABLES, dashboard_filter=AUG)) == (D(2026, 3, 1), D(2026, 3, 31))


def test_weather_with_no_period_is_the_latest_day_and_with_a_period_a_range():
    weather = REGISTRY["weather"]
    assert res("What's the weather like today?", weather, dashboard_filter=AUG).period_source == "snapshot"
    assert span(res("How much rain in January 2026?", weather)) == (D(2026, 1, 1), D(2026, 1, 31))


def test_metrics_with_no_period_say_so_for_a_past_period():
    r = res("How many batches did we have in March 2026?", REGISTRY["batch_count"])
    assert r.unresolved.code == "period_not_supported"
    assert res("How many batches do we have?", REGISTRY["batch_count"]).ok


def test_all_time_scope_removes_the_period():
    s = res("feed cost", dashboard_filter=AUG).scope
    assert (all_time_scope(s).start, all_time_scope(s).end, all_time_scope(s).period_source) == (None, None, "all_time")


# ---------------------------------------------------------------------------------- refuse to guess
def test_a_month_without_a_year_is_a_question_not_a_guess():
    r = res("How many chickens died in march?", REGISTRY["mortality"])
    assert r.unresolved.code == "month_without_year" and "Which year" in r.unresolved.message


def test_may_the_verb_is_not_a_month():
    assert res("how may I see the feed cost").ok


@pytest.mark.parametrize("q", ["feed cost last fortnight", "feed cost this season", "feed cost recently", "feed cost last friday"])
def test_time_words_it_cannot_resolve_are_named(q):
    r = res(q)
    assert r.unresolved.code == "unsupported_period" and "I can't work out" in r.unresolved.message


def test_two_periods_are_not_silently_merged():
    assert res("feed cost in March 2026 and April 2026").unresolved.code == "multiple_periods"
    assert res("feed cost in March and April 2026").unresolved.code == "multiple_periods"


# ---------------------------------------------------------------------------------- domains
@pytest.mark.parametrize("q,domains", [
    ("How many pigs do we have?", ("piggery",)), ("chickens", ("poultry",)), ("our broilers", ("poultry",)),
    ("the piggery", ("piggery",)), ("pigs and chickens", ("piggery", "poultry")), ("the maize crop", ("crops",)),
    ("how many pigss do we hav", ("piggery",)), ("chikens", ("poultry",)), ("poultery feed", ("poultry",)),
    ("PIG-B04 weight", ()),                                                     # a batch code is not the word 'pigs'
    ("BRO-P03 deaths", ()), ("feed cost", ()), ("shared costs", ("shared",)),
])
def test_domain_lexicon(q, domains):
    assert domain_words_in(q)[0] == domains


def test_an_unspecified_domain_defaults_to_all_and_says_so():
    r = res("What's our feed cost?")
    assert (r.scope.domains, r.domain_source) == (None, "default_all")


def test_naming_everything_the_metric_covers_is_the_same_as_naming_nothing():
    assert res("feed cost for pigs and chickens").scope.domains is None
    assert res("feed cost for pigs").scope.domains == ("piggery",)


def test_a_single_module_farm_resolves_to_its_one_domain():
    r = res("What's our feed cost?", modules={"piggery": True, "poultry": False, "crops": False})
    assert (r.scope.domains, r.domain_source) == (("piggery",), "single_module")


def test_a_domain_whose_module_is_off_is_named_not_silently_dropped():
    r = res("feed cost for chickens", modules={"piggery": True, "poultry": False, "crops": True})
    assert r.unresolved.code == "module_off" and "poultry module is turned off" in r.unresolved.message


def test_a_domain_the_metric_does_not_cover_is_named():
    r = res("feed cost for crops")
    assert r.unresolved.code == "domain_unsupported" and "crops" in r.unresolved.message
    assert res("feed cost for pigs and crops").unresolved.code == "domain_unsupported"      # no quiet drop


def test_shared_is_a_domain_for_expenses():
    assert res("shared expenses", REGISTRY["expenses"]).scope.domains == ("shared",)


def test_batch_code_is_picked_up_in_either_case():
    assert res("average weight of batch pig-b04", REGISTRY["weight"]).scope.batch_code == "PIG-B04"
    assert res("deaths in BRO-P02", REGISTRY["mortality"]).scope.batch_code == "BRO-P02"


# ---------------------------------------------------------------------------------- aggregation and grain
def test_average_weekly_is_an_aggregation():
    r = res("What's the average weekly feed cost?")
    assert (r.scope.aggregation, r.scope.grain) == ("avg_per_week", None)


def test_month_by_month_is_a_grain():
    assert res("feed cost by month").scope.grain == "month"
    assert res("monthly feed cost").scope.grain == "month"


@pytest.mark.parametrize("q", ["average monthly feed cost", "average feed cost per day", "feed cost per week", "daily feed cost"])
def test_aggregations_it_cannot_do_are_named(q):
    r = res(q)
    assert r.unresolved is not None and r.unresolved.code == "unsupported_aggregation", q


def test_a_metric_that_has_no_average_says_so():
    assert res("average weekly expenses", REGISTRY["expenses"]).unresolved.code == "unsupported_aggregation"


def test_average_litter_size_and_per_animal_are_not_aggregations():
    assert res("What's the average litter size?", REGISTRY["breeding"]).ok
    assert res("What does feed cost us per animal?", REGISTRY["feed_cost_per_animal"]).ok


def test_daily_log_is_not_a_request_to_split_by_day():
    assert res("feed recorded in the daily log").ok


# ---------------------------------------------------------------------------------- last week and last N days
def test_last_week_is_the_previous_full_monday_to_sunday_week():
    for today in (D(2026, 10, 12), D(2026, 10, 15), D(2026, 10, 18)):          # a Monday, a Thursday, a Sunday
        r = resolve("feed cost last week", FEED, today=today)
        assert span(r) == (D(2026, 10, 5), D(2026, 10, 11)), today
    assert resolve("feed cost last week", FEED, today=D(2026, 10, 19)).scope.start == D(2026, 10, 12)   # next Monday rolls over


def test_this_week_is_the_current_monday_to_sunday_week():
    assert span(res("feed cost this week")) == (D(2026, 10, 12), D(2026, 10, 18))


@pytest.mark.parametrize("week_start,name,last_start,last_end", [
    (0, "monday", D(2026, 10, 5), D(2026, 10, 11)),
    (6, "sunday", D(2026, 10, 4), D(2026, 10, 10)),
    (5, "saturday", D(2026, 10, 3), D(2026, 10, 9)),
    (2, "wednesday", D(2026, 10, 7), D(2026, 10, 13)),
])
def test_the_week_start_is_a_per_farm_setting(week_start, name, last_start, last_end):
    r = resolve("feed cost last week", FEED, today=TODAY, week_start=week_start)
    assert span(r) == (last_start, last_end) and (r.scope.end - r.scope.start).days == 6, name


def test_when_today_is_the_week_start_last_week_is_the_week_just_ended():
    # Sunday 18 Oct on a Sunday-start farm: a new week begins today, so last week is the one that ended yesterday
    assert span(resolve("feed cost last week", FEED, today=D(2026, 10, 18), week_start=6)) == (D(2026, 10, 11), D(2026, 10, 17))
    assert span(resolve("feed cost this week", FEED, today=D(2026, 10, 18), week_start=6)) == (D(2026, 10, 18), D(2026, 10, 24))


def test_last_7_days_is_a_rolling_window_ending_today_not_last_week():
    r = res("feed cost in the last 7 days")
    assert span(r) == (D(2026, 10, 9), TODAY) and r.period_label == "last 7 days (9–15 Oct 2026)"
    assert (r.scope.end - r.scope.start).days == 6                          # seven days, today included
    assert span(res("feed cost last week")) != span(r)


def test_last_7_days_and_last_week_agree_only_when_today_is_the_week_end():
    sunday = D(2026, 10, 18)
    assert span(resolve("feed cost last 7 days", FEED, today=sunday)) == (D(2026, 10, 12), sunday)
    assert span(resolve("feed cost last week", FEED, today=sunday)) == (D(2026, 10, 5), D(2026, 10, 11))


# ---------------------------------------------------------------------------------- same day last month / last year
@pytest.mark.parametrize("today,phrase,expected", [
    (D(2026, 10, 15), "same day last month", D(2026, 9, 15)),
    (D(2026, 10, 15), "the same day last year", D(2025, 10, 15)),
    (D(2026, 10, 15), "this day last month", D(2026, 9, 15)),
    (D(2026, 10, 15), "this day last year", D(2025, 10, 15)),
    (D(2026, 10, 15), "a month ago today", D(2026, 9, 15)),
    (D(2026, 10, 15), "a year ago today", D(2025, 10, 15)),
    (D(2026, 10, 15), "one year ago to the day", D(2025, 10, 15)),
    (D(2026, 1, 15), "same day last month", D(2025, 12, 15)),                  # across a year boundary
    # clamping: the day does not exist in the earlier month, so it is that month's last day
    (D(2026, 3, 31), "same day last month", D(2026, 2, 28)),
    (D(2026, 5, 31), "same day last month", D(2026, 4, 30)),
    (D(2026, 3, 30), "same day last month", D(2026, 2, 28)),
    (D(2026, 3, 29), "same day last month", D(2026, 2, 28)),
    (D(2024, 3, 31), "same day last month", D(2024, 2, 29)),                   # leap year: Feb has 29
    (D(2024, 3, 30), "same day last month", D(2024, 2, 29)),
    (D(2026, 8, 31), "same day last month", D(2026, 7, 31)),                   # no clamp needed
    (D(2026, 12, 31), "same day last month", D(2026, 11, 30)),
    (D(2026, 1, 31), "same day last month", D(2025, 12, 31)),
    # leap days
    (D(2028, 2, 29), "same day last year", D(2027, 2, 28)),                    # 29 Feb falls back to 28 Feb
    (D(2024, 2, 29), "same day last year", D(2023, 2, 28)),
    (D(2029, 2, 28), "same day last year", D(2028, 2, 28)),                    # 28 Feb, no fallback needed
    (D(2028, 3, 1), "same day last year", D(2027, 3, 1)),
    (D(2025, 2, 28), "same day last year", D(2024, 2, 28)),                    # last year was a leap year: still the 28th
    (D(2028, 2, 29), "same day last month", D(2028, 1, 29)),
])
def test_same_day_last_month_or_year_is_one_clamped_date(today, phrase, expected):
    r = resolve(f"What was the feed cost on {phrase}?", FEED, today=today)
    assert r.ok and span(r) == (expected, expected) and r.period_source == "question"


def test_the_resolved_date_is_echoed_in_the_label():
    r = res("feed cost on the same day last month")
    assert r.period_label == "same day last month (15 Sep 2026)"
    assert resolve("feed cost same day last month", FEED, today=D(2026, 3, 31)).period_label == "same day last month (28 Feb 2026)"
    assert resolve("feed cost same day last year", FEED, today=D(2028, 2, 29)).period_label == "same day last year (28 Feb 2027)"


def test_same_day_last_month_is_not_read_as_all_of_last_month():
    """The defect before this fix: it silently resolved to the whole of September (and last year to all of 2025)."""
    assert span(res("feed cost same day last month")) != (D(2026, 9, 1), D(2026, 9, 30))
    assert span(res("feed cost same day last year")) != (D(2025, 1, 1), D(2025, 12, 31))


def test_same_day_for_a_snapshot_is_the_as_of_date():
    r = res("how many pigs did we have the same day last month", HEADCOUNT)
    assert (r.scope.as_of, r.period_source, span(r)) == (D(2026, 9, 15), "question", (None, None))


def test_a_plain_last_month_still_means_the_whole_month():
    assert span(res("feed cost last month")) == (D(2026, 9, 1), D(2026, 9, 30))


# ---------------------------------------------------------------------------------- comparisons of periods
@pytest.mark.parametrize("q", [
    "feed cost this month vs last month", "feed cost compared to last month", "same day last month compared to today",
    "How does this month's feed cost compare to last month?", "was feed cost higher than last month",
    "compare March 2026 and April 2026", "feed cost March 2026 versus April 2026", "feed cost against last year",
    "feed cost compared with the same day last month", "feed cost up from last month", "what is the change since last month",
    "how did feed cost this year compare to last year",
])
def test_comparing_periods_is_a_named_refusal(q):
    r = res(q)
    assert r.unresolved is not None and r.unresolved.code == "comparison_not_supported", q
    assert "separately" in r.unresolved.message


@pytest.mark.parametrize("q", [
    "Compare piggery and poultry costs", "Compare piggery and poultry costs this year",
    "feed cost for pigs vs chickens in March 2026", "pigs versus chickens feed cost",
    "how does feed cost split between pigs and chickens in March 2026", "which domain costs more, piggery or poultry",
    "more than 5 pigs", "feed cost last month",
])
def test_comparing_domains_or_ordinary_words_is_not_a_period_comparison(q):
    r = res(q)
    assert r.unresolved is None or r.unresolved.code != "comparison_not_supported", q


def test_a_comparison_of_a_snapshot_with_a_past_date_is_also_refused():
    r = res("how many pigs do we have compared to the same day last month", HEADCOUNT)
    assert r.unresolved.code == "comparison_not_supported"
