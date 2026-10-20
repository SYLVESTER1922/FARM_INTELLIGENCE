# Router prompt log

Every change to `router/prompt.py` gets a new `PROMPT_VERSION` and an entry here. Tuning uses the DEV set only; no dev question is
copied into the prompt, and the locked held-out set is never used.

## v1 (2026-10-15)
First version. Rules, a catalogue generated from the registry (`answers` / `does_not_answer`), four invented examples.
Dev, gpt-4o-mini, 3 repeats: 134/176 correct, 3 wrong (all feed-cost questions routed to `expenses`), 22 refused, 16 clarified.

## v2 (2026-10-19)
Diagnosed from the v1 run (causes, not phrases):
- `metric: none / out_of_scope` was chosen for answerable questions by gpt-4o-mini. The `metric` field now says to match by meaning
  and to use `none` only when nothing could answer even in part; the out-of-scope rule says a question about the farm's animals,
  crops, money or stores always has a metric. (Registry `answers` texts also gained the plain ways of asking: harvested, on hand,
  ready to sell, today's weather, combined headcount, sold or closed.)
- feed cost routed to `expenses` with category "feed": "feed" was listed as an example category. Removed; feed is never a
  category; `feed_consumed_cost` is "never expenses"; `expenses.does_not_answer` says so.
- a dimension the metric does not offer (receivables/buyer, labour/domain, fcr/batch): the catalogue now says "Breakdowns: none"
  and the dimension rule is tied to the listed breakdowns.
- "average weight" read as `avg_per_week`, "this month" read as a monthly grain, "in total" / "so far" read as all-time: each rule
  now says what does not count.
- a section word inside a category ("day-old chicks") was dropped from `domains`: the rule now says to include it.
Dev, gpt-4o-mini, 3 repeats: 161/176 correct (91.5%), 1 wrong (0.6%, a mortality question given a per-batch breakdown), 8 refused, 6 clarified.

## v3 (2026-10-19)
Changes after v2, again from causes:
- the catalogue says per metric whether an average per week and a month-by-month view exist ("Average per week: no" for weight, breeding
  and the rest), so "average weight" is no longer read as a weekly average;
- three more invented examples: a section word inside a cost question, a question outside the farm's records, and a count that must
  not get a breakdown ("how many ... have died so far" has dimension none).
Deterministic changes made alongside (not prompt): a dimension the wording did not ask for is asked about; a named "not tracked" refusal
needs the user's own words behind it; a dimension "domain" on a multi-section metric is its default view; an all-time disagreement is only
asked about when a dashboard filter could change the answer.
Dev, gpt-4o-mini, 3 repeats: 162/176 correct (92.0%), 0 wrong, 4 refused, 10 clarified (5.7%: over the 5% cap; three were my new
"breakdown nobody asked for" check firing on harmless cases, fixed in code below).

## v4
Removed the invented "outside the farm's records" example added in v3: with it, gpt-4o-mini answered `none` for a plain total feed cost
in two of three repeats. The other v3 additions stay.

## v5 (2026-10-19)
The refusal vocabulary is now generated from the curated list in `catalog/untracked.py` (step 6) instead of written in the prompt: three
refusal classes were added for data that IS recorded but that no metric reads (`staff_info`, `crop_scouting`, `field_operations`) and
one for payroll history. No other rule changed. Measured after the change: see plan section 24.
