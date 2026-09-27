# 12: Tier-3 tool - expenses breakdown by domain (comparison)

**What to build:** "Compare piggery and poultry costs" resolves via a new tier-3 tool
returning all three domains' expense totals together, instead of the previous
behavior where `q_expenses_to_date` only ever returned one domain's total and the
narrator admitted "poultry costs not provided for comparison." Sourced from a real
QA-pass gap, and from the settled design decision (during the earlier expanded-scope
sequencing conversation) to extend a single tool to return multiple domains rather than
have the LLM call two tools in one turn - tier-3's dispatch only ever uses the first
tool call per turn (see `resolve_tool_call`).

**Blocked by:** 03 (Tier-3 core - tool-calling dispatch)

**Status:** done

**Implementation note**: reuses `q_expenses_to_date`'s exact query three times (once
per domain) rather than a new SQL pattern. `q_expenses_to_date`'s own tool description
was tightened to explicitly point comparison questions at this tool instead, since the
two tools' purposes (a single total vs. a breakdown) could otherwise be confused by the
LLM.

- [x] "Compare piggery and poultry costs this year" resolves with both real domain
      totals present together. Verified against real production Supabase data:
      piggery 14896.67, poultry 7201.15 - independently cross-checked, exact match.
- [x] Module scoping applies across all three domains, same static-declaration rule.
- [x] Tested at both seams: black-box final-answer content (asserting both domains'
      real figures appear), and tool-selection assertion for canonical phrasings
      including the exact real logged question.
- [x] No changes required to tier-3's core dispatch mechanism itself.
