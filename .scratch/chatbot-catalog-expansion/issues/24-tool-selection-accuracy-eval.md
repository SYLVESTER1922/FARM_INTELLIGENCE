# 24: Tool-selection accuracy eval

**What to build:** a holistic, cross-tool tool-selection accuracy eval - distinct from
every per-tool "resolve_tool_call picks X for canonical phrasings" test elsewhere in
this suite. Turns "how accurate is the chatbot at picking the right tool" from a guess
into a real, enforced, measured number, per the user's explicit target: >95% accuracy,
<5% risk of a wrong/hallucinated response.

**Blocked by:** 03 (Tier-3 core - tool-calling dispatch)

**Status:** done

**Implementation note**: 50 cases, three categories - 40 "canonical" (one tool's own
established phrasings, harvested from its existing per-tool test file, re-run together
in one shared eval rather than 19 separate ones), 3 "adversarial" (fresh paraphrasings of
the exact confusion boundaries that caused real regressions this project has already
hit - FCR vs. mortality rate, expense category vs. expense domain - not the same exact
phrasing the original regression test already covers, to actually stress the boundary),
7 "negative" (must resolve to NO tool at all: genuinely domain-ambiguous questions,
the real historical "are we owing anyone" accounts-payable bug, and genuinely
out-of-scope questions). A miss prints exactly which question, expected vs. actual tool,
and category - the same information that would otherwise only surface after a real user
hits it in production.

- [x] `test_tool_selection_accuracy_meets_threshold` asserts accuracy >= 0.95 across all
      50 cases, with a clear per-miss report if the threshold isn't met.
- [x] Verified: 100% (50/50), zero misses, stable across 2 repeated runs (real
      non-determinism means a single passing run proves less than two).
- [x] This is the regression gate that would have caught the `q_health_cost_summary`
      mis-routing regression found manually during ticket 16-23's implementation - run
      it on every future tool addition, not just once here.
- [x] The other half of the user's accuracy/hallucination request - a deterministic
      narration-grounding check, covering wrong narration of correct data rather than
      wrong tool selection - built separately. See ticket 25.
