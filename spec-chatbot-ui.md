# Spec: Chatbot UI (Gradio, Hugging Face Spaces)

## Problem Statement

The chatbot's answer engine (`spec-chatbot-answer-engine.md`, tickets 01–04) is fully
built and tested — `answer_question` correctly resolves questions, respects module
scoping, and never lets an LLM touch raw-row arithmetic. But it's a Python function, not
something a farm owner can actually use. On top of that, several genuinely open questions
were never addressed by either backend spec, because they're specific to *presenting*
answers rather than *computing* them: how a scoping refusal should look to the farm owner
versus staying purely internal `query_log` data, how a farm owner would pick which
farm/module they're viewing, and what the user experience should be for the LLM
fallback's added latency versus the near-instant deterministic path.

## Solution

A single-page Gradio chat app, deployed to a **private** Hugging Face Space
(password-protected via HF's built-in visibility setting) — matching the delivery
pattern already used by Netrisyl's other chatbot products, JCC-Chatbot and the Pharmacy
Assistant (confirmed directly, not assumed). A thin message-handler function wires
Gradio's chat interface to the already-built `answer_question` seam: a hardcoded
`farm_code` for this pass (multi-farm UI explicitly deferred — there's only one real
farm today), the Supabase DSN sourced from an environment variable via HF Spaces
Secrets (the same pattern the backend already uses for `OPENAI_API_KEY`), and any
exception caught and replaced with a fixed, generic error message so a farm owner never
sees a raw stack trace.

## User Stories

1. As a farm owner, I want to type a question in plain language and get an answer, so I
   don't need to know SQL or Python.
2. As a farm owner, I want to see my past questions and answers in a scrolling chat
   history, so I can refer back to something I asked earlier in the session.
3. As a developer, I want the chat history displayed in the UI never fed back into
   `answer_question` as context, so the backend's explicit "no multi-turn" decision
   stays intact — history is a display concern, not a context concern.
4. As a farm owner, I want the chat to feel responsive while I wait for an answer, so I
   know the app is working, even without knowing which resolution tier is being tried.
5. As a developer, I want no distinct UI signal for which intent-resolution tier
   answered a question, so I don't need to expose internal tiering machinery before real
   usage feedback ever asks for it.
6. As a farm owner, when a module is turned off, I want to see the chatbot's own
   explanation (e.g. "The poultry module is turned off...") displayed as a normal
   answer, so I understand why without a confusing special UI treatment.
7. As a developer, I want no module selector or per-domain browsing UI, so the interface
   stays pure free-text Q&A, matching `answer_question`'s actual signature (question and
   farm_code only — no domain parameter).
8. As a developer, I want a single hardcoded `farm_code` for this UI pass, so I'm not
   building farm-switching UI against a system that only has one real farm to switch
   between.
9. As a farm owner, I want the chatbot to run as a Gradio app, matching the interface
   style of Netrisyl's other chatbot products, so the experience feels familiar across
   the company's tools.
10. As a developer, I want the app deployed to a Hugging Face Space, matching where the
    sibling products already run, rather than standing up new hosting infrastructure.
11. As a developer, I want the Space to be private/password-protected, so the farm's
    financial and health data (debtor names and amounts, disease outbreaks, mortality
    rates) is never exposed on a public, unauthenticated URL.
12. As a developer, I want the Supabase DSN sourced from an environment variable via HF
    Spaces Secrets, the same pattern already used for `OPENAI_API_KEY`, so there's one
    consistent credentials story rather than a special case for one value.
13. As a developer, I want any genuine infrastructure failure (DB unreachable, OpenAI
    API error, timeout) caught at the UI layer and shown as a fixed, generic "something
    went wrong" message, so a farm owner never sees a raw exception or stack trace, and
    internals are never leaked.
14. As a developer, I want a single message-handler function to be the one seam under
    test, so tests don't depend on Gradio's rendering internals or the deployed Space.
15. As a developer, I want the handler's happy path tested by delegating to the
    already-tested `answer_question`, so this layer's tests focus on what's actually new
    here (wiring, credentials sourcing, error handling) rather than re-proving backend
    behavior that's already covered.
16. As a developer, I want the exception-swallowing behavior explicitly tested, so I
    know a backend failure can never leak past this layer to the farm owner.
17. As a farm owner, I want the chatbot's answers — including scoped-out refusals —
    displayed exactly as returned text, with no distinct icon or visual treatment
    versus a genuine "I don't know," so the interface stays simple for this first pass.
18. As a developer, I want this UI layer to add no new business logic beyond wiring,
    credentials sourcing, and error handling, so `answer_question` remains the single
    source of truth for all answering behavior.
19. As a developer, I want farm-switching UI, a module selector, and fallback-tier-
    specific latency messaging explicitly named as deferred rather than half-built, so
    this spec is honest about what's actually being delivered now versus later.
20. As a developer, I want the credentials pattern (environment variables via HF
    Secrets) to require no code changes between local development and the deployed
    Space, so testing locally accurately reflects deployed behavior.

## Implementation Decisions

- **Platform**: a Gradio app using a chat-interface component, matching JCC-Chatbot and
  the Pharmacy Assistant's existing stack — confirmed directly with the user, not
  assumed, the second time in this project that "match what Netrisyl's other products
  already do" has settled a technology decision (the first was the LLM provider,
  OpenAI GPT-4o-mini).
- **Deployment**: Hugging Face Spaces, with the Space set to **private** (HF's built-in
  visibility/password setting) — not public, given the sensitivity of the data in the
  chatbot's answers.
- **Seam**: a single message-handler function (e.g. `handle_message(question: str) ->
  str`), wired directly to Gradio's chat component. Internally it calls
  `answer_question(question, farm_code=FARM_CODE, dsn=DSN)`:
  - `FARM_CODE` is hardcoded for this pass (single real farm today; farm-switching UI
    explicitly deferred, not built against a hypothetical second farm).
  - `DSN` is read from an environment variable (e.g. `FARM_INTELLIGENCE_DB_DSN`) via HF
    Spaces Secrets — mirroring exactly how `OPENAI_API_KEY` already works in
    `chatbot/engine.py`, not a new credentials mechanism.
- **Conversation history**: Gradio's chat component displays a running thread of past
  exchanges by default. This is a display-only concern — no history or prior messages
  are ever passed into `answer_question`, preserving the backend's explicit no-multi-turn
  design untouched.
- **Latency UX**: Gradio's default "waiting for a response" indicator is the only signal
  while an answer is generating. No distinct messaging differentiates the deterministic
  path from the LLM fallback path — doing so would require `answer_question` to expose
  which tier it's about to attempt before it finishes, which is backend work out of
  scope here.
- **`scoped_out` display**: `Answer.text` (already a complete, farm-owner-readable
  explanation from the backend's own template) is displayed exactly as returned, with no
  distinct icon, color, or visual treatment versus a genuine `unresolved` answer.
  `scoped_out_reason` itself stays internal (`query_log`-only) — the UI never reads or
  displays it directly, only the already-phrased `Answer.text`.
- **No module selector**: the interface is pure free-text Q&A — no tabs, filters, or
  per-domain browsing UI. Domain scoping happens entirely server-side and is invisible
  to the UI layer.
- **Error handling**: the handler wraps the call to `answer_question` in a try/except;
  any exception (DB unreachable, OpenAI API error, timeout, etc.) is caught and a fixed,
  generic message (e.g. "Something went wrong — please try again.") is returned instead.
  No raw exception or traceback ever reaches the farm owner. This is the one piece of
  genuinely new application logic this layer adds beyond wiring.
- **Explicitly deferred, not half-built**: farm-switching UI, a module selector/browser,
  fallback-tier-specific latency messaging, and per-user roles/accounts within the Space
  (a single shared password is sufficient given the solo/two-person context this whole
  project operates in).

## Testing Decisions

- **Seam**: the message-handler function only. No tests against Gradio's rendering,
  HTML/JS output, or the deployed Space itself — those are framework/platform
  configuration, not application logic that benefits from automated tests.
- **Happy path**: the handler correctly delegates to `answer_question` and returns its
  `.text`. This is intentionally a thin test — `answer_question`'s own correctness is
  `spec-chatbot-answer-engine.md`'s job, already covered by its 68 tests, not this
  spec's job to re-prove.
- **Exception handling**: the one genuinely new behavior this layer adds. Simulate
  `answer_question` raising, and assert the handler returns the fixed generic error
  message rather than propagating. Since this needs to simulate a failure
  `answer_question` won't naturally produce on demand (a real DB outage, say), injecting
  a failure at this seam's boundary is the legitimate, narrow exception to
  "test against the real thing" — same spirit as ticket 04 sabotaging the `query_log`
  table mid-test to prove its fire-and-forget behavior
  (`test_query_log_write_failure_never_breaks_the_answer`), rather than trying to
  provoke a real Postgres or OpenAI outage on demand.
- **Prior art**: `tests/test_chatbot_engine.py`'s fire-and-forget test (above), and the
  black-box-through-one-seam discipline already established across every prior ticket in
  this project.
- **Not tested**: Gradio's own configuration, HF Spaces deployment settings, and the
  private-Space password protection are verified manually (opening the deployed Space
  and confirming it prompts for a password) rather than via automated tests, since
  they're platform configuration, not application code.

## Out of Scope

- Farm-switching UI (multi-farm support) — deferred until a second real farm exists to
  switch to.
- A module selector/browser UI — pure free-text Q&A only for this pass.
- Fallback-tier-specific latency messaging — would require `answer_question` to expose
  tier information before completing, a backend change out of scope here.
- Per-user roles or accounts within the Space — a single shared password is sufficient
  given the solo/two-person context.
- Any changes to `chatbot/engine.py`, `chatbot/catalog.py`, `chatbot/matcher.py`, or
  `chatbot/fallback.py` — this spec is built entirely on top of the already-complete
  `answer_question` seam and doesn't modify it.
- Conversation memory / multi-turn context — explicitly out of scope per the backend
  spec; this UI layer doesn't change that. Displayed history is view-only.
- Analytics or dashboarding on top of `query_log` — still nobody's job yet, per the
  backend spec's own out-of-scope note; unchanged by this spec.

## Further Notes

- This spec builds directly on the completed `spec-chatbot-answer-engine.md` (tickets
  01–04) and treats `answer_question` as a given, stable seam — not open for
  re-litigation here.
- The full design behind this spec was stress-tested via `/grill-me` before being
  written down; treat the decisions above as settled, not open for re-litigation during
  implementation.
- No issue tracker is configured for this project; this is a standalone spec file,
  consistent with `spec-supabase-sync.md` and `spec-chatbot-answer-engine.md`.
