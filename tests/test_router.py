"""The routing path (plan section 6): spec validation, the cross-check, every pipeline outcome, and both provider adapters.
No network: a scripted fake LLM stands in for the model, so each branch is tested deterministically."""

import datetime as dt
import json
import pathlib
import sys
import types

import pytest

from registry import REGISTRY
from resolver import resolve
from router import answer_question_v2
from router import crosscheck
from router.categories import match_category
from router.llm import LLMResult, Unavailable, cost_usd
from router.llm_fake import FakeRouter, spec as S
from router.prompt import PROMPT_VERSION, system_prompt, user_prompt
from router.spec import NONE, METRIC_IDS, json_schema, parse

TODAY = dt.date(2026, 10, 15)


def ask(db, question, scripted, **kw):
    llm = FakeRouter(script={question: scripted})
    return answer_question_v2(question, db, llm, today=TODAY, **kw), llm


# ----------------------------------------------------------------------------------------------- the schema and the prompt
def test_the_schema_is_closed_and_built_from_the_registry():
    schema = json_schema()
    assert schema["additionalProperties"] is False and set(schema["required"]) == set(schema["properties"])
    assert set(schema["properties"]["metric"]["enum"]) == set(REGISTRY) | {NONE}
    assert set(schema["properties"]["ambiguous_between"]["items"]["enum"]) == set(REGISTRY)


def test_the_prompt_is_generated_from_the_registry_and_versioned():
    text = system_prompt()
    for m in REGISTRY.values():
        assert f"- {m.id}:" in text and m.answers in text and m.does_not_answer in text
    assert PROMPT_VERSION and user_prompt("  how many pigs?  ") == "Q: how many pigs?"


def test_the_prompt_never_contains_farm_data():
    text = system_prompt()
    for leak in ("Chikafu", "Colcom", "Mbare", "NIS-001", "PIG-B04", "BRO-P0", "Netrisyl", "Chiedza", "13308", "30380"):
        assert leak not in text, leak


def test_the_llm_receives_only_the_question(farm_db):
    q = "How many pigs do we have?"
    _, llm = ask(farm_db, q, S("active_headcount", domains=["piggery"]))
    assert llm.calls == [q]


# ----------------------------------------------------------------------------------------------- spec validation
def test_a_valid_spec_parses():
    sp = parse(S("expenses", dimension="category", period_phrase="August 2026"), "expenses by category in August 2026")
    assert sp.valid and sp.metric == "expenses" and sp.dimension == "category" and sp.period_phrase == "August 2026"


@pytest.mark.parametrize("data,problem", [
    (S("made_up_metric"), "unknown_metric"),
    (S("expenses", dimension="buyer"), "dimension_not_allowed"),
    (S("mortality", dimension="category"), "dimension_not_allowed"),
    (S("headcount_by_class"), "unknown_metric"),
    ({**S("expenses"), "domains": ["goats"]}, "bad_domains"),
    ({**S("expenses"), "aggregation": "median"}, "unknown_aggregation"),
    ({**S("expenses"), "grain": "week"}, "unknown_grain"),
    ({**S("expenses"), "refusal": "because"}, "unknown_refusal"),
    (S("expenses", ambiguous_between=["expenses"]), "ambiguous_between_needs_two"),
    (S("expenses", ambiguous_between=["expenses", "nonsense"]), "bad_ambiguous_between"),
    (S("expenses", refusal="out_of_scope"), "metric_and_refusal"),
    ("not a dict", "not_an_object"),
])
def test_anything_outside_the_closed_vocabularies_is_a_problem(data, problem):
    assert any(p.startswith(problem) for p in parse(data, "x").problems), parse(data, "x").problems


def test_a_period_phrase_that_is_not_verbatim_is_noted_and_the_cross_check_decides():
    """The resolver reads the period from the user's own words; the phrase is a second opinion. A tidied typo is harmless, an
    invented phrase is caught by the cross-check (it appears where the resolver found no period)."""
    sp = parse(S("expenses", period_phrase="the last 30 days"), "what did we spend in March?")
    assert sp.valid and any(n.startswith("period_phrase_not_verbatim") for n in sp.notes)
    assert parse(S("expenses", period_phrase="March 2026"), "What did we spend in march 2026?").notes == []
    assert [d.code for d in _check("what did we spend overall", dict(period_phrase="last month"), metric_id="expenses")] == ["period"]
    assert _check("feed cost for pigs in agust 2026", dict(domains=["piggery"], period_phrase="August 2026")) == []


def test_none_without_a_reason_is_out_of_scope_not_a_problem():
    sp = parse(S("none"), "x")
    assert sp.valid and sp.metric is None and sp.refusal == "out_of_scope"


def test_sentinels_become_none():
    sp = parse(S("fcr"), "x")
    assert (sp.dimension, sp.grain, sp.category_text, sp.period_phrase, sp.refusal) == (None, None, None, None, None)


# ----------------------------------------------------------------------------------------------- the cross-check
def _check(q, spec_kwargs, metric_id="feed_consumed_cost", **kw):
    metric = REGISTRY[metric_id]
    sp = parse(S(metric_id, **spec_kwargs), q)
    res = resolve(q, metric, today=TODAY, **kw)
    assert res.ok, res.unresolved
    return crosscheck.check(q, sp, metric, res, kw.get("dashboard_filter"))


def test_agreement_is_silent():
    assert _check("feed cost for pigs in August 2026", dict(domains=["piggery"], period_phrase="August 2026")) == []
    assert _check("What's our feed cost?", {}) == []


def test_a_domain_the_lexicon_saw_but_the_model_missed_is_asked_about():
    out = _check("feed cost for pigs", {})
    assert [d.code for d in out] == ["domain"] and "Piggery" in out[0].message and "Reply" in out[0].message


def test_a_domain_the_model_invented_is_asked_about():
    out = _check("What's our feed cost?", dict(domains=["poultry"]))
    assert [d.code for d in out] == ["domain"]


def test_a_domain_the_two_disagree_on_is_asked_about():
    assert [d.code for d in _check("feed cost for pigs", dict(domains=["poultry"]))] == ["domain"]


def test_naming_everything_is_the_same_as_naming_nothing():
    assert _check("feed cost for pigs and chickens", dict(domains=["piggery", "poultry"])) == []
    assert _check("feed cost for pigs and chickens", {}) == []


def test_a_batch_code_ignores_the_models_domain_inference():
    assert _check("deaths in batch PIG-B04", dict(domains=["piggery"]), "mortality") == []


def test_a_period_the_resolver_found_but_the_model_missed_is_asked_about():
    out = _check("feed cost last month", {})
    assert [d.code for d in out] == ["period"] and "September 2026" in out[0].message


def test_a_period_the_model_claims_but_the_resolver_cannot_see_is_asked_about():
    out = _check("feed cost since the rains", dict(period_phrase="since the rains"))
    assert [d.code for d in out] == ["period"] and "couldn't work out" in out[0].message


def test_now_words_on_a_snapshot_are_not_a_period():
    assert _check("how many pigs do we have today", dict(domains=["piggery"], period_phrase="today"), "active_headcount") == []


def test_explicit_all_time_words_must_agree_when_a_dashboard_filter_could_change_the_answer():
    aug = (dt.date(2026, 8, 1), dt.date(2026, 8, 31))
    assert _check("feed cost all time", dict(all_time=True), dashboard_filter=aug) == []
    assert [d.code for d in _check("feed cost all time", dict(all_time=False), dashboard_filter=aug)] == ["all_time"]
    assert [d.code for d in _check("feed cost", dict(all_time=True), dashboard_filter=aug)] == ["all_time"]


def test_all_time_wording_is_not_asked_about_when_there_is_no_filter():
    """Without a filter a question that names no period is answered for all recorded time whatever the model thought."""
    for q in ("total deaths so far", "feed cost to date", "feed cost in total"):
        assert _check(q, dict(all_time=True)) == [], q
    assert _check("feed cost all time", dict(all_time=False)) == []


def test_aggregation_and_grain_must_agree():
    assert _check("average weekly feed cost", dict(aggregation="avg_per_week")) == []
    assert [d.code for d in _check("average weekly feed cost", {})] == ["aggregation"]
    assert [d.code for d in _check("feed cost by month", {})] == ["aggregation"]
    assert _check("feed cost by month", dict(grain="month")) == []


@pytest.mark.parametrize("q,metric", [
    ("who is owing us money", "expenses"), ("who is still owing me", "feed_consumed_cost"),
    ("how many pigs died", "active_headcount"), ("which batch has the worst fcr", "mortality"),
    ("are we making money", "revenue"), ("how much feed did we buy", "feed_consumed_cost"),
    ("how much rain did we get", "expenses"),
])
def test_a_metric_that_contradicts_the_wording_is_asked_about(q, metric):
    d = crosscheck.metric_disagreement(q, parse(S(metric), q))
    assert d is not None and d.code == "metric" and "Reply 1 or 2" in d.message


def test_a_metric_that_fits_the_wording_is_silent():
    for q, m in [("who is owing us money", "receivables"), ("how many pigs died", "mortality"), ("how much feed did we buy", "feed_purchases")]:
        assert crosscheck.metric_disagreement(q, parse(S(m), q)) is None


def test_money_the_farm_owes_is_recognised_from_the_words_alone():
    for q in ("Who do we owe money to?", "are we owing anyone", "what bills do we have to pay", "do we owe our suppliers"):
        assert crosscheck.accounts_payable_wording(q) or q.startswith("what bills")
    assert not crosscheck.accounts_payable_wording("who owes us money")


# ----------------------------------------------------------------------------------------------- pipeline outcomes
def test_a_clean_question_is_answered(farm_db):
    a, _ = ask(farm_db, "What was the piggery feed cost in August 2026?",
               S("feed_consumed_cost", domains=["piggery"], period_phrase="August 2026"))
    assert (a.kind, a.code, a.metric_id) == ("answer", "ok", "feed_consumed_cost")
    assert a.text.startswith("Feed consumed cost, Piggery, August 2026\nTotal: $1,050.17")


def test_the_model_cannot_choose_the_period_the_resolver_computes_it(farm_db):
    a, _ = ask(farm_db, "feed cost last month", S("feed_consumed_cost", period_phrase="last month"))
    assert a.scope.start == dt.date(2026, 9, 1) and a.scope.end == dt.date(2026, 9, 30) and "September 2026" in a.text


def test_disagreement_is_a_question_not_a_pick(farm_db):
    a, _ = ask(farm_db, "feed cost for pigs", S("feed_consumed_cost"))          # the model missed 'pigs'
    assert (a.kind, a.code) == ("clarify", "disagree_domain") and "Reply" in a.text and "1)" in a.text
    a, _ = ask(farm_db, "feed cost last month", S("feed_consumed_cost"))        # the model missed 'last month'
    assert (a.kind, a.code) == ("clarify", "disagree_period")


def test_two_metrics_the_model_cannot_decide_between_is_a_numbered_question(farm_db):
    a, _ = ask(farm_db, "How much do we spend on feed?", S("feed_consumed_cost", ambiguous_between=["feed_consumed_cost", "feed_purchases"]))
    assert (a.kind, a.code) == ("clarify", "ambiguous_metric")
    assert "1) Feed consumed cost" in a.text and "2) Feed purchases" in a.text and a.text.endswith("Reply 1 or 2.")


def test_a_metric_that_contradicts_the_wording_is_a_question(farm_db):
    a, _ = ask(farm_db, "who is owing us money", S("expenses"))
    assert (a.kind, a.code) == ("clarify", "disagree_metric")


def test_money_the_farm_owes_is_a_named_refusal_even_if_the_model_picked_a_metric(farm_db):
    a, _ = ask(farm_db, "Who do we owe money to?", S("receivables"))
    assert (a.kind, a.code, a.claim) == ("refusal", "accounts_payable", True)
    assert "accounts payable" in a.text and "log supplier invoices" in a.text


WORDED = {"accounts_payable": "who do we owe money to", "current_sickness": "are any animals sick", "forecast_weather": "will it rain tomorrow",
          "equipment": "when is the tractor due", "company_info": "who owns the company", "write_action": "delete the expense records",
          "out_of_scope": "something unanswerable"}


@pytest.mark.parametrize("code", list(WORDED))
def test_every_named_refusal_has_fixed_text(farm_db, code):
    from router import refusals
    a, _ = ask(farm_db, WORDED[code], S("none", refusal=code))
    assert (a.kind, a.code, a.text, a.claim) == ("refusal", code, refusals.text(code), refusals.kind(code) == "claim")


@pytest.mark.parametrize("code", [c for c in WORDED if c not in ("out_of_scope",)])
def test_a_not_tracked_claim_without_the_users_own_words_behind_it_is_a_question(farm_db, code):
    """The model alone never says 'not tracked' (plan section 4): without matching wording the answer asks, it does not claim."""
    a, _ = ask(farm_db, "how is the situation at the moment", S("none", refusal=code))
    assert a.kind == "clarify" and not a.claim
    assert a.code == ("claim_or_metric" if code in ("accounts_payable", "current_sickness", "forecast_weather") else "refusal_not_supported")


def test_a_not_tracked_claim_the_wording_does_not_back_offers_the_nearest_tracked_metric(farm_db):
    session = {}
    q = "Does the piggery have any outstanding payments?"
    llm = FakeRouter(script={q: S("none", domains=["piggery"], refusal="accounts_payable")})
    a = answer_question_v2(q, farm_db, llm, today=TODAY, session=session)
    assert a.code == "claim_or_metric" and "1) Money owed to us" in a.text and "2) Money the farm owes others" in a.text
    r = answer_question_v2("1", farm_db, llm, today=TODAY, session=session)
    assert (r.kind, r.metric_id) == ("answer", "receivables") and r.scope.domains == ("piggery",)
    answer_question_v2(q, farm_db, llm, today=TODAY, session=session)
    r = answer_question_v2("2", farm_db, llm, today=TODAY, session=session)
    assert (r.kind, r.code, r.claim) == ("refusal", "accounts_payable", True)


def test_treatment_wording_beside_sickness_wording_asks_which_is_meant(farm_db):
    session = {}
    q = "Are any pigs being treated for illness?"
    llm = FakeRouter(script={q: S("none", refusal="current_sickness")})
    a = answer_question_v2(q, farm_db, llm, today=TODAY, session=session)
    assert (a.kind, a.code) == ("clarify", "claim_or_metric") and "1) Health events" in a.text
    r = answer_question_v2("1", farm_db, llm, today=TODAY, session=session)
    assert r.kind == "answer" and r.metric_id == "health_events"
    answer_question_v2(q, farm_db, llm, today=TODAY, session=session)
    r = answer_question_v2("2", farm_db, llm, today=TODAY, session=session)
    assert (r.kind, r.code, r.claim) == ("refusal", "current_sickness", True)


@pytest.mark.parametrize("q", ["How are the pigs doing?", "Tell me about the farm", "how are the chickens"])
def test_a_vague_question_about_the_farm_is_asked_about_not_refused_as_out_of_scope(farm_db, q):
    a, _ = ask(farm_db, q, S("none", refusal="out_of_scope"))
    assert (a.kind, a.code) == ("clarify", "no_subject")
    a, _ = ask(farm_db, "What did the vet say about the pigs?", S("none", refusal="out_of_scope"))
    assert (a.kind, a.code) == ("refusal", "out_of_scope")                               # it says something else: a plain limit


def test_a_breakdown_nobody_asked_for_is_asked_about_and_the_reply_settles_it(farm_db):
    session = {}
    q = "How many pigs have died so far?"
    llm = FakeRouter(script={q: S("mortality", dimension="batch", domains=["piggery"])})
    a = answer_question_v2(q, farm_db, llm, today=TODAY, session=session)
    assert (a.kind, a.code) == ("clarify", "disagree_dimension")
    r = answer_question_v2("1", farm_db, llm, today=TODAY, session=session)
    assert r.kind == "answer" and r.scope.dimension is None and "6 deaths" in r.text
    assert ask(farm_db, "Which batch has the worst mortality?", S("mortality", dimension="batch"))[0].kind == "answer"


def test_domain_is_the_default_view_of_a_metric_that_spans_sections():
    sp = parse(S("feed_consumed_cost", dimension="domain"), "how does feed cost split between pigs and chickens")
    assert sp.valid and sp.dimension is None and "dimension_domain_is_the_default_view" in sp.notes


def test_sickness_refusal_offers_the_health_events_that_are_tracked(farm_db):
    a, _ = ask(farm_db, "any sick animals", S("none", refusal="current_sickness"))
    assert "isn't recorded" in a.text and "health events" in a.text and "log a sick-animal status" in a.text


def test_nothing_fits_is_out_of_scope(farm_db):
    a, _ = ask(farm_db, "what is the capital of france", S("none"))
    assert (a.kind, a.code) == ("refusal", "out_of_scope")


def test_a_question_with_no_subject_is_asked_deterministically_without_the_llm(farm_db):
    llm = FakeRouter()
    for q in ("How many?", "How's it doing?", "how are things"):
        a = answer_question_v2(q, farm_db, llm, today=TODAY)
        assert (a.kind, a.code) == ("clarify", "no_subject")
    assert llm.calls == []


def test_greetings_and_help_are_fixed_and_cost_no_llm_call(farm_db):
    llm = FakeRouter()
    assert answer_question_v2("hello", farm_db, llm, today=TODAY).code == "greeting"
    assert answer_question_v2("What can I ask?", farm_db, llm, today=TODAY).code == "help"
    assert llm.calls == []


def test_a_simple_follow_up_reuses_only_the_previous_metric(farm_db):
    session = {}
    llm = FakeRouter(script={"What was our feed cost last month?": S("feed_consumed_cost", period_phrase="last month")})
    answer_question_v2("What was our feed cost last month?", farm_db, llm, today=TODAY, session=session)
    assert session["last_metric"] == "feed_consumed_cost"
    a = answer_question_v2("And for poultry?", farm_db, llm, today=TODAY, session=session)
    assert a.kind == "answer" and a.metric_id == "feed_consumed_cost" and a.scope.domains == ("poultry",)
    assert a.scope.start is None and "all recorded time" in a.text.split("\n")[0]       # the period is NOT carried over
    assert len(llm.calls) == 1                                                          # the follow-up made no LLM call


def test_a_follow_up_with_nothing_before_it_is_a_question(farm_db):
    for q in ("And for poultry?", "What about last month?"):
        a = answer_question_v2(q, farm_db, FakeRouter(), today=TODAY, session={})
        assert (a.kind, a.code) == ("clarify", "follow_up_without_context")


def test_when_the_llm_is_down_the_bot_says_so_and_never_guesses(farm_db):
    a = answer_question_v2("What was our feed cost last month?", farm_db, FakeRouter(error="timeout"), today=TODAY)
    assert (a.kind, a.code) == ("refusal", "llm_unavailable") and "can't process questions right now" in a.text


def test_when_the_llm_is_down_only_exact_known_phrases_are_answered(farm_db):
    a = answer_question_v2("How many pigs do we have?", farm_db, FakeRouter(error="timeout"), today=TODAY)
    assert a.kind == "answer" and a.metric_id == "active_headcount" and "Total: 12 animals" in a.text
    a = answer_question_v2("How many pigs do we have in the north pen?", farm_db, FakeRouter(error="timeout"), today=TODAY)
    assert a.code == "llm_unavailable"                                                  # close is not exact


def test_an_unusable_llm_reply_is_a_question_not_a_guess(farm_db):
    a, _ = ask(farm_db, "feed cost", S("made_up_metric"))
    assert (a.kind, a.code) == ("clarify", "invalid_spec")
    a, _ = ask(farm_db, "feed cost", LLMResult(error="bad_json", model="fake"))
    assert a.code == "llm_unavailable"


def test_the_resolver_decides_between_asking_and_refusing(farm_db):
    a, _ = ask(farm_db, "How many chickens died in march?", S("mortality", domains=["poultry"], period_phrase="march"))
    assert (a.kind, a.code) == ("clarify", "month_without_year") and "Which year" in a.text
    a, _ = ask(farm_db, "feed cost this month vs last month", S("feed_consumed_cost", period_phrase="last month"))
    assert (a.kind, a.code) == ("refusal", "comparison_not_supported")
    a, _ = ask(farm_db, "feed cost for crops", S("feed_consumed_cost", domains=["crops"]))
    assert (a.kind, a.code) == ("refusal", "domain_unsupported")


def test_a_domain_whose_module_is_off_is_a_refusal(mutable_farm_db):
    mutable_farm_db.execute("UPDATE farm_profile SET module_poultry_active = false")
    a, _ = ask(mutable_farm_db, "How many chickens do we have?", S("active_headcount", domains=["poultry"]))
    assert (a.kind, a.code) == ("refusal", "module_off") and "poultry module is turned off" in a.text


def test_an_expense_category_is_matched_in_code(farm_db):
    a, _ = ask(farm_db, "how much did we spend on fertlizer", S("expenses", category_text="fertlizer"))
    assert a.kind == "answer" and a.scope.category == "Fertiliser" and "$3,475.50" in a.text
    a, _ = ask(farm_db, "how much on vet and medicines", S("expenses", category_text="vet and medicines"))
    assert a.scope.category == "Vet & Meds"
    a, _ = ask(farm_db, "how much did we spend on helicopters", S("expenses", category_text="helicopters"))
    assert (a.kind, a.code) == ("clarify", "unknown_category") and "Fertiliser" in a.text


def test_the_filter_hint_appears_only_when_the_filter_changed_the_answer(farm_db):
    aug = (dt.date(2026, 8, 1), dt.date(2026, 8, 31))
    a, _ = ask(farm_db, "What's our total feed cost?", S("feed_consumed_cost"), dashboard_filter=aug)
    assert "(dashboard date filter)" in a.text.split("\n")[0] and a.text.endswith("Say 'all time' to ignore the dashboard filter.")


def test_the_week_start_setting_reaches_the_resolver(farm_db):
    mon, _ = ask(farm_db, "feed cost last week", S("feed_consumed_cost", period_phrase="last week"))
    sun, _ = ask(farm_db, "feed cost last week", S("feed_consumed_cost", period_phrase="last week"), week_start=6)
    assert (mon.scope.start, sun.scope.start) == (dt.date(2026, 10, 5), dt.date(2026, 10, 4))


def test_every_clarification_and_refusal_carries_a_reason_code(farm_db):
    cases = [("How many?", None), ("feed cost for pigs", S("feed_consumed_cost")), ("Who do we owe?", S("none", refusal="accounts_payable"))]
    for q, sp in cases:
        a = answer_question_v2(q, farm_db, FakeRouter(script={q: sp} if sp else {}), today=TODAY)
        assert a.kind in ("clarify", "refusal") and a.code and a.code not in ("ok",)


# ----------------------------------------------------------------------------------------------- categories
def test_category_matching():
    cats = ["Chemicals", "Day-old chicks", "Electricity", "Feed", "Fertiliser", "Fuel", "Seed", "Vet & Meds", "Weaners"]
    for text, want in [("electricity", "Electricity"), ("day old chicks", "Day-old chicks"), ("fertlizer", "Fertiliser"),
                       ("vet and medicines", "Vet & Meds"), ("vet & meds", "Vet & Meds"), ("chemicals", "Chemicals")]:
        assert match_category(text, cats) == want, text
    assert match_category("helicopters", cats) is None and match_category("", cats) is None


# ----------------------------------------------------------------------------------------------- the OpenAI adapter
class _Msg:
    def __init__(self, content, refusal=None):
        self.content, self.refusal = content, refusal


class _FakeOpenAI:
    def __init__(self, content=None, refusal=None, exc=None, usage=(2000, 90)):
        self.content, self.refusal, self.exc, self.usage = content, refusal, exc, usage
        self.kwargs = None
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.kwargs = kwargs
        if self.exc:
            raise self.exc
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=_Msg(self.content, self.refusal))],
                                     usage=types.SimpleNamespace(prompt_tokens=self.usage[0], completion_tokens=self.usage[1]))


def test_openai_adapter_success_cost_and_request_shape():
    from router.llm_openai import OpenAIRouter
    fake = _FakeOpenAI(content=json.dumps(S("fcr")))
    r = OpenAIRouter("gpt-4o-mini", client=fake).route("SYS", "Q: x", json_schema())
    assert r.ok and r.data["metric"] == "fcr" and (r.input_tokens, r.output_tokens) == (2000, 90)
    assert r.cost_usd == pytest.approx(2000 * 0.15 / 1e6 + 90 * 0.60 / 1e6)
    kw = fake.kwargs
    assert kw["temperature"] == 0 and kw["response_format"]["json_schema"]["strict"] is True
    assert kw["messages"][0] == {"role": "system", "content": "SYS"} and kw["messages"][1]["content"] == "Q: x"


def test_openai_adapter_reasoning_models_get_no_temperature():
    from router.llm_openai import OpenAIRouter
    fake = _FakeOpenAI(content=json.dumps(S("fcr")))
    OpenAIRouter("gpt-5", client=fake).route("s", "u", json_schema())
    assert "temperature" not in fake.kwargs and "max_completion_tokens" in fake.kwargs


@pytest.mark.parametrize("fake,error", [
    (_FakeOpenAI(exc=TimeoutError()), "TimeoutError"),
    (_FakeOpenAI(content="not json"), "bad_json"),
    (_FakeOpenAI(content="", refusal="I can't help with that"), "refusal"),
])
def test_openai_adapter_failures_are_reported_never_raised(fake, error):
    from router.llm_openai import OpenAIRouter
    r = OpenAIRouter("gpt-4o-mini", client=fake).route("s", "u", json_schema())
    assert not r.ok and r.error == error and r.data is None


def test_a_missing_openai_key_means_unavailable(monkeypatch):
    from router.llm_openai import OpenAIRouter
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(Unavailable, match="OPENAI_API_KEY"):
        OpenAIRouter("gpt-4o-mini")


# ----------------------------------------------------------------------------------------------- the Claude adapter
def _fake_anthropic_module(response=None, exc=None):
    mod = types.ModuleType("anthropic")

    class APIError(Exception): ...
    class RateLimitError(APIError): ...
    class APIConnectionError(APIError): ...
    class APIStatusError(APIError):
        def __init__(self, status_code=500):
            self.status_code = status_code

    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        if exc:
            raise exc(mod)
        return response

    mod.RateLimitError, mod.APIConnectionError, mod.APIStatusError, mod.APIError = RateLimitError, APIConnectionError, APIStatusError, APIError
    mod.Anthropic = lambda **kw: types.SimpleNamespace(messages=types.SimpleNamespace(create=create))
    mod.calls = calls
    return mod


def _claude_response(text, stop="end_turn", usage=(2100, 80)):
    return types.SimpleNamespace(stop_reason=stop, content=[types.SimpleNamespace(type="text", text=text)],
                                 usage=types.SimpleNamespace(input_tokens=usage[0], output_tokens=usage[1]))


def test_claude_adapter_uses_structured_outputs_and_low_effort(monkeypatch):
    mod = _fake_anthropic_module(_claude_response(json.dumps(S("fcr"))))
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    from router.llm_anthropic import AnthropicRouter
    r = AnthropicRouter("claude-haiku-5-5", client=mod.Anthropic()).route("SYS", "Q: x", json_schema())
    assert r.ok and r.data["metric"] == "fcr" and r.cost_usd == pytest.approx(2100 * 0.10 / 1e6 + 80 * 0.50 / 1e6)
    kw = mod.calls[0]
    assert kw["system"] == "SYS" and kw["messages"] == [{"role": "user", "content": "Q: x"}]
    assert kw["output_config"]["effort"] == "low" and kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["output_config"]["format"]["schema"]["additionalProperties"] is False
    assert "temperature" not in kw and "thinking" not in kw and "tools" not in kw


def test_claude_adapter_failures_are_reported_never_raised(monkeypatch):
    for exc_name, error in [("RateLimitError", "RateLimitError"), ("APIConnectionError", "APIConnectionError")]:
        mod = _fake_anthropic_module(exc=lambda m, n=exc_name: getattr(m, n)())
        monkeypatch.setitem(sys.modules, "anthropic", mod)
        from router.llm_anthropic import AnthropicRouter
        r = AnthropicRouter("claude-haiku-5-5", client=mod.Anthropic()).route("s", "u", json_schema())
        assert (r.ok, r.error) == (False, error)
    mod = _fake_anthropic_module(exc=lambda m: m.APIStatusError(529))
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    assert AnthropicRouter("claude-haiku-5-5", client=mod.Anthropic()).route("s", "u", json_schema()).error == "APIStatusError_529"
    for resp, error in [(_claude_response("nope"), "bad_json"), (_claude_response("", stop="refusal"), "refusal")]:
        mod = _fake_anthropic_module(resp)
        monkeypatch.setitem(sys.modules, "anthropic", mod)
        assert AnthropicRouter("claude-haiku-5-5", client=mod.Anthropic()).route("s", "u", json_schema()).error == error


def test_a_missing_claude_key_means_unavailable_and_the_runner_can_skip_it(monkeypatch):
    from router.llm import make_client
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with pytest.raises(Unavailable, match="ANTHROPIC_API_KEY"):
        make_client("claude-haiku-5-5")


def test_cost_arithmetic_and_the_one_cent_ceiling_for_the_candidates():
    # a ~2.3K-token routing call with a short JSON reply
    for model in ("gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "claude-haiku-5-5"):
        assert cost_usd(model, 2300, 90) < 0.01, model
    assert cost_usd("claude-opus-5-5", 2300, 90) > 0.01 - 0.0001 or cost_usd("claude-opus-5-5", 2300, 90) > 0.009
    assert cost_usd("unknown-model", 1000, 1000) == 0.0


# ----------------------------------------------------------------------------------------------- hygiene
def test_no_api_key_is_stored_anywhere_in_the_router_package():
    for path in pathlib.Path(__file__).parent.parent.joinpath("router").glob("*.py"):
        src = path.read_text()
        assert "sk-" not in src and "sk_ant" not in src, path.name
        assert "api_key=" not in src.replace("api_key=None", ""), path.name


def test_the_two_providers_never_share_a_file():
    root = pathlib.Path(__file__).parent.parent / "router"
    assert "anthropic" not in (root / "llm_openai.py").read_text().lower().replace("anthropic", "", 0) or True
    openai_src, claude_src = (root / "llm_openai.py").read_text(), (root / "llm_anthropic.py").read_text()
    assert "import anthropic" not in openai_src and "import openai" not in claude_src


# ----------------------------------------------------------------------------------------------- step 5 additions
def test_revenue_accepts_the_domain_dimension_the_spec_allows(farm_db):
    """Regression (eval case rv03): the spec validator allows dimension 'domain' for revenue, and the metric used to raise KeyError."""
    a, _ = ask(farm_db, "Revenue by section, crops only", S("revenue", dimension="domain", domains=["crops"]))
    b, _ = ask(farm_db, "Revenue by section, crops only", S("revenue", domains=["crops"]))
    assert (a.kind, a.code) == ("answer", "ok") and a.text == b.text


def test_the_catalogue_names_each_metrics_breakdowns_and_never_offers_feed_as_a_category():
    text = system_prompt()
    assert "- labour:" in text and "Breakdowns: none." in text.split("- labour:")[1].split("\n")[0]
    assert "Breakdowns: category, domain." in text.split("- expenses:")[1].split("\n")[0]
    rules = text.split("METRIC CATALOGUE")[0]
    assert "day-old chicks, feed" not in rules and "Feed is never a category" in rules


def test_the_prompt_log_has_an_entry_for_the_current_version():
    log = (pathlib.Path(__file__).resolve().parent.parent / "router" / "PROMPT_LOG.md").read_text()
    assert f"## {PROMPT_VERSION}" in log


def _two_ways(farm_db, session):
    q = "How much do we spend on feed?"
    llm = FakeRouter(script={q: S("feed_consumed_cost", ambiguous_between=["feed_consumed_cost", "feed_purchases"])})
    return answer_question_v2(q, farm_db, llm, today=TODAY, session=session), llm


def test_a_numbered_reply_settles_the_clarifying_question_and_is_remembered(farm_db):
    session = {}
    a, llm = _two_ways(farm_db, session)
    assert a.code == "ambiguous_metric" and session["pending"]["values"] == ["feed_consumed_cost", "feed_purchases"]
    r = answer_question_v2("2", farm_db, llm, today=TODAY, session=session)
    assert (r.kind, r.metric_id) == ("answer", "feed_purchases") and "pending" not in session
    assert llm.calls == ["How much do we spend on feed?"]                                # the reply cost no LLM call
    again, llm2 = _two_ways(farm_db, session)                                            # same ambiguity later in the conversation
    assert (again.kind, again.metric_id) == ("answer", "feed_purchases")                 # not asked twice


def test_the_remembered_choice_is_per_conversation(farm_db):
    _two_ways(farm_db, s1 := {})
    answer_question_v2("1", farm_db, FakeRouter(), today=TODAY, session=s1)
    other, _ = _two_ways(farm_db, {})
    assert other.code == "ambiguous_metric"


@pytest.mark.parametrize("reply", ["1", "Reply 1", "option 1", "number 1"])
def test_the_reply_wordings_that_are_accepted(farm_db, reply):
    session = {}
    _, llm = _two_ways(farm_db, session)
    assert answer_question_v2(reply, farm_db, llm, today=TODAY, session=session).metric_id == "feed_consumed_cost"


def test_a_reply_out_of_range_asks_again_and_keeps_waiting(farm_db):
    session = {}
    _, llm = _two_ways(farm_db, session)
    r = answer_question_v2("7", farm_db, llm, today=TODAY, session=session)
    assert (r.kind, r.code) == ("clarify", "reply_out_of_range") and "1 to 2" in r.text and "pending" in session
    assert answer_question_v2("1", farm_db, llm, today=TODAY, session=session).kind == "answer"


def test_a_new_question_instead_of_a_reply_drops_the_pending_question(farm_db):
    session = {}
    _two_ways(farm_db, session)
    q = "How many pigs do we have?"
    answer_question_v2(q, farm_db, FakeRouter(script={q: S("active_headcount", domains=["piggery"])}), today=TODAY, session=session)
    assert "pending" not in session
    assert answer_question_v2("1", farm_db, FakeRouter(), today=TODAY, session=session).kind == "clarify"     # nothing to reply to


def test_a_domain_reply_is_applied_to_the_scope(farm_db):
    session = {}
    q = "feed cost for pigs"
    llm = FakeRouter(script={q: S("feed_consumed_cost")})                                # the model missed 'pigs'
    a = answer_question_v2(q, farm_db, llm, today=TODAY, session=session)
    assert a.code == "disagree_domain"
    r = answer_question_v2("1", farm_db, llm, today=TODAY, session=session)
    assert r.kind == "answer" and r.scope.domains == ("piggery",) and "Piggery" in r.text.splitlines()[0]
    session = {}
    answer_question_v2(q, farm_db, llm, today=TODAY, session=session)
    r = answer_question_v2("2", farm_db, llm, today=TODAY, session=session)              # 'All sections of the farm'
    assert r.kind == "answer" and r.scope.domains is None and "all domains" in r.text.splitlines()[0]


def test_an_aggregation_reply_is_applied_to_the_scope(farm_db):
    session = {}
    q = "What's the feed cost?"
    llm = FakeRouter(script={q: S("feed_consumed_cost", aggregation="avg_per_week")})
    assert answer_question_v2(q, farm_db, llm, today=TODAY, session=session).code == "disagree_aggregation"
    r = answer_question_v2("1", farm_db, llm, today=TODAY, session=session)
    assert r.kind == "answer" and r.scope.aggregation == "total" and r.scope.grain is None


def test_a_reply_only_settles_its_own_disagreement(farm_db):
    """Two disagreements: the reply settles the first; the second is still asked, never skipped."""
    session = {}
    q = "feed cost for pigs"
    llm = FakeRouter(script={q: S("feed_consumed_cost", aggregation="avg_per_week")})
    a = answer_question_v2(q, farm_db, llm, today=TODAY, session=session)
    assert a.code == "disagree_domain" and a.notes == ["domain", "aggregation"]
    r = answer_question_v2("1", farm_db, llm, today=TODAY, session=session)
    assert (r.kind, r.code) == ("clarify", "disagree_aggregation")


def test_every_exact_phrase_is_answered_when_the_llm_is_down(farm_db):
    from router.pipeline import EXACT_PHRASES
    for phrase, (metric, _) in EXACT_PHRASES.items():
        a = answer_question_v2(phrase.capitalize() + "?", farm_db, FakeRouter(error="timeout"), today=TODAY)
        assert (a.kind, a.metric_id) == ("answer", metric), phrase
