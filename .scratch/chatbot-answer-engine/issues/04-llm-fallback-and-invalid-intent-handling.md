# 04: LLM fallback tier + invalid-intent handling

**What to build:** A farm owner phrasing a question in a way the deterministic catalog
doesn't recognize still gets a correct answer, via a single real LLM call — and if the
LLM's interpretation doesn't check out against the same closed vocabulary the
deterministic path uses, the system refuses rather than trusting a hallucinated answer.

**Blocked by:** 01, 02, 03

**Status:** done

- [x] When tier 1 doesn't produce a complete, unambiguous match (`no_match`, `ambiguous`,
      or `missing_parameter`), a single OpenAI (GPT-4o-mini) call attempts structured-intent
      extraction (`query_id` + parameters) from the question before falling back to
      `unresolved`. (`chatbot/fallback.py`, wired into `answer_question`)
- [x] The LLM's structured intent is validated against the same closed vocabularies tier
      1 uses (known `query_id`s, known domain/parameter values) before it's trusted.
      (`validate_llm_intent`, reuses `chatbot/matcher.py`'s `PARAM_EXTRACTORS` for
      parameter parsing rather than trusting the LLM's own date logic)
- [x] A valid fallback intent reaches the same query catalog and phrasing step as a
      tier-1 match, produces a correct answer, and logs `intent_source=llm_fallback`,
      `query_id` populated.
      (`test_llm_fallback_answers_a_rephrased_question_tier1_misses` — real OpenAI call,
      question deliberately phrased to miss every tier-1 cluster)
- [x] An invalid/hallucinated fallback intent (e.g. naming an unknown `query_id` or
      domain) is caught by validation and logs `intent_source=unresolved`,
      `failure_reason=invalid_llm_intent` — never executed as SQL.
      **Deviation, agreed with the user before writing the test**: empirically, GPT-4o-mini
      given the extraction prompt never hallucinates an unknown `query_id` — it either
      resolves correctly or honestly declines, even under mild adversarial prompting (see
      probe results in the session). That makes this branch untestable via a live,
      unscripted API call. Tested instead via `tests/test_chatbot_fallback_validation.py`,
      a deterministic unit test directly on `validate_llm_intent` with a hand-constructed
      "as if the LLM said this" dict — a narrow, justified second seam (validating our own
      closed-vocabulary check, not model behavior), not a silent black-box violation.
- [x] No retry loop: a single LLM call is attempted per question; a validation miss goes
      straight to `unresolved`, not a second attempt. (structurally guaranteed - one
      `llm_extract_intent` call, no loop, in `answer_question`)
- [x] A fallback-resolved intent for an inactive module is scoped out the same way a
      tier-1-resolved one is (ticket 03's mechanism applies uniformly regardless of tier)
      — proving "module scoping enforced once, uniformly" actually holds across tiers,
      not just within tier 1.
      (`test_llm_fallback_resolved_intent_is_still_scoped_out_when_module_inactive` —
      passed immediately, since ticket 03's scoping check was already shared across both
      code paths by design)
- [x] A small number of tests (not exhaustive scenario coverage) call the real OpenAI API
      end-to-end: at least one proving a valid fallback produces a correct answer, and one
      proving an invalid fallback intent is caught and logged, not trusted (the latter via
      the unit-test deviation above, since the live model won't cooperate).
- [x] All tier-1-only tests from tickets 01-03 continue to pass unmodified — tier 2 only
      activates when tier 1 doesn't produce a complete match.

**Real semantic gap found and fixed while implementing this ticket**: my first pass
collapsed "the LLM honestly declines (`query_id: null`)" and "the LLM names an unknown
`query_id`" into the same `invalid_llm_intent` reason, which broke every tier-1-only
`unresolved` test — the fallback attempt was overwriting `no_match`/`ambiguous`/
`missing_parameter` with `invalid_llm_intent` even when the LLM correctly agreed nothing
matched. Fixed by threading tier 1's original reason through to `validate_llm_intent` and
only using `invalid_llm_intent` for a genuinely unknown `query_id` or a named query whose
required parameter is present-but-unparseable; a *missing* required parameter (the LLM
correctly identifying the right query but the question genuinely lacking the info) now
resolves to `missing_parameter`, the same root-cause label tier 1 uses, not
`invalid_llm_intent`. This is exactly what "all tier-1-only tests continue to pass
unmodified" was checking for.
