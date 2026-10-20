"""The remaining edges of the resolver and the renderer, so the Gate A audit can say both packages are fully covered by their unit tests
(line coverage, measured with `coverage run --source=resolver,render`)."""

import datetime as dt

from registry import REGISTRY
from registry.core import Result, Scope
from render import RenderContext, render
from render import format as fmt
from resolver import resolve
from resolver.lexicon import domain_words_in
from resolver.periods import extract_periods

TODAY = dt.date(2026, 10, 15)
CTX = RenderContext(currency="USD", data_through=dt.date(2026, 9, 15))


def _render(metric_id, question, figures, rows):
    res = resolve(question, REGISTRY[metric_id], today=TODAY)
    assert res.ok
    return render(res, Result(metric_id, "ok", res.scope, figures=figures, rows=rows), CTX)


def test_format_helpers_show_n_a_for_a_missing_value():
    assert fmt.money(None) == "n/a" and fmt.date(None) == "n/a"


def test_culled_sows_are_stated_as_not_counted():
    text = _render("sow_count", "how many sows", {"total": 3, "by_status": {"Open": 3}, "culled": 2}, [{"status": "Open", "count": 3}])
    assert "2 culled sows not counted." in text


def test_a_batch_without_an_fcr_says_why():
    text = _render("fcr", "feed conversion", {"best_batch": "A", "best_fcr": 1.5, "worst_batch": "B", "worst_fcr": 2.5},
                   [{"batch_code": "C", "label": "Piggery", "fcr": None, "reason": "fewer than two weight samples", "samples": 1}])
    assert "C (Piggery): not available, fewer than two weight samples (1 sample(s))" in text


def test_nothing_overdue_or_due_soon_is_stated_not_left_blank():
    text = _render("market_readiness", "which batches are ready to sell", {"overdue": 0, "due_soon": 0}, [])
    assert "No active batch is overdue or due within 30 days (overdue 0, due soon 0)." in text


def test_a_range_of_months_with_no_year_is_left_to_the_bare_month_rule():
    periods, bare = extract_periods("from march to may", TODAY, 0)
    assert periods == [] and [b.month for b in bare] == [3, 5]


def test_abbreviated_months_and_may_count_after_a_preposition():
    _, bare = extract_periods("feed cost in aug", TODAY, 0)
    assert [b.month for b in bare] == [8]
    _, bare = extract_periods("feed cost in may", TODAY, 0)
    assert [b.month for b in bare] == [5]


def test_this_month_rolls_into_the_next_year_in_december():
    res = resolve("feed cost this month", REGISTRY["feed_consumed_cost"], today=dt.date(2026, 12, 15))
    assert res.ok and res.scope.start == dt.date(2026, 12, 1) and res.scope.end == dt.date(2026, 12, 31)
    res = resolve("feed cost last quarter", REGISTRY["feed_consumed_cost"], today=dt.date(2026, 12, 15))
    assert res.ok and res.scope.end == dt.date(2026, 9, 30)


def test_every_module_off_is_a_named_problem_not_an_empty_answer():
    res = resolve("how much feed did we use", REGISTRY["feed_consumed_cost"], today=TODAY, modules={"piggery": False, "poultry": False})
    assert not res.ok and res.unresolved.code == "module_off" and "None of the modules" in res.unresolved.message


def test_a_month_by_month_view_a_metric_does_not_have_is_said_so():
    res = resolve("how many sows by month", REGISTRY["sow_count"], today=TODAY)
    assert not res.ok and res.unresolved.code == "unsupported_aggregation" and "month by month" in res.unresolved.message


def test_words_that_only_look_like_farm_words_are_not_domains():
    assert domain_words_in("the plotted line") == ((), ())


def test_next_month_in_december_is_january_of_the_next_year():
    res = resolve("feed cost next month", REGISTRY["feed_consumed_cost"], today=dt.date(2026, 12, 15))
    assert res.ok and res.scope.start == dt.date(2027, 1, 1)


def test_the_second_month_of_a_range_without_a_year_is_not_silently_dropped():
    res = resolve("feed cost from march to may", REGISTRY["feed_consumed_cost"], today=TODAY)
    assert not res.ok and res.unresolved.code in ("month_without_year", "multiple_periods")


# ----------------------------------------------------------------------------------------------- found by the generated-variants probe
import pytest  # noqa: E402

from resolver.periods import comparison_cue, normalise  # noqa: E402


@pytest.mark.parametrize("q", [
    "feed cost on this date in the previous month", "What did the feed cost amount to on this day in the previous month?",
    "feed cost on the same date last month", "feed cost on this date last month", "feed cost on this day of the previous month",
])
def test_same_day_wordings_are_one_date_not_the_whole_month(q):
    res = resolve(q, REGISTRY["feed_consumed_cost"], today=TODAY)
    assert res.ok and res.scope.start == res.scope.end == dt.date(2026, 9, 15), q


def test_a_typo_in_a_period_word_is_repaired_and_a_typo_in_compare_is_still_a_comparison():
    assert normalise("feed cost last montth") == "feed cost last month" and normalise("this wek") == "this week"
    assert normalise("last night") == "last night"                                      # not a period word: untouched
    assert comparison_cue("How does this month's feed cost comare to last montth?") == "period"
    assert comparison_cue("feed cost relative to last month") == "period"
    res = resolve("How does this month's feed cost comare to last montth?", REGISTRY["feed_consumed_cost"], today=TODAY)
    assert not res.ok and res.unresolved.code == "comparison_not_supported"


@pytest.mark.parametrize("word,domain", [("izingulube", "piggery"), ("nguruve", "piggery"), ("huku", "poultry"),
                                         ("inkukhu", "poultry"), ("chibage", "crops")])
def test_shona_and_ndebele_farm_words_name_a_section(word, domain):
    assert domain_words_in(f"Marii yakawanda {word}?")[0] == (domain,)


def test_a_category_question_says_so_on_the_first_line():
    from registry import compute
    res = resolve("spend on feed in March 2026", REGISTRY["expenses"], today=TODAY)
    text = render(res, Result("expenses", "ok", res.scope.with_(category="Feed"), figures={"total": 1.0, "dimension": "domain"},
                              rows=[{"key": "piggery", "label": "Piggery", "month": None, "total": 1.0}]), CTX)
    assert text.splitlines()[0].startswith("Expenses by domain (Feed only)")


def test_prefixed_shona_nouns_still_name_their_section():
    assert domain_words_in("Mangani nguruve nehuku tine here?")[0] == ("piggery", "poultry")
    assert domain_words_in("Marii yedzenguruve?")[0] == ("piggery",)
    assert domain_words_in("how many dollars")[0] == () and domain_words_in("whukuzo")[0] == ()      # an unrelated word is not matched
