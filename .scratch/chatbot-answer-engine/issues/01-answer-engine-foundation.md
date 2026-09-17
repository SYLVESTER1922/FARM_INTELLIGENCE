# 01: Answer-engine foundation: one seam, one query, query_log

**What to build:** The whole `answer_question` pipeline shape, proven on the smallest
possible scope. A farm owner can ask the feed-cost-split question in plain language and
get a correctly phrased answer computed from the real query catalog's SQL (never from LLM
arithmetic on raw rows); an unrelated or incomplete question gets an honest refusal, not a
guess. Every call — answered or not — is logged.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] `answer_question(question, farm_code, dsn) -> Answer` exists as the single public
      seam; nothing else needs to be called externally to get an answer.
      (`chatbot/engine.py`)
- [x] The `query_log` table is created idempotently (`CREATE TABLE IF NOT EXISTS`,
      matching `sync/engine.py`'s convention) with columns: timestamp, `farm_code`,
      `question_text`, `intent_source`, `query_id`, `failure_reason`,
      `scoped_out_reason`. (`_ensure_query_log_table`)
- [x] The query catalog contains exactly one entry to start: the feed-cost-split-by-domain
      query (the same logic already proven in `tests/test_sync_shared_core.py`), with a
      declared `query_id`, its required parameters, and a curated phrase cluster
      (multiple example phrasings of the same question). (`chatbot/catalog.py` — required
      a `period` parameter, an explicit `<Month> <Year>` phrase, since the ticket also
      needed a genuine `missing_parameter` case to test against.)
- [x] The tier-1 deterministic matcher is pure Python (no LLM call, no network call) and
      matches a question against the catalog's phrase clusters via normalized
      substring/token-overlap logic. (`chatbot/matcher.py`)
- [x] Asking a phrasing that matches the cluster, with all required parameters present in
      the question, returns a correctly phrased answer whose numbers match the query's
      real SQL output, and logs `intent_source=deterministic`, `query_id` populated,
      `failure_reason` and `scoped_out_reason` both null.
      (`test_answer_question_answers_feed_cost_split`,
      `test_answer_question_logs_query_log_row_for_success`)
- [x] Asking a question that matches the cluster but omits a required parameter returns
      the deterministic "I can't answer that yet" template and logs
      `intent_source=unresolved`, `failure_reason=missing_parameter`, `query_id` null.
      (`test_answer_question_returns_missing_parameter_when_no_month_given`)
- [x] Asking an unrelated question (matches no cluster at all) returns the same refusal
      template and logs `intent_source=unresolved`, `failure_reason=no_match`, `query_id`
      null. (`test_answer_question_returns_unresolved_for_unrelated_question`)
- [x] The refusal template returned for `unresolved` never invokes any LLM call —
      structurally guaranteed (the `unresolved` branch returns before `_phrase()` is ever
      called) and confirmed by the no_match/missing_parameter tests never hitting OpenAI.
- [x] The phrasing step (for the success case) is a real OpenAI call whose prompt
      receives only the already-computed final result of the query's execution — never
      raw row-level data (the SQL's own `GROUP BY` already aggregates; `computed` holds
      only the grouped rows, never per-day log rows).
- [x] `query_log` writes are fire-and-forget: a simulated write failure never blocks or
      fails the returned `Answer`. (`test_query_log_write_failure_never_breaks_the_answer`
      — sabotages the table mid-test and confirms the answer still comes back correctly)
- [x] Tests go entirely through the `answer_question` seam, against a real Postgres
      instance. "Zero LLM calls" holds for the no_match/missing_parameter tests; the
      success-path tests each make one real OpenAI call for phrasing, as corrected before
      implementation started.

**Provider note**: implemented against OpenAI GPT-4o-mini, not Claude — see the
`Switch LLM provider` commit; the spec and all four tickets were updated before any code
was written against the old provider.
