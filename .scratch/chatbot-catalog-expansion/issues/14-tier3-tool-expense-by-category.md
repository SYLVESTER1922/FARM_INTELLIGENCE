# 14: Tier-3 tool - expense breakdown by category

**What to build:** "What's our biggest expense category overall?" resolves via a new
tier-3 tool giving a real breakdown by CATEGORY (Feed, Labour, Vet, etc.), instead of
`q_expenses_by_domain` being matched and its domain breakdown mislabeled as categories.
Sourced from a real bug found in a security/edge-case QA pass.

**Blocked by:** 03 (Tier-3 core - tool-calling dispatch), 12 (`q_expenses_by_domain`,
whose description was tightened alongside this ticket to explicitly distinguish the
two dimensions)

**Status:** done

**Implementation note**: a fresh, self-contained SQL query was written directly in
`chatbot/tools.py` rather than reusing/relocating `ui/queries.py`'s existing
`EXPENSE_BREAKDOWN_SQL` (used by the dashboard's expense breakdown donut) - the
dashboard's version is deliberately lifetime-only/unfiltered, while this chat tool
respects the global date-range filter like every other tier-3 tool; forcing the
dashboard's chart onto a filtered query it was never designed for would have been an
unwanted behavior change to something outside this ticket's scope.

- [x] "What's our biggest expense category overall?" resolves to a real category
      breakdown via `q_expense_by_category`, never conflating category with domain.
      Verified against real production Supabase data: "Feed" at 19281.0 - independently
      cross-checked against a direct `GROUP BY category` query, exact match. Never says
      "piggery" or "poultry" in the answer.
- [x] `q_expenses_by_domain`'s own description was tightened to explicitly point
      category questions at this new tool instead, since the two tools' purposes could
      otherwise be confused by the LLM.
- [x] Optional domain filter supported, validated against the closed vocabulary.
- [x] Tested at both seams: black-box final-answer content, and tool-selection
      assertion for canonical phrasings including the exact real logged question.
