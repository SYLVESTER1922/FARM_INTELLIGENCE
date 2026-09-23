# 01: Tier-0 greeting/help responses

**What to build:** Bare greetings ("hi", "hey") and "what can you ask" style questions
get a fixed, honest canned response describing the chatbot's real capabilities, checked
before tier-1's real catalog matching is attempted.

**Blocked by:** None (can start immediately)

**Status:** done

**Implementation note**: the ticket originally proposed reusing tier-1's fuzzy
recall-based phrase scoring. Building it revealed that scoring is unsafe for this use -
it's a recall-only overlap (matched tokens ÷ phrase length), so a short phrase like "hi"
would score a perfect match against *any* question merely containing the word "hi"
anywhere in it, including a real data question. `chatbot/greetings.py` instead does
exact normalized-token-set matching against a curated phrase list - the whole question
must reduce to a known phrase, not just overlap with one. Documented in the module's
own docstring.

- [x] A curated set of greeting/capability phrase patterns (e.g. "hi", "hey", "what can
      you ask", "what can I ask you") are recognized, checked before tier-1's catalog
      matching runs.
- [x] A recognized greeting/capability question returns a fixed, honest response
      describing the chatbot's real, current capabilities (not a fabricated broader
      feature set) - zero LLM calls.
- [x] A question that merely contains a greeting word but is clearly a real data
      question (e.g. "hi, how many pigs do we have") is not misclassified as tier-0 -
      real data questions still resolve normally.
- [x] The existing 4-entry catalog's tier-1/tier-2 behavior and all currently-passing
      tests are unaffected (71 -> 76 passing, all prior tests unchanged).
- [ ] Verified against the real logged failures already in `query_log` (bare
      "hi"/"Hie"/"HI" and "what can you ask"/"What can I ask you?"/"what questions can i
      ask?") - these now resolve via tier-0 instead of `unresolved`. Covered by unit
      tests reproducing these exact real phrasings; not yet re-verified live against
      production.
