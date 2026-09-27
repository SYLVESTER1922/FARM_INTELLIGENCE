# 10: Tier-3 tool - profit (revenue minus expenses)

**What to build:** "Is the piggery profitable?" and "how much profit did we make"
resolve via a new tier-3 tool computing a real subtraction (revenue to date minus
expenses to date), farm-wide or for one domain. Sourced from a real QA-pass gap: the
dashboard's Expenses vs Revenue chart shows both series as separate lines but never
computes their difference, so this closes a genuine gap rather than duplicating what's
already visible.

**Blocked by:** 03 (Tier-3 core - tool-calling dispatch)

**Status:** done

**Implementation note**: uses the same "to date" cumulative-cutoff semantics as
`q_expenses_to_date` (not a `date_from`-bounded range) for both revenue and expenses,
so the subtraction is always comparing two totals as of the same cutoff. Reuses
`q_expenses_to_date` directly for the expenses half rather than duplicating its query.

- [x] "Is the piggery profitable?" and "how much profit did we make" resolve to a real
      subtraction, not a non-answer. Verified against real production Supabase data:
      piggery profit = 9333.17 revenue - 14896.67 expenses = -5563.50, independently
      cross-checked, exact match.
- [x] Farm-wide (all domains) and single-domain queries both work.
- [x] Module scoping applies across all three domains (profit can touch any of them),
      same static-declaration rule as `q_expenses_to_date`.
- [x] Tested at both seams: black-box final-answer content (single-domain and
      farm-wide), and tool-selection assertion for canonical phrasings including the
      exact real logged question.
- [x] Known limitation, not fixed here: does not yet support a relative period like
      "last month" - answers the cumulative "to date" figure instead. The real logged
      question that surfaced this ("how much profit did we make last month") got a
      real, correctly-computed to-date figure, just not scoped to "last month"
      specifically. Worth a follow-up if this proves confusing in practice.
