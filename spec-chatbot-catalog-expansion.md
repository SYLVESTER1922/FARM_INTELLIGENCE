# Spec: Chatbot catalog expansion (tier-3 tool-calling + tier-0 help)

## Problem Statement

Farm Intelligence's chat currently answers only 4 fixed question types (the tier-1/tier-2
catalog: `feed_cost_split`, `poultry_mortality_spike`, `piggery_disease_outbreak`,
`crop_debtor`). Real usage, captured in the app's own `query_log`, shows this is too
narrow: 24 of 47 logged questions failed to resolve. Several of those failures are
questions the farm's data can genuinely answer today but nothing is wired up for them
("how many pigs do we have?", "how many hectares of crop is planted?", "what's the
weather like today?" — `weather_log` is synced with zero query coverage). Others are
bare greetings or "what can you ask" questions that get the same unhelpful generic
refusal as a real data question the app can't answer. And the refusal itself can't
distinguish "we don't track that at all" (e.g. accounts payable — money the farm owes
suppliers, a different thing from `revenue.payment_status='Owing'`, which tracks money
owed *to* the farm) from "we have this data but haven't built a query for it yet" —
today both produce the identical generic message.

The obvious fix — let the LLM write and run its own SQL against the database — is
explicitly rejected as a real safety/correctness risk: wrong queries, hallucinated
columns or tables, no guardrails against a bad generated query actually reaching
Postgres.

## Solution

Expand the chatbot to answer a much wider range of real questions the data can support,
without ever letting an LLM generate or execute its own SQL. This is done by adding a
new **tier-3**: a small, curated, growing set of named Python query functions (the same
"real query runs first, LLM only narrates the result" principle the existing catalog
already upholds), registered as OpenAI tools so GPT-4o-mini picks which one applies to
a given question and supplies only filter *values* — never table names, column names,
or SQL text. This mirrors the actual architecture two sibling Netrisyl products
(Savanna QSR Intelligence, Lobels Stores Intelligence) already run in production: both
register ~10-12 medium-granularity tool functions this way, and neither writes SQL.

Alongside tier-3, a tiny **tier-0** handles bare greetings and "what can you ask"
questions with a fixed, honest, canned response — a third of real logged failures were
exactly this, and it's a different problem (conversational UX) from data-query coverage,
so it's solved with the cheapest possible mechanism (reusing tier-1's existing
phrase-matching, not new machinery) rather than folded into tier-3's tool-calling.

The existing tier-1/tier-2 catalog, its 4 entries, and the public `answer_question` seam
are all unchanged. Tier-3 is invisible behind that same seam — from the rest of the
codebase's perspective, the chatbot just answers more questions than it used to.

## User Stories

1. As a farm owner, I want to ask "how many pigs do we have?" and get a real, current
   answer, so that I don't have to know the app doesn't cover that question today.
2. As a farm owner, I want to ask "how many hectares of crop is planted?" and get a real
   answer computed from the actual plantings data, not a refusal.
3. As a farm owner, I want to ask "what's the weather like today?" and get a real answer
   from the weather log that's already being synced but never queried.
4. As a farm owner, I want a question outside the app's supported data (e.g. "do we owe
   anyone money?" — accounts payable) to get an honest "we don't track that" answer that
   names what's actually different about it, not the same generic refusal as any other
   unanswerable question.
5. As a farm owner, I want a question about data the app tracks but hasn't built a query
   for yet to be distinguishable, in the app's own understanding, from a question about
   data the app genuinely never captures — even if both currently render as "can't
   answer yet" to me, so the gap is fixable rather than a permanent wall.
6. As a farm owner, I want to say "hi" or ask "what can you ask?" and get a helpful,
   on-brand response, not the same generic failure message as an unanswerable data
   question.
7. As a farm owner, when I ask a *known* question type but leave out a detail it needs
   (e.g. "how does feed cost split between pigs and chickens" with no month), I want to
   be asked specifically for the missing detail, not given a generic "can't answer" as
   if the question weren't understood at all.
8. As a farm owner, when I've selected a date range in the global filter and ask a
   newly-added tier-3 question, I want the answer scoped to that range, exactly like the
   4 original catalog questions already are.
9. As a farm owner, if I ask about a domain (piggery/poultry/crops) whose module is
   turned off for my farm, I want that refusal to hold regardless of which tier of the
   chatbot would otherwise have answered it.
10. As a farm owner, I never want a chat answer to contain a number the underlying data
    doesn't actually support — this must hold for every new tier-3 question exactly as
    it already holds for the 4 existing ones.
11. As the developer, I want tier-3's tool functions to be safe by construction — every
    database value they touch goes through parameterized queries, and any argument that
    should only ever be one of a fixed set of values (a domain name, say) is validated
    against that list before the query runs, so a nonsensical LLM-supplied argument fails
    cleanly instead of silently returning an empty or wrong result.
12. As the developer, I want to see which tier-3 tool (and which arguments) real
    questions actually trigger, via `query_log`, so I can decide which tool to add next
    based on real evidence instead of guessing, the same way this expansion itself was
    grounded in real logged failures.
13. As the developer, I want tier-3 tool-selection correctness to be directly testable,
    not just inferable from the final narrated answer, so that adding tool #13 someday
    can't silently break which tool gets picked for tool #4's intended phrasing without
    a test catching it.
14. As the developer, I want this expansion to leave chat one-shot (no conversation
    memory) exactly as it is today — multi-turn is a separate, deliberately deferred
    piece of scope, not bundled into this change just because both sibling products
    happen to support it.
15. As the developer, I want the three starter tier-3 tools chosen from real evidence
    (the app's own `query_log`), not from guessing at what farm owners might want to ask.
16. As a farm owner, I want every answer's numbers - old catalog or new tier-3 alike - to
    come from a real, already-computed query result, with the LLM only ever narrating
    that result in plain language, never inventing or recomputing a figure itself.

## Implementation Decisions

- **Tier architecture**: tier-0 (greeting/help) → tier-1 (deterministic matcher) →
  tier-2 (LLM-validated catalog fallback) → tier-3 (tool-calling). Each tier is tried in
  order; the first to produce a confident result answers. Tier-3 is reached only when
  tier-1 and tier-2 both produce a true `no_match` or `ambiguous` result — never on
  `missing_parameter` (see below) or a `scoped_out` result from an earlier tier.
- **Tier-0 (help/greetings)**: a fixed, small set of greeting/capability phrase patterns
  checked via the same phrase-matching mechanism tier-1 already uses (not new matching
  logic), before tier-1's real catalog matching runs. Returns a canned, honest response
  describing what the chatbot can actually answer. Zero LLM calls.
- **Tier-3 tool registration**: medium-granularity named functions (not one function per
  exact phrasing, not a single maximal generic "aggregate metric X by dimension Y"
  primitive), registered as OpenAI tools with `tool_choice="auto"`, matching the actual
  pattern already proven in production by Savanna QSR Intelligence and Lobels Stores
  Intelligence. Each tool's SQL shape is fixed at registration time; only filter values
  (a batch code, a date, a domain name) are supplied by the LLM.
- **Starter tool set for this pass** (three tools, chosen from real `query_log`
  evidence, not guessed): current pig/poultry headcount (reusing the existing "active
  as of a date" methodology already established for the dashboard's Active Headcount
  stat card, not a naive current-status read), total crop area planted (from the real
  planted-area figure already tracked per planting), and a weather-log lookup (a table
  that is already synced with zero existing query coverage). Tier-3 is a living catalog
  meant to grow from this starting point via the same evidence-driven process, not a
  one-time comprehensive sweep of the schema.
- **Argument validation**: every tier-3 tool executes through parameterized queries,
  never string-built SQL — free-text arguments (batch codes, material/crop names) are
  never pre-validated and are trusted to the database, which returns nothing for a value
  that doesn't exist, the same way an unmatched free-text lookup already behaves
  elsewhere in this codebase. Closed-vocabulary arguments (a domain name, or any other
  argument that should only ever be one of a fixed set of values) are validated against
  that fixed list before the query runs; a value outside it is treated as an invalid
  tool call, not executed.
- **No retry on invalid tool-call arguments**: a validation failure at tier-3 is a
  single, final failure for that tier, consistent with tier-2's existing "a validation
  miss here is a single, final failure" precedent. Tier-3 failing does not currently fall
  through to any further tier.
- **Module scoping for tier-3**: each tier-3 tool statically declares which domains
  (piggery/poultry/crops) it touches, at registration time, exactly like the existing
  catalog's `domains` field. The existing uniform scoping check (any touched domain
  inactive → scoped out) applies unchanged, regardless of tier. A `scoped_out` result
  from any tier is final for that question — it is never re-attempted at a later tier.
- **`missing_parameter` handling**: when tier-1 or tier-2 determines the question matches
  a *known* query type but is missing a required detail (e.g. a month), the chatbot
  responds with a targeted clarifying question naming the missing detail, instead of the
  generic unresolved message, and does not escalate to tier-3. This is a real gap fixed
  as part of this work: today's refusal text is currently identical for every failure
  reason.
- **Honest "not tracked" vs. "not yet wired" distinction**: a small, hand-maintained,
  curated description of what data the app tracks (domain by domain — not a live
  database schema introspection, and never raw table/column names surfaced to the
  farm owner) is what both informs tier-3's tool selection and shapes the refusal
  wording when nothing matches, so a genuinely untracked concept (accounts payable) can
  be named honestly as different from a tracked-but-unqueried one. This mirrors the
  existing catalog's own curation style (hand-written phrase clusters), kept manually in
  sync with the schema rather than auto-derived from it.
- **Date-range filter**: tier-3 respects the globally-selected date range using the same
  mechanism tiers 1-2 already use — each tier-3 tool that supports date filtering
  declares which column its filter applies to, and the currently-selected range is
  injected into its query the same way it already is for the 4 existing catalog entries.
  Tools do not take LLM-suppliable date arguments of their own; the LLM only reasons
  about dates when a question names one directly (e.g. "in March"), which continues to
  narrow *within* whatever range is currently selected, unchanged from today.
- **No multi-turn**: chat remains one-shot. Tier-3 does not thread conversation history
  into its LLM calls, even though both reference products (Savanna, Lobels) do this in
  their own chat implementations. This is deliberately excluded from this pass.
- **Observability**: `query_log` gains the ability to record, for a tier-3 hit, which
  tool was selected and its validated arguments (structured, safe data — not
  LLM-authored SQL text), alongside the existing fields already logged for every
  question.
- **New module boundary**: tier-3's tool registrations, dispatch, and argument
  validation live in a new module alongside the existing catalog module, keeping the
  existing catalog's tier-1/tier-2 code untouched. The public answer-engine seam's
  signature does not change.

## Testing Decisions

- **Primary seam, unchanged**: `answer_question(question, farm_code, dsn, date_from,
  date_to) -> Answer`. Every behavioral test — a tier-3 question resolving correctly, a
  `scoped_out` result holding regardless of which tier would have matched, a
  `missing_parameter` question getting the clarifying response instead of falling
  through to tier-3, a date-filtered tier-3 answer changing correctly when the range
  changes — goes through this one black-box seam, exactly as all existing tier-1/tier-2
  tests already do.
- **One narrow, explicitly-agreed secondary seam** for tier-3 tool *selection*
  specifically: a function that performs the tool-calling round-trip and returns which
  tool was chosen and with what arguments, tested directly with real questions against
  the real OpenAI API. This is the direct analogue of the existing precedent already
  established for tier-2 (`validate_llm_intent` tested directly, since the real model
  empirically won't misbehave on demand for that branch) — it is the only place
  tool-selection correctness can be asserted on without reaching into
  `answer_question`'s internals, and exists specifically to catch a new tool's
  registration silently changing which tool gets picked for an existing tool's intended
  phrasing.
- **No mocking**: real local Postgres for every test, a small number of tests against
  the real OpenAI API end-to-end, same established convention as every other layer of
  this codebase.
- **New assertion category**: for each tier-3 tool, at least one test asserting the
  correct tool (by name) is selected for a canonical real-world phrasing of the question
  it's meant to answer, in addition to the existing convention of asserting on final
  narrated answer content.
- **Argument-validation tests**: tests covering a tier-3 tool called with an invalid
  closed-vocabulary argument, confirming it fails cleanly (no query executed) rather than
  silently returning an empty or wrong result.

## Out of Scope

- Multi-turn conversation memory — explicitly deferred, a separate piece of scope from
  this expansion, even though both reference products support it.
- Full schema coverage — this pass ships three evidence-grounded starter tools, not a
  comprehensive sweep of the remaining 23-tab schema.
- Any form of LLM-generated or LLM-executed SQL, in any constrained or sandboxed form —
  ruled out entirely, not just deferred.
- Live database schema introspection as the mechanism for the chatbot's knowledge of
  what data exists — the hand-maintained data dictionary is the settled mechanism, not
  an interim step toward introspection.
- Retry logic for invalid tier-3 tool arguments — a single, final failure, matching
  tier-2's existing precedent.
- Accounts-payable tracking itself (money the farm owes suppliers) — this spec makes the
  chatbot able to say honestly that this isn't tracked; it does not add the tracking.

## Further Notes

This expansion was reached via a three-round `/grill-me` session that also formally
closed out a previously-parked round of unanswered questions from an earlier session
(SQL safety guardrails, schema-learning mechanism, module-scoping detection, `query_log`
fields, testing strategy, retry policy) — those six questions are all resolved above,
several reframed once free-form SQL generation was explicitly ruled out as a hard
constraint partway through this project's life. The starter tool selection and the
tier-0 help/greeting justification are both grounded in a real read of this app's own
`query_log` table (24 of 47 logged questions failed; the specific failures cited above
are real, not illustrative). Prior art for the tool-calling mechanism itself (medium-
granularity named functions over OpenAI's native tool-calling, real query-then-narrate
execution, no SQL generation) was verified by reading Savanna QSR Intelligence's and
Lobels Stores Intelligence's actual current chat implementations directly, not assumed
from memory of them.
