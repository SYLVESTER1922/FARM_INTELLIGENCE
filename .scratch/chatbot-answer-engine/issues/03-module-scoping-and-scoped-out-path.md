# 03: Module scoping + the scoped_out refusal path

**What to build:** A farm owner asking about a module they've turned off gets a clear,
honest refusal explaining why — distinct from "I don't understand you" — and that refusal
is logged in a way that's analyzable separately from genuine catalog gaps.

**Blocked by:** 01, 02 (needs domain-specific queries — the poultry/piggery findings — to
scope against; the cross-domain feed-cost query alone can't prove single-module refusal)

**Status:** done

- [x] After intent resolution succeeds (tier 1, for this ticket's scope), a single
      uniform check compares the resolved query's domain(s) against
      `00_FARM_PROFILE.module_piggery_active` / `module_poultry_active` /
      `module_crops_active`. (`chatbot/catalog.py` gained a `domains` field per
      `CatalogQuery`; `_find_inactive_domain` in `chatbot/engine.py` is the one check,
      run before SQL execution regardless of which query matched.)
- [x] Asking about the poultry finding (or piggery finding) when that module is active
      answers normally, unaffected by the scoping check.
      (`test_answer_question_answers_normally_when_module_active`)
- [x] Asking about the poultry finding when `module_poultry_active = No` (test fixture
      with that flag off) returns the deterministic `scoped_out` template — never
      LLM-phrased — explaining that the module is turned off.
      (`test_answer_question_scopes_out_when_module_inactive`)
- [x] The `scoped_out` case logs `intent_source` as whichever tier resolved it, `query_id`
      populated with the resolved query, `failure_reason` null, and `scoped_out_reason`
      set to the module name (`piggery` / `poultry` / `crops`) — not a boolean, and not a
      renamed `inactive_module` constant. (`test_scoped_out_query_log_row`)
- [x] **Cross-domain query rule** (the feed-cost-split query touches both piggery and
      poultry at once, which the spec didn't explicitly resolve): a cross-domain query is
      scoped out if *any* domain it touches has an inactive module, not only if all of
      them do — consistent with the workbook's stated purpose of refusing entirely rather
      than silently returning a partial cross-domain answer. `scoped_out_reason` records
      whichever inactive module triggered the refusal.
      (`test_cross_domain_query_scoped_out_when_either_domain_inactive` — piggery active,
      poultry inactive; asserts the piggery-only partial dollar figure never leaks into
      the refusal text. Passed on the first run: `_find_inactive_domain` iterates every
      domain in order and returns the first inactive one, which already generalized to
      "any" rather than "all" without needing a separate implementation.)
- [x] Tests go entirely through the `answer_question` seam, against real Postgres. The
      `scoped_out` refusal tests are zero-LLM (the refusal template is never phrased by
      OpenAI); the "active module, answers normally" tests still make a real OpenAI call
      for phrasing, same as ticket 01's success-path tests.
