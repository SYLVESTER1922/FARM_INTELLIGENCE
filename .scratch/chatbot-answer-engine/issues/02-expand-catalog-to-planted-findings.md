# 02: Expand the catalog to the three planted findings

**What to build:** A farm owner can ask about the poultry mortality spike, the piggery
disease outbreak, or the unpaid crop sale, in plain language, and get a correct answer for
each — proving the pattern from ticket 01 generalizes to a multi-entry catalog, including
the case where two clusters could plausibly both match a question.

**Blocked by:** 01

**Status:** done

- [x] Three more catalog entries added: poultry mortality spike (`poultry_mortality_spike`,
      finds `BRO-P02`-style batches by highest mortality %), piggery disease outbreak
      (`piggery_disease_outbreak`, finds `PIG-B02`-style batches by treatment count),
      crop debtor (`crop_debtor`, lists `Owing` crop sales) — each with a declared
      `query_id` and a curated phrase cluster. None needed `required_params` (unlike
      ticket 01's `feed_cost_split`) — they're all general lookups, not date-scoped.
      (`chatbot/catalog.py`)
- [x] Each of the three is answerable end-to-end via the tier-1 matcher alone, with
      correct phrasing and correct `query_log` rows (`intent_source=deterministic`,
      correct `query_id`).
      (`test_answer_question_answers_poultry_mortality_spike`,
      `test_answer_question_answers_piggery_disease_outbreak`,
      `test_answer_question_answers_crop_debtor`)
- [x] A question deliberately crafted to plausibly match two clusters at once (e.g.
      overlapping vocabulary between two of the now-four catalog entries) logs
      `intent_source=unresolved`, `failure_reason=ambiguous`, `query_id` null — and the
      system does not guess between the two candidates.
      (`test_answer_question_returns_ambiguous_for_overlapping_question` — added the
      phrase "is something wrong with a batch" to both `poultry_mortality_spike` and
      `piggery_disease_outbreak`'s clusters; a genuinely vague real question, not an
      artificial construction)
- [x] All of ticket 01's acceptance criteria still pass against the now-four-entry
      catalog (no regression in the single-match or no-match cases).

**Real bug found and fixed while implementing this ticket**: the phrasing prompt from
ticket 01 only instructed the model to preserve numeric values exactly, not identifiers.
The first `piggery_disease_outbreak` test run correctly resolved to batch `PIG-B02` in
SQL, but the LLM's phrased answer described the treatment cost without ever naming the
batch. Fixed by rewriting the phrasing prompt to require every field in the computed
data - identifiers and labels, not just numbers - be included verbatim. Confirmed stable
across 3 repeated runs afterward. This is exactly the kind of gap the real-API testing
strategy (agreed before ticket 01) was meant to catch.
