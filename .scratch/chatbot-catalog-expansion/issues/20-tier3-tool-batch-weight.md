# 20: Tier-3 tool - batch weight / growth tracking

**What to build:** "What's the average weight of batch PIG-B01?" / "how heavy are the
pigs right now" and real phrasing variants resolve via a new tier-3 tool - latest
average sampled weight per batch, from `pig_weights`/`poultry_weights`, as of a cutoff.

**Blocked by:** 03 (Tier-3 core - tool-calling dispatch)

**Status:** done

**Implementation note**: at least one of `domain` or `batch_code` is required - neither
is individually marked required in the tool schema (both are legitimate ways to ask),
but calling with neither is a genuine tool-call error, raising `InvalidToolArgument`
(final, no retry, same precedent as `q_cost_per_animal`'s required `domain`). Piggery
weights are kg, poultry weights are grams - kept as separate, explicitly-labelled result
fields (`piggery_avg_weight_kg_by_batch` / `poultry_avg_weight_g_by_batch`), never
merged into one ambiguous "weight" number, so the narrator never mixes units.

- [x] "What's the average weight of batch PIG-B01?" resolves to `q_batch_weight` with
      the real latest sample (verified against a real fixture: two weight samples,
      correctly picks the later 28.5kg over the earlier 20.0kg once the as-of cutoff -
      driven by the latest headcount data date - covers it).
- [x] Calling with neither `domain` nor `batch_code` raises `InvalidToolArgument`.
- [x] Module scoping applies (piggery/poultry).
- [x] Tested at both seams: black-box final-answer content, direct argument-validation
      tests (missing both args, invalid domain), and tool-selection assertion for
      canonical phrasings.
