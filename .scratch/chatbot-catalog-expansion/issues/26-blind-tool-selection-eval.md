# 26: Blind tool-selection eval (independent of ticket 24's self-authored set)

**What to build:** a second tool-selection accuracy eval, built from real questions
pulled from `query_log` (real farm-owner phrasing, never seen by the person building the
tools) rather than authored phrasings - to get an unbiased accuracy number.

**Blocked by:** 24 (tool-selection accuracy eval)

**Status:** open

**Current-state baseline (as of this ticket, so whoever picks this up isn't starting
blind)**: 176 tests passing across the full suite, run twice for stability, zero
regressions. Ticket 24's eval - 50 cases (40 canonical, 3 adversarial, 7 negative) -
currently scores 100% (50/50), stable across 2 runs. Ticket 25's narration-grounding
check was independently verified against 12 real production questions with zero false
positives.

**Why this is a real, separate gap, not just "more test cases"**: ticket 24's eval is a
genuine regression gate (it would have caught the `q_health_cost_summary` mis-routing
regression found manually during tickets 16-23), but it is not an unbiased accuracy
measurement - most of its "canonical" cases are the same phrasings already used to
design and test the tools in the first place (harvested directly from each tool's own
`test_chatbot_tier3_*.py` file), and its "adversarial"/"negative" cases were also
hand-picked by the same person who built the tools, from the same known historical bugs.
A number derived that way tends to look better than real-world accuracy, because it's
scored against the exact confusions already anticipated and fixed.

**What "done" looks like**: pull a real, unfiltered sample of logged questions from
`query_log` (the production table every tier-3 hit and every catalog hit already
records, per section 6 of the handoff doc), label each with its actual/expected tool
(or `None` if it should resolve to no tool at all) by inspecting what a correct answer
would require - not by re-using ticket 24's existing case list - then run the same
`resolve_tool_call`-based accuracy scoring against that blind set. Report the real
number, not just "does it also hit >=95%" - if it's meaningfully lower than ticket 24's
100%, that gap itself is the useful finding, and further tool-description tightening or
new adversarial cases should be driven by whatever that set actually surfaces.

- [ ] A blind eval set built from real `query_log` questions, not authored phrasings.
- [ ] Accuracy measured and reported against that set specifically (not blended with
      ticket 24's numbers - the two evals answer different questions and should stay
      reported separately).
- [ ] Any real miss found this way gets its own regression case folded into ticket 24's
      eval afterward, same as every other real bug found in this project's history.
