# 01: Answer-engine foundation: one seam, one query, query_log

**What to build:** The whole `answer_question` pipeline shape, proven on the smallest
possible scope. A farm owner can ask the feed-cost-split question in plain language and
get a correctly phrased answer computed from the real query catalog's SQL (never from LLM
arithmetic on raw rows); an unrelated or incomplete question gets an honest refusal, not a
guess. Every call — answered or not — is logged.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `answer_question(question, farm_code, dsn) -> Answer` exists as the single public
      seam; nothing else needs to be called externally to get an answer.
- [ ] The `query_log` table is created idempotently (`CREATE TABLE IF NOT EXISTS`,
      matching `sync/engine.py`'s convention) with columns: timestamp, `farm_code`,
      `question_text`, `intent_source`, `query_id`, `failure_reason`,
      `scoped_out_reason`.
- [ ] The query catalog contains exactly one entry to start: the feed-cost-split-by-domain
      query (the same logic already proven in `tests/test_sync_shared_core.py`), with a
      declared `query_id`, its required parameters, and a curated phrase cluster
      (multiple example phrasings of the same question).
- [ ] The tier-1 deterministic matcher is pure Python (no LLM call, no network call) and
      matches a question against the catalog's phrase clusters via normalized
      substring/token-overlap logic.
- [ ] Asking a phrasing that matches the cluster, with all required parameters present in
      the question, returns a correctly phrased answer whose numbers match the query's
      real SQL output, and logs `intent_source=deterministic`, `query_id` populated,
      `failure_reason` and `scoped_out_reason` both null.
- [ ] Asking a question that matches the cluster but omits a required parameter returns
      the deterministic "I can't answer that yet" template and logs
      `intent_source=unresolved`, `failure_reason=missing_parameter`, `query_id` null.
- [ ] Asking an unrelated question (matches no cluster at all) returns the same refusal
      template and logs `intent_source=unresolved`, `failure_reason=no_match`, `query_id`
      null.
- [ ] The refusal template returned for `unresolved` never invokes any LLM call.
- [ ] The phrasing step (for the success case) is a real OpenAI call whose prompt
      receives only the already-computed final result of the query's execution — never
      raw row-level data. Phrasing is an LLM call for every successful answer regardless
      of which tier resolved the intent (this ticket only covers tier 1); it is not
      something "zero LLM calls" ever applies to.
- [ ] `query_log` writes are fire-and-forget: a simulated write failure never blocks or
      fails the returned `Answer`.
- [ ] Tests go entirely through the `answer_question` seam, against a real Postgres
      instance, matching this repo's existing black-box testing discipline
      (`tests/test_sync_*.py`). **"Zero LLM calls" applies only to the pure-refusal
      tests** (`unresolved` cases: no match, ambiguous, missing parameter) — intent
      resolution itself is zero-LLM in this ticket's scope (tier 1 only, no fallback
      yet), but every success-path test still makes one real OpenAI call for phrasing.
