# 04: LLM fallback tier + invalid-intent handling

**What to build:** A farm owner phrasing a question in a way the deterministic catalog
doesn't recognize still gets a correct answer, via a single real LLM call — and if the
LLM's interpretation doesn't check out against the same closed vocabulary the
deterministic path uses, the system refuses rather than trusting a hallucinated answer.

**Blocked by:** 01, 02, 03

**Status:** ready-for-agent

- [ ] When tier 1 doesn't produce a complete, unambiguous match (`no_match`, `ambiguous`,
      or `missing_parameter`), a single OpenAI (GPT-4o-mini) call attempts structured-intent
      extraction (`query_id` + parameters) from the question before falling back to
      `unresolved`.
- [ ] The LLM's structured intent is validated against the same closed vocabularies tier
      1 uses (known `query_id`s, known domain/parameter values) before it's trusted.
- [ ] A valid fallback intent reaches the same query catalog and phrasing step as a
      tier-1 match, produces a correct answer, and logs `intent_source=llm_fallback`,
      `query_id` populated.
- [ ] An invalid/hallucinated fallback intent (e.g. naming an unknown `query_id` or
      domain) is caught by validation and logs `intent_source=unresolved`,
      `failure_reason=invalid_llm_intent` — never executed as SQL.
- [ ] No retry loop: a single LLM call is attempted per question; a validation miss goes
      straight to `unresolved`, not a second attempt.
- [ ] A fallback-resolved intent for an inactive module is scoped out the same way a
      tier-1-resolved one is (ticket 03's mechanism applies uniformly regardless of tier)
      — proving "module scoping enforced once, uniformly" actually holds across tiers,
      not just within tier 1.
- [ ] A small number of tests (not exhaustive scenario coverage) call the real OpenAI API
      end-to-end: at least one proving a valid fallback produces a correct answer, and one
      proving an invalid fallback intent is caught and logged, not trusted.
- [ ] All tier-1-only tests from tickets 01-03 continue to pass unmodified — tier 2 only
      activates when tier 1 doesn't produce a complete match.
