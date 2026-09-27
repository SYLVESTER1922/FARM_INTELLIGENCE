# 13: Tier-3 tool - FCR ranking

**What to build:** "Which batch has the worst feed conversion ratio?" resolves via a
new tier-3 tool that ranks batches by FCR, instead of tier-1 mismatching it to
`poultry_mortality_spike` and mislabeling a mortality percentage as FCR. Sourced from a
real bug found in a security/edge-case QA pass.

**Blocked by:** 03 (Tier-3 core - tool-calling dispatch)

**Status:** done

**Implementation note**: the mismatch had two independent causes, both fixed. (1)
`chatbot/matcher.py`'s `_overlap` scoring changed from recall-on-phrase-only to Jaccard
similarity - the old formula let a short, generic-template phrase ("which X has the
worst Y") score high against any question sharing that template regardless of what Y
was (0.714 for the FCR question against `poultry_mortality_spike`'s phrase, ignoring
that "mortality" itself never matched). Jaccard scores the same case at 0.5, below
threshold, while every exact-phrase match in the existing catalog still scores a full
1.0 exactly as before - verified against the full test suite, zero regressions, since
every existing tier-1 test happens to use exact-phrase matches. (2) `PIG_FCR_SQL`/
`POULTRY_FCR_SQL`/`fetch_fcr_by_batch`'s logic was relocated from `ui/queries.py` into
`chatbot/catalog.py`'s new `fcr_by_batch`, mirroring `active_headcount_asof`'s existing
placement there, so this tool and the dashboard's FCR chart share one source of truth.

- [x] "Which batch has the worst feed conversion ratio?" resolves via `q_fcr_ranking`,
      not `poultry_mortality_spike`. Verified against real production Supabase data:
      PIG-B01 with FCR 2.65 (the real worst of four piggery batches) - independently
      cross-checked, exact match. Never mentions mortality.
- [x] Tier-1's Jaccard fix verified with zero regressions across the full test suite.
- [x] Module scoping applies (piggery/poultry), same static-declaration rule.
- [x] Tested at both seams: black-box final-answer content (asserting the correct worst
      batch and the explicit absence of "mortality" in the text), and tool-selection
      assertion for canonical phrasings including the exact real logged question.
