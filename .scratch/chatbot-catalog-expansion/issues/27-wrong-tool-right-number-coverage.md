# 27: Coverage for "right number, wrong question" (correctly-sourced but substantively wrong answers)

**What to build:** a way to catch a tool that runs cleanly, returns a real,
correctly-computed number pulled from the right place in the database, and narrates it
with full grounding - but the number answers a *different* question than the one asked.
Neither ticket 24's tool-selection eval nor ticket 25's narration-grounding check covers
this failure mode; both were built for a different half of the accuracy/hallucination
problem.

**Blocked by:** 24 (tool-selection accuracy eval), 25 (narration-grounding check)

**Status:** open

**Current-state baseline (as of this ticket)**: 176 tests passing across the full suite,
run twice for stability, zero regressions. Ticket 24's tool-selection eval: 100%
(50/50), stable across 2 runs. Ticket 25's narration-grounding check: verified against
12 real production questions with zero false positives.

**Why this is a real, separate gap**: ticket 24 checks *which tool* gets picked (a
selection-accuracy problem: FCR question -> `q_fcr_ranking`, not `q_mortality_rate`).
Ticket 25 checks that a narration's numbers are *real* (a grounding problem: no invented
`999` where the data says `24`). Neither checks whether the *right* tool got called with
the *right arguments* for the specific nuance of the question - e.g. a tool being called
with the wrong `domain` argument (this project's very first real production bug,
`6d3e063`/round 1 in the handoff doc, was close to this shape: the right general
concept, wrong specifics), or a period/cutoff argument that technically executes and
returns a real, grounded number, but isn't the period/cutoff the question actually
asked about. This can currently only be caught by a manual QA pass (the two 15-question
passes already run this project's history) or a live user reporting it - neither is
systematic or automatic.

**What "done" looks like** (a starting direction, not a fixed design - worth grilling
before building): likely an extension of ticket 24's eval structure, but asserting on
*tool arguments*, not just tool name - e.g. "which chickens died last week" must resolve
to `q_mortality_rate` with `domain="poultry"` and `period="last_7_days"`, not just "some
tool that happens to be `q_mortality_rate`." Would need real logged examples (see ticket
26) of argument-level mistakes to know which argument confusions are actually worth
guarding against, rather than guessing at plausible-sounding ones.

- [ ] A concrete design for checking tool *arguments*, not just tool *selection* -
      decide whether this extends ticket 24's eval structure or needs a different seam.
- [ ] At least the known real argument-level bugs from this project's history (the
      combined-headcount domain-guessing bug, `6d3e063`'s owing-question misrouting)
      captured as permanent regression cases, the same way ticket 24 captured
      tool-selection regressions.
- [ ] A decision on whether this needs new tooling (e.g. asserting on
      `ToolCallResult.arguments`) or is already achievable with what `resolve_tool_call`
      already returns.
