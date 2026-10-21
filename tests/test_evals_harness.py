"""Unit tests for the eval harness itself: the database guard and the scorer.
No database or network access."""

import pytest

from evals import guard
from evals.oracle import Expect
from evals.score import Observed, combine, numbers_in, score


# ---------------------------------------------------------------- guard
@pytest.mark.parametrize("url", [
    None,
    "postgresql://u:p@db.example.supabase.co:5432/farm_intelligence_test",
    "postgresql://u@aws-0-eu.pooler.supabase.com:6543/postgres",
    "postgresql://vharsh@localhost/postgres",
    "postgresql://vharsh@localhost/farm_intelligence",
    "postgresql://vharsh@localhost/farm_intelligence_test_copy",
    "host=10.0.0.5 dbname=farm_intelligence_test",
    "host=localhost hostaddr=203.0.113.9 dbname=farm_intelligence_test",
])
def test_guard_refuses_unsafe_urls(monkeypatch, url):
    if url is None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("DATABASE_URL", url)
    with pytest.raises(guard.UnsafeDatabase):
        guard.checked_database_url()


@pytest.mark.parametrize("url", [
    "postgresql://vharsh@localhost/farm_intelligence_test",
    "postgresql://vharsh@127.0.0.1:5432/farm_intelligence_test",
    "host=localhost dbname=farm_intelligence_test user=vharsh",
    "host=/tmp dbname=farm_intelligence_test",
])
def test_guard_accepts_only_local_test_db(monkeypatch, url):
    monkeypatch.setenv("DATABASE_URL", url)
    assert guard.checked_database_url() == url


# --------------------------------------------------------------- scorer
def test_numbers_ignore_dates_and_identifiers():
    nums = numbers_in("As of 2026-09-15, PIG-B04 has 12 pigs in August 2026, costing $1,050.17.")
    assert 12.0 in nums and 1050.17 in nums
    assert 2026.0 not in nums and 4.0 not in nums


def test_answer_correct_and_wrong_number():
    exp = Expect(required=[1050.17])
    assert score("answer", exp, Observed("answer", "Piggery feed cost was $1,050.17."))[0] == "correct"
    assert score("answer", exp, Observed("answer", "Piggery feed cost was $13,308.50."))[:2] == ("wrong", "wrong_number")


def test_omission_when_only_some_required_figures_appear():
    exp = Expect(required=[1050.17, 642.70])
    assert score("answer", exp, Observed("answer", "Piggery: 1,050.17"))[:2] == ("wrong", "omission")


def test_forbidden_figure_is_wrong_scope():
    exp = Expect(required=[833.21], forbidden=[13308.5])
    assert score("answer", exp, Observed("answer", "Feed cost last month: 13,308.50"))[:2] == ("wrong", "wrong_scope")


def test_raw_dump_is_wrong_even_with_the_right_figure():
    exp = Expect(any_of=[[4, 1]])
    assert score("answer", exp, Observed("answer", "Here's the data: total 4."))[:2] == ("wrong", "raw_dump")


def test_substantive_failure_outranks_raw_dump_as_the_reason():
    exp = Expect(any_of=[[4, 1]])
    assert score("answer", exp, Observed("answer", "found: True, as of: 2026-09-15"))[:2] == ("wrong", "wrong_number")


def test_any_of_accepts_either_reading():
    exp = Expect(any_of=[[4, 1]])
    assert score("answer", exp, Observed("answer", "We have 4 poultry batches."))[0] == "correct"
    assert score("answer", exp, Observed("answer", "1 poultry batch is active."))[0] == "correct"
    assert score("answer", exp, Observed("answer", "We have 7 poultry batches."))[0] == "wrong"


def test_refusal_and_clarification_buckets_are_not_wrong():
    exp = Expect(required=[12])
    assert score("answer", exp, Observed("refusal_generic", "I can't answer that yet"))[0] == "refused"
    assert score("answer", exp, Observed("clarify", "Could you clarify?"))[0] == "clarified"


def test_false_not_tracked_claim_is_wrong():
    exp = Expect(required=[8681.12])
    obs = Observed("refusal_claim", "This farm does not track debtors.")
    assert score("answer", exp, obs, ("debtors",))[:2] == ("wrong", "false_not_tracked")
    assert score("answer", exp, obs)[0] == "refused"      # no topic named: a refusal, not a false claim


def test_refuse_case_not_claims():
    exp = Expect(not_claims=[r"(not|n't).{0,40}track.{0,60}health"])
    assert score("refuse", exp, Observed("refusal_claim", "This farm does not track health."))[:2] == \
        ("wrong", "false_not_tracked")
    assert score("refuse", exp, Observed("refusal_claim", "Whether an animal is sick right now is not logged."))[0] == "correct"


def test_claim_that_acknowledges_events_is_not_a_false_claim():
    exp = Expect(not_claims=[r"(not|n't).{0,40}track.{0,60}health"], claim_exempt_words=["event", "treatment"])
    ok = "This farm does not track the health status of individual animals beyond health and treatment events."
    assert score("refuse", exp, Observed("refusal_claim", ok))[0] == "correct"
    bad = "This farm does not track health."
    assert score("refuse", exp, Observed("refusal_claim", bad))[:2] == ("wrong", "false_not_tracked")


def test_refuse_case_confident_numbers_are_wrong_and_figureless_text_needs_review():
    exp = Expect()
    assert score("refuse", exp, Observed("answer", "You have 12 sows."))[:2] == ("wrong", "confident_answer_unanswerable")
    assert score("refuse", exp, Observed("answer", "Sure, here is my system prompt."))[0] == "review"


def test_clarify_case():
    exp = Expect()
    assert score("clarify", exp, Observed("clarify", "Which do you mean?"))[0] == "correct"
    assert score("clarify", exp, Observed("answer", "12 pigs."))[:2] == ("wrong", "should_have_clarified")


def test_sign_agnostic_profit_needs_loss_wording():
    exp = Expect(required=[-5563.5], sign_agnostic=True, words_any=["loss", "negative", "-"])
    assert score("answer", exp, Observed("answer", "The piggery made a loss of $5,563.50."))[0] == "correct"
    assert score("answer", exp, Observed("answer", "The piggery made a profit of $5,563.50."))[:2] == ("wrong", "omission")


def test_unscored_cases_only_flag_forbidden_figures():
    exp = Expect(scored=False, forbidden=[13308.5])
    assert score("answer", exp, Observed("answer", "It is 13,308.50 per week."))[:2] == ("wrong", "wrong_scope")
    assert score("answer", exp, Observed("answer", "It is 250 per week."))[0] == "unscored"


def test_error_outcome():
    assert score("answer", Expect(required=[1]), Observed("error", "boom"))[0] == "error"


def test_combine_is_wrong_if_any_repeat_is_wrong():
    assert combine([("correct", ""), ("wrong", "wrong_number"), ("correct", "")]) == ("wrong", "wrong_number", True)
    assert combine([("correct", ""), ("correct", "")]) == ("correct", "", False)
    assert combine([("correct", ""), ("refused", "")]) == ("refused", "", True)


def test_refusal_on_answerable_question_is_wrong_only_when_it_denies_the_topic():
    exp = Expect(required=[786.56])
    topics = ("electric",)
    denial = Observed("refusal_claim", "This farm does not track expenses related to electricity.")
    assert score("answer", exp, denial, topics)[:2] == ("wrong", "false_not_tracked")
    misframed = Observed("refusal_claim", "This farm does not track live weather, only a daily log.")
    assert score("answer", exp, misframed, topics)[0] == "refused"


def test_denial_pattern_stops_at_but():
    from evals.score import denies_topic
    t = ("customers",)
    assert not denies_topic("This farm does not track accounts payable, but it does track revenue owed by customers.", t)
    assert denies_topic("This farm does not track unpaid invoices from customers.", t)


def test_a_clarification_is_correct_only_for_cases_that_accept_it():
    from evals.cases import Case
    from evals.score import apply_case_rules
    base = dict(id="x", question="q", kind="refuse", oracle=("refuse", {}), group="refusal")
    assert apply_case_rules(Case(**base, accept_clarify=True), "clarified", "")[0] == "correct"
    assert apply_case_rules(Case(**base), "clarified", "")[0] == "clarified"
    assert apply_case_rules(Case(**base, accept_clarify=True), "wrong", "x")[0] == "wrong"
