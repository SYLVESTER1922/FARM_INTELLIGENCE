"""
The v2 answer path (spec-chatbot-v2-plan.md, section 6): ONE LLM call per question, then code.

    greeting / help (exact)  ->  no real subject? ask  ->  follow-up? reuse the previous metric  ->  LLM routes to a spec
    ->  validate the spec against the registry's closed vocabularies  ->  named refusal / ambiguity question
    ->  scope resolver reads the period and domains from the same words  ->  cross-check them against the LLM's spec
    ->  registry computes  ->  template renders

Session state (a plain dict the caller keeps for one conversation; the UI holds it in gr.State):
    last_metric   the previous answered metric, for "and for poultry?" follow-ups
    pending       the clarifying question just asked: the options and what each means, so a reply of "1" or "2" is applied
    metric_choice a choice between two named metrics, remembered for the rest of the conversation so it is not asked again

Three outcomes only: an answer, a clarifying question (numbered options, with a reason code) or a named refusal. There is no silent
pick anywhere: whenever the LLM and the deterministic reading disagree, the user is asked. If the LLM is unavailable the bot says so
and answers only exact known phrases; it never guesses.
"""

import dataclasses
import re
import time
from dataclasses import dataclass, field

from catalog.build import help_text, limits_text
from registry import REGISTRY, Scope, compute
from registry.core import latest_log_date
from render import RenderContext, render
from render.constants import GREETING
from resolver import all_time_scope, resolve
from resolver.periods import harare_today, normalise
from router import alerts, crosscheck, refusals
from router.categories import farm_categories, match_category
from router.llm import LLMResult, is_transient
from router.prompt import PROMPT_VERSION, system_prompt, user_prompt
from router.spec import RoutedSpec, json_schema, parse

HELP = None                                  # generated from the registry on use: catalog.build.help_text()

_GREETINGS = {"hi", "hello", "hey", "hie", "yo", "hi there", "hello there", "hey there", "good morning", "good afternoon", "good evening"}
_HELPS = {"help", "what can you ask", "what can i ask", "what can i ask you", "what questions can i ask", "what do you do",
          "how does this work", "what are you able to answer", "what can you answer", "what can you tell me", "what do you track",
          "what data do you have", "what can you do"}
_LIMITS = {"what can t you answer", "what can you not answer", "what don t you know", "what can t you tell me", "what do you not track",
           "what don t you track", "what are your limits"}

_STOPWORDS = {
    "how", "what", "why", "when", "where", "who", "which", "is", "are", "was", "were", "do", "does", "did", "doing", "done",
    "it", "its", "this", "that", "these", "those", "the", "a", "an", "to", "of", "for", "with", "on", "in", "at", "about",
    "many", "much", "any", "some", "we", "us", "our", "you", "your", "have", "has", "had", "going", "happening", "like", "and",
    "s", "things", "thing", "up", "tell", "me", "show", "give", "please", "can", "could", "hows",
}
_FOLLOW_UP = re.compile(r"^\s*(and|what about|how about|same for|what of)\b")

# OUTAGE FALLBACK, exact matches only. These 13 phrases are answered when (and only when) the LLM could not be used; with the model up
# they are routed like any other question. Close is not exact: anything else gets the busy / unavailable reply. question -> (metric, domains)
EXACT_PHRASES = {
    "how many pigs do we have": ("active_headcount", ("piggery",)),
    "how many chickens do we have": ("active_headcount", ("poultry",)),
    "how many animals do we have": ("active_headcount", ()),
    "how many batches do we have": ("batch_count", ()),
    "how many sows do we have": ("sow_count", ()),
    "what is our profit": ("profit", ()),
    "what is our revenue": ("revenue", ()),
    "what is our total revenue": ("revenue", ()),
    "who owes us money": ("receivables", ()),
    "who owes us": ("receivables", ()),
    "what are our total expenses": ("expenses", ()),
    "what is our feed cost": ("feed_consumed_cost", ()),
    "how much feed do we have left": ("feed_stock", ()),
}

# "1", "2", "reply 2", "option 3", "number 1"
_REPLY = re.compile(r"^(?:(?:reply|option|number|choice|no|answer)\s*)?(\d)$")


@dataclass
class V2Answer:
    text: str
    kind: str                           # answer | clarify | refusal
    code: str                           # ok | no_record | not_available | greeting | help | clarify reason | refusal code
    metric_id: str = None
    scope: Scope = None
    spec: RoutedSpec = None
    llm: LLMResult = None
    claim: bool = False                 # a refusal that says something is not tracked
    seconds: float = 0.0
    notes: list = field(default_factory=list)

    @property
    def observed_kind(self):
        """How the eval harness classifies it: answer | clarify | refusal_generic | refusal_claim."""
        if self.kind == "refusal":
            return "refusal_claim" if self.claim else "refusal_generic"
        return self.kind


_FARM_WORDS = {"farm", "farms", "animal", "animals", "livestock", "stock", "herd", "flock", "everything"}


def _vague_about_the_farm(question):
    """A question about a section or the farm in general with nothing to say what is wanted ("how are the pigs doing?"): not out of
    scope, so the answer is the deterministic question with examples, not a refusal."""
    from resolver.lexicon import WORD_TO_DOMAIN
    tokens = set(re.findall(r"[a-z0-9]+", question.lower())) - _STOPWORDS
    return bool(tokens & (set(WORD_TO_DOMAIN) | _FARM_WORDS)) and not (tokens - set(WORD_TO_DOMAIN) - _FARM_WORDS)


def _has_subject(question):
    tokens = set(re.findall(r"[a-z0-9]+", question.lower()))
    return bool(tokens - _STOPWORDS)


def _farm(conn, farm_code):
    row = conn.execute("""SELECT currency, module_piggery_active, module_poultry_active, module_crops_active
                          FROM farm_profile WHERE farm_code = %s""", (farm_code,)).fetchone()
    if row is None:
        return "USD", None
    return row[0] or "USD", {"piggery": bool(row[1]), "poultry": bool(row[2]), "crops": bool(row[3])}


def _clarify(code, text, **kw):
    return V2Answer(text=text, kind="clarify", code=code, **kw)


def _refuse(code, text, claim=False, **kw):
    return V2Answer(text=text, kind="refusal", code=code, claim=claim, **kw)


def answer_question_v2(question: str, conn, llm, *, farm_code: str = "NIS-001", today=None, dashboard_filter=None,
                       week_start: int = 0, session: dict = None, quota_alert=alerts.report_quota_error) -> V2Answer:
    t0 = time.perf_counter()
    ans = _answer(question, conn, llm, farm_code, today or harare_today(), dashboard_filter, week_start, session, quota_alert)
    ans.seconds = time.perf_counter() - t0
    if session is not None and ans.kind == "answer" and ans.metric_id:
        session["last_metric"] = ans.metric_id
    return ans


def _answer(question, conn, llm, farm_code, today, dashboard_filter, week_start, session, quota_alert=None):
    q = (question or "").strip()
    norm = normalise(q)
    pending = session.pop("pending", None) if session is not None else None    # a question is only ever answered once

    # ---- fixed responses, no LLM
    if norm in _GREETINGS:
        return V2Answer(text=GREETING, kind="answer", code="greeting")
    if norm in _HELPS:
        return V2Answer(text=help_text(), kind="answer", code="help")
    if norm in _LIMITS:
        return V2Answer(text=limits_text(), kind="answer", code="help")

    # ---- a numbered reply to the clarifying question just asked
    reply = _REPLY.match(norm)
    if pending is not None and reply:
        n = int(reply.group(1))
        if not 1 <= n <= len(pending["values"]):
            session["pending"] = pending                                          # still waiting for a valid number
            return _clarify("reply_out_of_range", f"Please reply with a number from 1 to {len(pending['values'])}.",
                            metric_id=pending["spec"].metric, spec=pending["spec"])
        value = pending["values"][n - 1]
        if pending.get("memory_key"):                                             # asked and answered: do not ask again
            session.setdefault("metric_choice", {})[pending["memory_key"]] = value
        return _continue(pending["question"], conn, pending["llm"], pending["spec"], farm_code, today, dashboard_filter,
                         week_start, session, choice=(pending["code"], value))
    if reply:                                                                    # a bare number with nothing to answer
        return _clarify("no_question_to_answer", refusals.NO_SUBJECT)
    if not _has_subject(q):
        return _clarify("no_subject", refusals.NO_SUBJECT)

    # ---- which metric? a follow-up reuses the previous one; otherwise one LLM call
    spec, llm_res = None, None
    if _FOLLOW_UP.match(norm):
        last = (session or {}).get("last_metric")
        if not last:
            return _clarify("follow_up_without_context", refusals.FOLLOW_UP_WITHOUT_CONTEXT)
        spec = RoutedSpec(metric=last, follow_up=True)
    else:
        llm_res = llm.route(system_prompt(), user_prompt(q), json_schema())
        if llm_res.ok:
            spec = parse(llm_res.data, q)
            if not spec.valid:
                return _clarify("invalid_spec", refusals.COULD_NOT_READ, spec=spec, llm=llm_res, notes=spec.problems)
        else:
            # OUTAGE FALLBACK ONLY (plan section 22): the model could not be used, so a question that exactly matches one of the few
            # known phrases is answered by the registry; anything else is told the truth, never guessed.
            if llm_res.error == "InsufficientQuota" and quota_alert is not None:     # logged, and emailed once a day (router/alerts.py)
                quota_alert(conn, llm_res, farm_code=farm_code)
            exact = EXACT_PHRASES.get(norm)
            if exact is None:
                busy = is_transient(llm_res.error)
                return _refuse("llm_busy" if busy else "llm_unavailable", refusals.LLM_BUSY if busy else refusals.LLM_DOWN,
                               llm=llm_res, notes=[llm_res.error, f"attempts={llm_res.attempts}"])
            spec = RoutedSpec(metric=exact[0], domains=exact[1])
    return _continue(q, conn, llm_res, spec, farm_code, today, dashboard_filter, week_start, session)


def _remember(session, q, llm_res, spec, code, options, values, memory_key=None):
    """Keep the clarifying question that was just asked, so the user's reply can be applied to it. `memory_key` names a choice between
    two metrics that, once made, is remembered for the rest of the conversation."""
    if session is not None:
        session["pending"] = {"question": q, "llm": llm_res, "spec": spec, "code": code, "options": options, "values": values,
                              "memory_key": memory_key}


def _continue(q, conn, llm_res, spec, farm_code, today, dashboard_filter, week_start, session, choice=None):
    """Everything after the spec exists. `choice` is (clarification code, the value the user picked) when this is the reply to a
    clarifying question; that one disagreement is settled by the user, every other check still runs."""
    currency, modules = _farm(conn, farm_code)
    chosen_code, chosen = choice if choice else (None, None)
    if chosen_code == "claim":                                        # the reply to "the nearest tracked metric, or not tracked?"
        if chosen == "not_tracked":
            code = spec.refusal or "out_of_scope"
            return _refuse(code, refusals.text(code), claim=refusals.kind(code) == "claim", spec=spec, llm=llm_res)
        chosen_code = "metric"
        from resolver.lexicon import domain_words_in           # the model gave no reading for this metric: the user's own words do
        spec = dataclasses.replace(spec, metric=chosen, refusal=None, domains=domain_words_in(q)[0])
    if chosen_code in ("ambiguous_metric", "metric"):
        spec = dataclasses.replace(spec, metric=chosen, ambiguous_between=(), refusal=None)

    # ---- money the farm owes others is not tracked, whatever the model picked
    if crosscheck.accounts_payable_wording(q):
        return _refuse("accounts_payable", refusals.text("accounts_payable"), claim=True, spec=spec, llm=llm_res)

    # ---- what an individual is paid is withheld by policy, whatever the model picked
    if crosscheck.staff_pay_wording(q):
        return _refuse("staff_pay", refusals.text("staff_pay"), claim=False, spec=spec, llm=llm_res)

    # ---- the model says nothing fits, or cannot decide between metrics
    if spec.ambiguous_between:
        remembered = ((session or {}).get("metric_choice") or {}).get(tuple(sorted(spec.ambiguous_between)))
        if remembered:                                                          # asked and answered earlier in this conversation
            spec = dataclasses.replace(spec, metric=remembered, ambiguous_between=())
        else:
            ids = list(spec.ambiguous_between[:3])
            opts = [crosscheck.option(m) for m in ids]
            text = crosscheck._numbered("I can read that more than one way. Do you mean:", opts)
            _remember(session, q, llm_res, spec, "ambiguous_metric", opts, ids, tuple(sorted(spec.ambiguous_between)))
            return _clarify("ambiguous_metric", text, spec=spec, llm=llm_res)
    if spec.metric is None:
        code = spec.refusal or "out_of_scope"
        if code == "out_of_scope" and _vague_about_the_farm(q):
            return _clarify("no_subject", refusals.NO_SUBJECT, spec=spec, llm=llm_res)
        near = crosscheck.NEAR_METRIC.get(code)
        backed = crosscheck.refusal_supported(code, q)
        if near and (not backed or (code == "current_sickness" and crosscheck.sickness_vs_treatment(q))):
            opts = [crosscheck.option(near), crosscheck.NOT_TRACKED_OPTION[code]]
            _remember(session, q, llm_res, spec, "claim", opts, [near, "not_tracked"])
            return _clarify("claim_or_metric", crosscheck._numbered("Do you mean:", opts), spec=spec, llm=llm_res, notes=[code])
        if not backed:                                                         # the model alone never says "not tracked"
            return _clarify("refusal_not_supported", refusals.COULD_NOT_READ, spec=spec, llm=llm_res, notes=[code])
        return _refuse(code, refusals.text(code), claim=refusals.kind(code) == "claim", spec=spec, llm=llm_res)

    metric = REGISTRY[spec.metric]
    bad = None if chosen_code in ("ambiguous_metric", "metric") else crosscheck.metric_disagreement(q, spec)
    if bad and sorted(bad.values) == sorted(crosscheck.FEED_PAIR):                # a feed-spend question asked and answered before
        remembered = ((session or {}).get("metric_choice") or {}).get(tuple(sorted(crosscheck.FEED_PAIR)))
        if remembered:
            spec, metric, bad = dataclasses.replace(spec, metric=remembered), REGISTRY[remembered], None
    if bad:
        _remember(session, q, llm_res, spec, "metric", bad.options, bad.values,
                  tuple(sorted(crosscheck.FEED_PAIR)) if sorted(bad.values) == sorted(crosscheck.FEED_PAIR) else None)
        return _clarify("disagree_metric", bad.message, metric_id=spec.metric, spec=spec, llm=llm_res)

    # ---- scope: the resolver reads the period and domains from the same words
    res = resolve(q, metric, today=today, dashboard_filter=dashboard_filter, modules=modules, week_start=week_start)
    if not res.ok:
        u = res.unresolved
        if u.code in ("month_without_year", "multiple_periods"):
            return _clarify(u.code, u.message, metric_id=spec.metric, spec=spec, llm=llm_res)
        return _refuse(u.code, u.message, metric_id=spec.metric, spec=spec, llm=llm_res)

    if res.scope.batch_code and not spec.follow_up:                                 # a batch code the farm does not have
        known = [r[0] for r in conn.execute("SELECT batch_code FROM pig_batches UNION ALL SELECT batch_code FROM poultry_batches ORDER BY 1")]
        if res.scope.batch_code not in known:
            import difflib
            squash = lambda c: c.replace("-", "").upper()
            close = difflib.get_close_matches(squash(res.scope.batch_code), [squash(k) for k in known], n=1, cutoff=0.7)
            guess = next((k for k in known if close and squash(k) == close[0]), None)
            return _clarify("unknown_batch", f"I don't see a batch {res.scope.batch_code}."
                            + (f" Did you mean {guess}?" if guess else "") + f" The batches are: {', '.join(known)}.",
                            metric_id=spec.metric, spec=spec, llm=llm_res)

    if not spec.follow_up:
        problems = [d for d in crosscheck.check(q, spec, metric, res, dashboard_filter) if d.code != chosen_code]
        if problems:
            d = problems[0]
            _remember(session, q, llm_res, spec, d.code, d.options, d.values)
            return _clarify(f"disagree_{d.code}", d.message, metric_id=spec.metric, spec=spec, llm=llm_res,
                            notes=[p.code for p in problems])

    # ---- what the user picked is applied to the scope the resolver built
    if chosen_code == "dimension":
        spec = dataclasses.replace(spec, dimension=chosen)
    scope = res.scope
    if chosen_code == "domain":
        scope = scope.with_(domains=tuple(chosen) or None)
    elif chosen_code in ("period", "all_time") and chosen == "all_time":
        scope = all_time_scope(scope)
        res = dataclasses.replace(res, scope=scope, period_source="all_time", period_label=None, filter_applied=False,
                                  offer_all_time_hint=False)
    elif chosen_code == "aggregation":
        scope = scope.with_(aggregation=chosen[0], grain=chosen[1])

    # ---- metric-specific parts of the scope (the resolver does not read these)
    scope = scope.with_(dimension=spec.dimension)
    if spec.category_text and spec.metric == "expenses":
        cats = farm_categories(conn)
        category = match_category(spec.category_text, cats)
        if category is None:
            return _clarify("unknown_category", f"I don't see an expense category called '{spec.category_text}'. "
                            f"The categories are: {', '.join(cats)}.", metric_id=spec.metric, spec=spec, llm=llm_res)
        scope = scope.with_(category=category)

    result = compute(spec.metric, conn, scope)
    allt = compute(spec.metric, conn, all_time_scope(scope)) if res.offer_all_time_hint else None
    ctx = RenderContext(currency=currency, data_through=latest_log_date(conn), all_time_result=allt)
    return V2Answer(text=render(res, result, ctx), kind="answer", code=result.status, metric_id=spec.metric, scope=scope,
                    spec=spec, llm=llm_res)
