# 03: Module scoping + the scoped_out refusal path

**What to build:** A farm owner asking about a module they've turned off gets a clear,
honest refusal explaining why — distinct from "I don't understand you" — and that refusal
is logged in a way that's analyzable separately from genuine catalog gaps.

**Blocked by:** 01, 02 (needs domain-specific queries — the poultry/piggery findings — to
scope against; the cross-domain feed-cost query alone can't prove single-module refusal)

**Status:** ready-for-agent

- [ ] After intent resolution succeeds (tier 1, for this ticket's scope), a single
      uniform check compares the resolved query's domain(s) against
      `00_FARM_PROFILE.module_piggery_active` / `module_poultry_active` /
      `module_crops_active`.
- [ ] Asking about the poultry finding (or piggery finding) when that module is active
      answers normally, unaffected by the scoping check.
- [ ] Asking about the poultry finding when `module_poultry_active = No` (test fixture
      with that flag off) returns the deterministic `scoped_out` template — never
      LLM-phrased — explaining that the module is turned off.
- [ ] The `scoped_out` case logs `intent_source` as whichever tier resolved it, `query_id`
      populated with the resolved query, `failure_reason` null, and `scoped_out_reason`
      set to the module name (`piggery` / `poultry` / `crops`) — not a boolean, and not a
      renamed `inactive_module` constant.
- [ ] **Cross-domain query rule** (the feed-cost-split query touches both piggery and
      poultry at once, which the spec didn't explicitly resolve): a cross-domain query is
      scoped out if *any* domain it touches has an inactive module, not only if all of
      them do — consistent with the workbook's stated purpose of refusing entirely rather
      than silently returning a partial cross-domain answer. `scoped_out_reason` records
      whichever inactive module triggered the refusal.
- [ ] Tests go entirely through the `answer_question` seam, against real Postgres. The
      `scoped_out` refusal tests are zero-LLM (the refusal template is never phrased by
      OpenAI); the "active module, answers normally" tests still make a real OpenAI call
      for phrasing, same as ticket 01's success-path tests.
