# Chatbot v2: plan (draft for review)

Status: **reviewed by Sylvester, no code changed.** Written after a twelve-question design review between Sylvester and Claude, then updated with the resolutions to the section 15 open items. Every decision below was agreed explicitly.

## 1. Goal

A chatbot that is ready to ship and needs only real client data. Targets:

- **Wrong answers at most 0.5%** of all answers (wrong-but-confident), with **zero tolerance for wrong money figures and headcounts**.
- **Honest refusals** and **clarifying questions** are separate budgets, not wrong answers.
- The 0.5% claim is made only at Gate C (section 12), in the exact form given there.

"Wrong" includes: a wrong number; the right number at the wrong scope; a silently omitted part or row; a false "we don't track that"; a raw data dump.

## 2. Why the current design fails (summary)

Seven stages sit between the question and the answer: tier-0, tier-1 phrase matcher, tier-2 LLM, ambiguity check, tier-3 LLM tool-calling, `explain_gap` LLM, and LLM narration plus the grounding regex. Each is a place to be wrong. Findings from reading the code:

| Live failure | Root cause |
|---|---|
| "How many batches of poultry" returned `found: True, as of: …` | No batch-count tool. The LLM probably picked `q_batch_weight`, then `fallback_narration` printed top-level scalars only (`grounding.py:213`). |
| Feed cost "last month" and "weekly average" returned 13308.5 | LLM guessed `domain=piggery` and dropped the period on `q_expense_by_category`. Nothing models "average" or "per week". Grounding passed because the number was in the data. |
| "Any sick pigs or chickens" refused | Hand-written `DATA_DICTIONARY` plus the `explain_gap` LLM. "Sick now" isn't a state in `health_log`. |
| "Who is owing us?" refused as accounts payable | Phrase tier has no stemming (Jaccard on exact tokens). `q_expenses_to_date`'s description tells the LLM to call no tool for "owing". `CROP_DEBTOR_SQL` also hard-codes `domain = 'crops'`, omitting piggery and poultry debtors. |
| Piggery feed cost in Aug 2026 refused, "split" answered | Capability gap: no feed-cost tool at HEAD. The answered one was consistent. |
| Feeding and Finance pages differ by about 35% for poultry | Two independent "kg consumed" sources: `feed_inventory.used_kg` (Feeding page, `ui/queries.py:342`) vs daily-log `feed_kg` (Finance, `feed_cost_by_domain`). A third copy lives in `FEED_COST_SPLIT_SQL`. |
| Not reported live | Two mortality definitions: deaths / chicks placed (catalog) vs deaths / current headcount (`q_mortality_rate`). |

The 50/50 tool-selection eval calls `resolve_tool_call` only. It bypasses six of the seven stages and scores only the tool name.

## 3. Decisions (all agreed)

| # | Decision |
|---|---|
| D1 | **Feed.** The daily log (`feed_kg` priced from `feed_inventory`) is the single "feed consumed cost" metric. `expenses.category = 'Feed'` is a separate metric, "feed purchases". Feeding page and Finance page both use the registry definition. The sync reports any month where daily-log consumption and `feed_inventory.used_kg` differ by more than the farm's tolerance (default 5%); **report-only at launch** (see section 9 and 16). |
| D2 | **Relative periods** ("last month", "this month", "last week", "this quarter", YTD) resolve against the **calendar date in Africa/Harare**, then check coverage. Fully covered: answer normally. Partly covered: answer and state the coverage. Not covered: say so, give the latest data date, never substitute another period. The data-date anchor in `matcher.py` is dropped for relative periods. The resolved period is stated on the first line of every answer. |
| D3 | **Snapshot questions** (headcount, stock on hand, balances) use the latest data date and say "as of <date>". |
| D4 | **Dashboard date filter stays in chat.** Precedence below (section 5). The scope resolver applies it, not the LLM. |
| D5 | **Fully templated answers.** No LLM in the answer path. `grounding.py` and its regex scaffolding are deleted once templates cover all registry metrics. |
| D6 | **Defaults and clarification.** Unspecified domain defaults to all domains (echoed, per-domain breakdown always shown). A single-module farm resolves to its one domain. Ambiguity between two named registry metrics always asks, with numbered options. The choice is remembered for the rest of the conversation. |
| D7 | **Currency** is one per-farm setting from `farm_profile.currency`. Templates, chart titles and the sidebar read it; "USD" is no longer hard-coded. Target farms record in USD throughout (edit if a client differs). Multi-currency is out of scope; a farm recording in more than one currency is onboarded as a data-quality blocker. |
| D8 | **Sync gates** run on a staging copy; live tables swap only on a pass. Block and warn severities (section 9). |
| D9 | **Launch registry** of about 19 metrics, with zero-tolerance groups (section 4). |
| D10 | **Eval** is independent, split, repeated and statistically honest (section 11). |
| D11 | **LLM role.** One call per question that maps the question to a metric plus scope spec. Closed enums only, never farm data. Cost ceiling **1 cent per question**; median latency under 3 s, p95 under 6 s. Model chosen by bake-off, then pinned (section 6). |
| D12 | **Strangler with shadow mode** cutover, per metric group (section 13). |

## 4. Metric registry

### Launch set (about 19)

| Group | Metrics |
|---|---|
| **Money (zero-tolerance)** | feed consumed cost; feed purchases; expenses (dimension: total, by category, by domain); revenue (dimension: total, top buyers, top products); profit; cost per animal; receivables (**new**, all domains, who owes us); labour cost |
| **Headcount (zero-tolerance)** | active headcount; batch count (**new**); sow count with status split (**new**, step 2); deaths and mortality rate (one definition) |
| **Performance** | FCR ranking; weight; harvest yield; breeding summary |
| **Operations** | feed stock; market readiness; health events (treatment events in a period); weather |

Averages and grain ("average weekly feed cost") are a registry feature (aggregation and grain in scope), not separate tools.

### Left out of v1 (exploratory lane later)

Per-sow breeding detail, buyer-level history, trend and "why" questions.

### Named refusals (deterministic, from the registry)

- **Accounts payable** ("do we owe anyone?"): not tracked. States exactly what is not tracked and what the farm would need to log (supplier invoices with amount, due date and paid status).
- **"Currently sick"**: not tracked as a state; only treatment events are logged. States that, offers the health-events metric, and says what to log (a sick-animal status per batch with a date).

An LLM never asserts "not tracked" by itself. Refusal reasons come from three classes: not tracked / tracked but no metric yet / needs scope.

### Every registry entry carries

1. definition (plain language, owner-approved)
2. source tables
3. unit and fixed decimals
4. template
5. scope rules (allowed domains, periods, aggregation, grain, snapshot or range)
6. zero-tolerance flag
7. at least N eval cases (N set per group in the build)
8. a parity test linking the chat output to the dashboard output for the same scope
9. a description of what it answers and does not answer (used by the lexicon cross-check and the catalog)

A coverage test fails if any table is neither exposed by a metric nor explicitly marked unexposed.

## 5. Scope resolver (deterministic code)

Input: the raw question text, the dashboard filter, the farm profile (modules, timezone, currency), and the session record (previously chosen metrics). It never calls an LLM.

Output, a typed scope:

| Field | Meaning |
|---|---|
| `metric` | registry metric (from the routing step) |
| `domains` | explicit set; all domains if none named; the single domain on a single-module farm |
| `period` | `start`, `end` (or `as_of` for snapshots) |
| `period_source` | `question` / `filter` / `all_time` / `snapshot` (which rule fired) |
| `coverage` | `full` / `partial` / `none`, with first and last data dates |
| `aggregation`, `grain` | total, average, per week, per month, etc. |
| `unresolved` | a typed reason, never a silent default |

### Period precedence (rules 1 to 5)

1. A period **named in the question** wins; the filter is ignored for that question.
2. **Explicit scope words** ("all time", "overall", "ever", "since we started") override the filter just as a named period does.
3. No period named and a **filter set**: the filter applies, and the first line says so, e.g. "Feed cost, all domains, 1–31 Aug 2026 (dashboard date filter)". If the answer would differ from all-time, add the hint "Say 'all time' to ignore the dashboard filter."
4. No period named and no filter: **all time**; the first line says "all recorded time (since <first data date>)".
5. **Snapshot** questions use the latest data date, ignore the filter, and are labelled "as of <date>".

Relative phrases resolve per D2, in Africa/Harare. Domain words are matched by a lexicon (pig, pigs, piggery, swine, sow; chicken, poultry, broiler, birds; and so on). The lexicon is also a cross-check on the LLM spec: a domain word the spec missed cannot silently fall through to "all domains".

## 6. Routing: question to metric

Single path, replacing tiers 1, 2 and 3:

1. **One LLM call** returns a JSON-schema-constrained spec over the registry's closed enums (metric, dimension, aggregation, grain, domain words, period phrase). It sees the question text only.
2. **Deterministic lexicon cross-check** (owe / owing / owed, pig words, "weekly", "average", and so on). If the spec and the lexicon disagree, ask a clarifying question; never pick one silently.
3. **Scope resolver** (section 5) builds the typed scope.
4. **Metric executes** and the template renders.

### Clarification

- Ambiguity between two named registry metrics always asks, with **2 to 3 numbered options** built from the registry ("Reply 1 or 2"), plus tappable buttons if the UI supports them reliably.
- The choice is stored in session state (a small record passed into `answer_question`, held in `gr.State`) and not re-asked in the conversation.
- Vague-about-everything questions keep the deterministic clarification with example questions.
- Every clarification is logged in `query_log` with a reason code.

### Follow-ups and multi-part questions

- **Simple follow-ups** ("and last month?", "and for poultry?") carry over the **previous metric only**. The new question supplies its own scope, and the resolved scope is echoed on the first line. Anything else is standalone.
- **Multi-part questions** ("feed cost and mortality") get a clarification asking which part to answer first. Answering several parts in one turn is on the backlog.

### Provider interface and model bake-off

- One provider-neutral interface (question in, validated spec out) with a small adapter per provider.
- Bake-off on the dev set: `gpt-4o-mini`, one stronger OpenAI model, one Claude model. Choose the cheapest that meets the routing target (set at Gate A). Report cost against accuracy. **Pin the version.** Re-run the locked eval before any model change.

### Failure mode

If the LLM call fails or times out, the bot says it can't process questions right now and falls back to the deterministic phrase tier for exact matches only. It never guesses. `explain_gap` is removed.

## 7. Answer rendering

Fixed layout, filled from the structured result:

1. **First line:** echoed scope (metric, domain, period, period_source).
2. **Figure(s)** with per-domain or per-category breakdown.
3. **Coverage note or hint**, always including "data through <date>".

Formatting: currency symbol from `farm_profile.currency` and thousand separators; human domain names; fixed decimals per unit; breakdown rows ordered largest first.

**Completeness test:** a unit test fails if any field of a metric's structured result is not rendered. Greeting and sign-off are fixed constants; no generated text surrounds a number.

The LLM's only roles: (a) mapping the question to a metric plus scope, and (b) the later exploratory lane, labelled "Exploratory, not verified".

## 8. Capability catalog and refusals

Generated from the registry, with the schema used as a coverage check. A small hand-curated "known untracked" list covers what a schema cannot prove (accounts payable, payroll history, equipment, live forecast weather, company legal structure). `DATA_DICTIONARY` and `explain_gap` are retired.

## 9. Sync and data-quality gates

- Gates run on a **staging copy**. Live tables swap only on a pass.
- On a block, the app **keeps serving the last good snapshot** with the banner "Data last verified <date>. A newer upload is being reviewed." Every chat answer carries "data through <date>".
- **Staleness rule:** when the last good snapshot is older than **7 days**, the banner becomes more prominent.
- **Notification:** every block notifies Sylvester by email during the pilot.
- **Log every gate firing** (gate, severity, farm, rows affected) to measure false-positive rates.

| Severity | Gate |
|---|---|
| **Block** | invalid or missing currency (not a recognised ISO code); suspected mixed currency; unrecognised units; duplicate primary keys |
| **Warn** | a month with no rows; 10× jump or drop in an expense category between consecutive periods |
| **Report only** | feed consumption reconciliation (daily log vs `feed_inventory.used_kg`) above the farm's tolerance: listed in the data-quality report, with **no banner and no caveat on any answer**; becomes a warn only after calibration on the first month of real data |

A warning goes live with a visible caveat on the affected metrics and appears in a data-quality report. The 10× jump starts as warn; promote to block after one month of real data.

**Reviewers:** during the pilot Netrisyl (Sylvester) reviews all flagged issues. Later the farm's data owner can acknowledge warnings; blocks stay with Netrisyl. Acknowledgements are logged with reviewer, reason and timestamp.

Also in the sync: missing data must never become zero. The current `COALESCE(SUM(...), 0)` in several tools becomes an explicit no-data result.

## 10. Dirty-data fixtures

A deliberately dirty fixture generator (typos, gaps, missing months, kg vs g, duplicate rows, a mixed-currency month) feeds the eval, because the synthetic workbook plants its findings and passes on clean data.

## 11. Evaluation

### Parts

1. **Questions:** about 150 hand-written to start (Sylvester owns and has final approval; Tadiwanashe Dzimbanete writes and spot-checks), plus the client's top 20 in their own wording. Generated paraphrases, typos and voice-style variants, with about 20% spot-checked by a person. The client's farm manager reviews a sample of about 30 questions and answers; planned, not depended on.
2. **Golden answers:** computed by an independent oracle (plain SQL or pandas on the fixture data), written separately from the registry code. A registry-oracle disagreement is a finding.
3. **Pass/fail rules:** exact on figures, scope and breakdown rows; no human grading in the loop.

### Split and repeats

- About 70% dev, about 30% locked held-out. A held-out case that is tuned against moves to dev and is replaced by a fresh case.
- Lock a held-out set of **about 600** including generated variants, with their hand-written source questions locked too.
- **3 repeats** per question; wrong if any run is wrong.
- After the pilot starts, `query_log` traffic (shadow run and pilot) is the primary evidence for the final claim. A "report wrong answer" button feeds the set.

### Buckets (reported separately)

correct; wrong (split into wrong number / wrong scope / omission / false refusal / raw dump); honest refusal; clarified. Clarified questions are neither right nor wrong, capped at **5%** of eval questions, with reason codes in `query_log`.

### Eval cases required up front

The eight live failures; one case for each of the five period rules; clarification and named-refusal cases; dirty-data cases; voice-style noisy text.

### Statistics

- 0 wrong in about 600 untuned independent questions supports 0.5% at 95% confidence (3/600).
- At most 1 wrong needs about 950 (4.74/0.005).
- **Variants of one source question count as a cluster**, not as independent questions.

## 12. Gates

### Gate A: internal ready (start shadow mode) - MET 2026-10-20 (section 25.8)

- Every launch metric has a definition, template, parity test and eval cases.
- All scope-resolver unit tests pass; the field-rendering test passes.
- Dev-set wrong rate at most **2%**.
- Model chosen by the bake-off and pinned.

### Gate B: pilot ready (the client uses it)

- **Zero wrong** in the held-out money and headcount questions, with at least **200 independent** questions in that group (zero in 200 supports at most 1.5% at 95%; internal only).
- Overall wrong rate at most **1%**, clarified at most **5%**, refusals at most **15%**.
- Every wrong answer found in held-out testing, in any group, is root-caused and fixed, with the case moved to dev and a fresh held-out case replacing it.
- Every answer states its scope and data date. The sync gates and the data-quality report are live. The "report wrong answer" button and `query_log` sampling work. Sylvester is notified of blocks.
- **The client promise is behavioural, not statistical:** every figure comes from the client's own sheet, every answer states its scope and data date, the bot says when it can't answer, and any answer can be flagged. No percentage is quoted to the client until Gate C is met.

### Gate C: the public claim

- **0 wrong in about 600 untuned independent questions, or at most 1 wrong in about 950**, with zero wrong in the money and headcount group across the whole run including pilot traffic.
- Stated exactly as: "At most X wrong in N untuned questions, 95% confidence, clusters counted once, model <pinned version>."
- Wrong-rate, clarified-rate and refusal-rate reported separately.

## 13. Build order

Each step names what it lets us measure.

| Step | Work | Measures |
|---|---|---|
| 0 | Clean baseline: land or stash the uncommitted work so a flag flip restores exactly today's behaviour. | Reproducible baseline. |
| 0.5 | Template for gathering the client's top 20 questions in their own wording. Run them through the registry and report which map to a metric, which are ambiguous and which have none, so you can decide to add or refuse. Lock the registry only after this. | Registry coverage of real questions. |
| 1 | **Eval harness first.** Runs `answer_question` against a fixture DB with independent oracle numbers; seeded with the eight live failures and the first 150 questions. | Today's baseline wrong rate; every later step shows a delta. |
| 2 | **Registry and parity.** Metric entries, then dashboard queries moved onto them (feed first, including the Feeding page), each with its parity test. **Before the Feeding page moves to the registry definition:** produce a before/after comparison of its numbers (by month and domain) and a changelog note explaining the change. | Definitions per metric = 1; parity passes; the Feeding page change is documented. |
| 3 | **Scope resolver.** Typed scope, five period rules, Africa/Harare relative periods, coverage, domain lexicon. | Scope accuracy as a pure function, no LLM. |
| 4 | **Templates.** Per-metric templates, completeness test, delete `grounding.py`. `COALESCE` zeros become explicit no-data. | Raw dumps and omissions at zero. |
| 5 | **Single routing path.** Provider interface, constrained spec, lexicon cross-check, clarification with session state, fail-closed on LLM failure, model bake-off and pin. Tiers 1 and 2 removed. | Routing accuracy, clarify rate, cost, latency. |
| 6 | **Capability catalog and refusals.** Generated from the registry, named refusals, `explain_gap` and `DATA_DICTIONARY` retired. | False-"not tracked" rate; refusal rate. |
| 7 | **Sync gates.** Staging, block and warn gates, last-good snapshot, banner, staleness, notification, acknowledgement and firing logs, dirty-data fixtures. | Gate false-positive rate; dirty-fixture wrong rate. |
| 8 | **Shadow mode.** New engine runs beside the old one behind a flag; disagreement report; "report wrong answer" button; `query_log` sampling. | Cases the written set missed. |
| 9 | **Per-group cutover:** headcount, then money, then the rest. Each group only when eval and shadow results pass. Render deploys stay manual; verify live after each. | Per-group live wrong rate. |
| 10 | Gate B, pilot with the client. | Pilot traffic evidence. |
| 11 | Gate C claim. Old engine deleted after the claim and one clean pilot month. | The 0.5% statement. |
| Later | Exploratory lane (semantic-layer composition, or NL-to-SQL), labelled "Exploratory, not verified", read-only over curated views, with a separate error budget. **Stays off until both prerequisites hold:** (a) per-farm isolation is tested, with cross-farm probe cases in the eval; (b) a read-only database role with row-level security exists (plus statement timeout and row limit). | Separate budget. |

## 14. Cutover details

- New engine in a new module behind a config flag; old path untouched; rollback is a flag flip, no redeploy.
- Shadow mode: the old engine answers; the new engine also runs on the same question and logs its answer to a separate table. A person labels disagreements.
- With a handful of users (assume 20 to 100 questions a week), shadow mode finds missed cases but cannot carry the claim; the held-out set and pilot traffic do.

## 15. Resolved items and remaining risks

**Resolved in review:**

1. **Follow-ups and multi-part questions:** see section 6. Multi-part answering is on the backlog.
2. **Mixed currency vs the 10× jump:** block on explicit mixed-currency evidence (invalid or missing code, a non-USD marker in the data); warn on the 10× jump (section 9).
3. **`Book2.xlsx`:** stays untracked and is listed in `.gitignore`. It is not committed.
4. **Notifications:** email during the pilot.
5. **Exploratory lane and NL-to-SQL:** off until per-farm isolation is tested and a read-only database role with row-level security exists (section 13, "Later").
6. **Feeding page change:** a before/after comparison and a changelog note are produced before it moves to the registry definition (section 13, step 2).

**Still to fill in or confirm:**

7. The weekly question volume (assumed 20 to 100).
8. The client's currency (USD stated; edit if it differs).

**Risks to watch:**

9. The reconciliation tolerance (default 5%) is a guess until real data exists; it is report-only and per-farm until calibrated (section 16).
10. Voice input adds transcription noise; the eval includes it.
11. Tenancy is only partly designed: it matters for the exploratory lane (item 5) and for any multi-farm deployment.

## 16. Registry definitions agreed at step 2 (2026-10-15)

1. **Mortality** = deaths ÷ animals at risk. For a batch, at risk = animals placed. For a period, at risk = headcount at
   the start of the period + animals added during it. The denominator is stated in every answer.
2. **Average weekly feed cost** = total consumed cost ÷ days covered × 7; the days used are stated. Feed *purchases*
   for the pigs (eval case fp03) is 13,308.50.
3. **Feed cost per animal** (renamed from "cost per animal") = feed consumed cost ÷ average headcount (mean daily
   headcount over the days logged). **FCR** = feed kg ÷ weight gained kg per batch, between its first and latest weight
   sample (a pig batch's starting weight counts as the first sample); a batch without two samples gets a named refusal.
4. **A period outside a table's records** answers "No <metric> recorded for that period; latest record is <date>"
   (or "earliest record is" before the first record), never 0. Zero is only returned inside coverage. A partly covered
   period is answered with its coverage flagged.
5. **By-domain expense views** show unallocated costs as "Shared (not allocated)" and the rows always sum to the total.
   A profit for a single domain excludes those costs; farm-wide profit includes them.
6. **Batch count** answers both: "N batches in total, M active". Active = status is not Sold and not Closed. Only
   active batches can be ready for market or overdue.

7. **Sow count** is a registry metric (`sow_count`): sows on the farm (not culled) with the split by current status
   (Open, Served, Pregnant, Lactating). The register keeps only each sow's current status, so it always answers "now".
   "How many sows?" is a normal answerable question (eval case hc08), not a refusal.
8. **Feed consumption reconciliation is report-only at launch.** On the synthetic data the 5% tolerance flags 17 of 20
   month-and-domain pairs (the inventory's `used_kg` and the daily log are independent sources and disagree), so it
   would be noise as a warning. It is listed in the data-quality report with no banner and no caveat on answers.
   The tolerance is a **per-farm setting** (default 5%), to be calibrated on the first month of real data before the
   check is promoted to a warn. Section 9's severity table is updated accordingly.

Also at this step: the metric registry (`registry/`, 21 metrics: the 19 planned plus `crop_plantings`, kept so the
existing area-planted and crop-types answers don't disappear, and `sow_count`), dashboard parity tests, the one-time
`query_log` startup migration (`registry/migrations.py`), and `registry/CHANGELOG-dashboard.md` (the Feeding page before/after note).

## 17. Resolver details agreed at step 3 (2026-10-15)

Relative phrases, all resolved in code against the calendar date in Africa/Harare:

| Phrase | Resolves to |
|---|---|
| last week | the previous full week, from the farm's first weekday (default Monday, so Monday to Sunday); the week start is a per-farm setting (`farm_settings.week_start`) |
| this week | the current week from that weekday |
| last 7 days (or any N days, weeks, months) | a rolling window ending today, today included (7 days = today and the 6 before) |
| last month, this month, last quarter, this quarter, last year, this year | the whole calendar period (coverage then says if the data reaches it) |
| year to date | 1 January to today |
| same day last month / same day last year | one date: today minus one month or one year, clamped to the last day of a shorter month (31 Mar gives 28 Feb, or 29 in a leap year; 31 May gives 30 Apr); 29 Feb minus a year gives 28 Feb. The resolved date is echoed on the first line, e.g. "same day last month (28 Feb 2026)". |

A snapshot question that names a past date (such as "same day last month") is answered as of that date.

**Comparisons of periods are a named refusal in v1.** "This month vs last month", "same day last month compared to today",
"higher than last year": the bot says it can't compare two periods yet and suggests asking for each separately. Comparing
domains ("compare piggery and poultry costs", "pigs vs chickens in March") is not affected. Before this was added, the
comparison words were silently dropped and one of the two periods was answered as if it were the question; and
"same day last month" silently meant the whole of last month.

## 18. Post-launch list

1. **Two-scope comparison:** answer "vs last month" and "same day last month compared to today" by resolving two scopes and
   computing the difference in code (never by an LLM), with both periods echoed.
2. **Multi-part questions:** answering several parts in one turn (v1 asks which part first).
3. **Exploratory lane** (semantic-layer composition, then NL-to-SQL), after per-farm isolation and a read-only role with
   row-level security exist (section 13).
4. **"To date" and "so far" as all-time words** if real usage shows farmers mean them that way (v1 keeps the four agreed
   scope words plus "all-time" and "lifetime").

## 19. Step 4: templated answers (2026-10-15)

`render/` turns a structured registry Result plus the resolver's Resolution into the answer, with no LLM: one template per
metric (21), the fixed layout (echoed scope on line 1; figures with the breakdown, every row, largest first, a monthly
series chronological; the result's own notes such as the denominator; a partial-coverage note; "Data through <date>.";
the "Say 'all time' ..." hint only when the dashboard filter changed the answer). Currency comes from
`farm_profile.currency`; dates read "15 Sep 2026"; domains read "Piggery", "Shared (not allocated)".

The completeness test fails if any field or row of a result is not read by its template (and a figure shown only through
a note must really appear in that note). With the router given the gold spec, every answerable dev case scores correct with
the eval scorer, so what remains of the error budget is routing (step 5).

**`chatbot/grounding.py` is not deleted yet.** The old engine imports it, and the strangler plan keeps the old engine
(and the flag-flip rollback) working until cutover. It goes when the old engine does, at the end of step 9, together with the
regex scaffolding. The new path does not use it.

## 20. Step 5: the single routing path (2026-10-19)

Decisions, all agreed at the start of the step:

1. **One LLM call, a closed spec.** The router returns a JSON object constrained to the registry's closed enums (metric, dimension,
   aggregation, grain, domains, period phrase, refusal class). It sees the question text only, never farm data. Anything outside the
   enums is a validation problem, not a guess.
2. **Disagreement means ask or refuse, never a silent pick.** The scope resolver and the deterministic cues (domain lexicon, direction
   of money, breakdown wording) read the same words independently. When they disagree with the spec the answer is a numbered
   clarifying question with a reason code. Two things keep this from becoming noise: an all-time disagreement is only asked about when a
   dashboard filter could change the answer, and a period phrase the model tidied (a typo fixed) is harmless because the resolver reads
   the period from the user's own words.
3. **A model alone never says "not tracked".** A named refusal that makes that claim needs the user's own words behind it. If it does
   not, or the wording reads two ways (outstanding payments, "treated for illness", "weather today"), the answer is a question between the
   nearest tracked metric and the "not tracked" explanation. A vague question about a section or the farm is asked about, not refused.
4. **Prompt tuning on the dev set only.** The locked held-out set is not used. No dev question is copied into the prompt; the examples are
   invented. Every prompt change is a new `PROMPT_VERSION` with an entry and the measured result in `router/PROMPT_LOG.md`.
5. **Candidates are compared on the five-way split, cost and latency** (correct, wrong by cause, refused, clarified), against the
   targets: wrong at most 2% on dev, clarified at most 5%, **cost at most 1 cent a question, median latency under 3 s, p95 under 6 s**.
   Candidates: `gpt-4o-mini`, `gpt-4.1`; `claude-haiku-5-5` is skipped until an Anthropic key exists.
6. **The model is pinned only after the comparison**, and provisionally until the locked-set run at Gate A (`router.llm.PINNED_MODEL`).
7. **If the LLM call fails, the bot falls back to the phrase tier for exact matches only** (`EXACT_PHRASES` in `router/pipeline.py`, 13
   phrases) and otherwise says it cannot process questions right now. It never guesses. (Retries with backoff were added afterwards: section 22.)
8. **Session state remembers clarification choices.** The session record holds the previous metric (for "and for poultry?"), the pending
   clarifying question with what each option means (so "1" or "reply 2" is applied to it), and any choice between two named metrics,
   which is not asked again in that conversation. A reply settles only its own disagreement; any other check still runs.

Fixes made in the step (causes, found on the first gpt-4o-mini run, 134 of 176 correct and 3 wrong):

| Cause | Fix |
|---|---|
| Feed cost routed to `expenses` with category "feed" (3 wrong answers) | "feed" was listed as an example category in the prompt. Removed; feed has its own metrics; `expenses.does_not_answer` and `feed_consumed_cost.answers` say so. |
| `none / out_of_scope` for answerable questions | The metric field now says to match by meaning and use `none` only when nothing could answer even in part; the registry `answers` texts name the plain ways of asking (harvested, on hand, ready to sell, today's weather, combined headcount, sold or closed). |
| Revenue crashed on `dimension: domain` | `registry/money.py` treats it as the default view. Regression test added. |
| Metrics with no breakdown or weekly average were given one | The catalogue states per metric: breakdowns, average per week, month by month. A dimension "domain" on a multi-section metric is its default view. |
| A breakdown nobody asked for ("how many pigs died" given per batch) | A dimension without breakdown wording (and no batch code) is asked about. |

Results on the 176 dev cases, 3 repeats (a case is wrong if any repeat is wrong). The harness uses the local `farm_intelligence_test`
database only.

| Run | Correct | Wrong | Refused | Clarified | Cost / question | Latency median / p95 |
|---|---|---|---|---|---|---|
| gpt-4o-mini, prompt v1 | 134 (76.1%) | 3 (1.7%) | 22 (12.5%) | 16 (9.1%) | $0.00037 | 1.55 s / 2.98 s |
| gpt-4o-mini, prompt v2 | 161 (91.5%) | 1 (0.6%) | 8 (4.5%) | 6 (3.4%) | $0.00042 | 0.81 s / 1.03 s |
| gpt-4o-mini, prompt v3 | 162 (92.0%) | 0 | 4 (2.3%) | 10 (5.7%) | $0.00049 | 0.82 s / 1.02 s |
| gpt-4o-mini, prompt v4 | 165 (93.8%) | 0 | 3 (1.7%) | 8 (4.5%) | $0.00048 | 0.81 s / 1.02 s |
| gpt-4.1, prompt v4 | 170 (96.6%) | 0 | 0 | 6 (3.4%) | $0.00640 | 0.64 s / 0.76 s |

Both candidates meet every dev target; zero wrong in the 117 money and headcount cases. This is a dev figure, tuned against, and says
nothing about the held-out rate. **Provisional pin: `gpt-4o-mini`**, the cheapest that meets the target (13 times cheaper than gpt-4.1,
which is the fallback if the locked run shows false refusals). Known weaknesses of the smaller model: a plain "total feed cost" is
refused in about 1 repeat in 3 (cases sc01 and sc07), and it still misses a section word in "day-old chicks" and "feed cost per pig"
(asked, never guessed). The remaining dev clarifications are deliberate: "outstanding payments" and "treated for illness" read two ways.

Measurement notes: gpt-4.1 is rate limited on this key at 450k tokens a minute, so the runner has `--pace` (it spaces call starts and is
outside the timed section); the first two gpt-4.1 attempts were discarded because over half the calls failed on the limit. Costs use
`router/llm.py` `PRICES`, which are config and must be checked against current price lists.

## 21. Steps 6 to 11 and what each lets us measure

| Step | Scope | Lets us measure |
|---|---|---|
| 6 Capability catalog and refusals | Generate the catalog and the "what I can answer" help from the registry; keep the small hand-written "known untracked" list; retire `explain_gap` and `DATA_DICTIONARY` once the new path replaces them. | False "we don't track that" rate; refusal rate. |
| 7 Sync gates (built, section 26) | Staging copy and swap-on-pass, block and warn gates, last-good snapshot with banner and staleness, email on a block, acknowledgement and firing logs, dirty-data fixtures. | Gate false-positive rate; wrong rate on the dirty fixtures. |
| 8 Shadow mode (built, section 27) | The new engine runs beside the old one behind a flag, logging to a separate table; disagreement report; "report wrong answer" button; `query_log` sampling. | Questions the written set missed. |
| 9 Per-group cutover | Headcount, then money, then the rest; each only when eval and shadow results pass; manual Render deploys, verified live. `grounding.py` and the old engine stay until the end of this step. | Live wrong rate per group. |
| 10 Gate B pilot | The client uses it: held-out run (zero wrong in at least 200 independent money and headcount questions), sync gates and the data-quality report live. | Pilot traffic evidence. |
| 11 Gate C claim | At most X wrong in N untuned questions at 95% confidence, clusters counted once, pinned model named. The old engine is deleted after the claim and one clean pilot month. | The 0.5% statement. |

## 22. Step 5 follow-ups (2026-10-19)

**Retries and the busy reply.** The router retries transient failures only (rate limit, timeout, connection error, HTTP 408, 409, 429,
5xx, 529): three attempts, waiting about 1 s and then 2 s with 25% jitter (`router.llm.RETRY_DELAYS`). Failures that retrying cannot fix are
never retried: a refusal, bad JSON, bad credentials, and an **exhausted account** (OpenAI's `insufficient_quota` arrives as HTTP 429 but is
not a rate limit, so it is reported as `InsufficientQuota`). When retries run out on a transient failure the reply is "I'm busy right now
and couldn't process that. Please try again in a minute." (code `llm_busy`); for any other failure it is the "can't process questions right
now" reply (`llm_unavailable`). Nothing is computed or guessed in either case. The latency figures include the waits.

**The phrase tier is an outage fallback for exact matches only.** `EXACT_PHRASES` in `router/pipeline.py` holds **13** phrases (pigs,
chickens and animals headcount; batches; sows; profit; revenue (two wordings); who owes us (two wordings); total expenses; feed cost; feed
left). It answers only when the model could not be used and the whole question, after normalising case and punctuation, equals one of them.
With the model up they are routed like any other question. A test pins the size at 13, so growing it is a visible, reviewed change.

**Why gpt-4o-mini refused a plain "total feed cost" about one repeat in three (cases sc01, sc07).** Temperature is 0 in the adapter
(confirmed by a test), but OpenAI chat models are not deterministic at temperature 0 (the responses carried more than one system
fingerprint). On a probe of 30 calls per setting with prompt v4 and the question "What's our total feed cost?":

| Model, setting | Routed to `feed_consumed_cost` | Routed to `none` | Cost / call |
|---|---|---|---|
| gpt-4o-mini, json_schema (current), temperature 0 | 0 | 30 | $0.00049 |
| gpt-4o-mini, json_schema, temperature 0, fixed seed | 0 | 30 | $0.00049 |
| gpt-4o-mini, forced strict function call | 30 | 0 | $0.00050 |
| gpt-4.1, json_schema | 30 | 0 | $0.00657 |
| gpt-4.1, forced strict function call | 30 | 0 | $0.00671 |

On that one question the mode decides the outcome, at the same cost, and gpt-4.1 is correct in both modes at about 13 times the cost. But
the probe overstates it. The same json_schema setting gave `none` 30 of 30 times in the probe and only 1 in 3 in the eval an hour earlier,
so the backend varies over time. And on the **full dev set the forced function call is no better**: it fixes sc01 and sc07 but other
borderline cases of the smaller model flip to refusals or clarifications instead.

| gpt-4o-mini, prompt v4, 176 cases x 3 | Correct | Wrong | Refused | Clarified | Cases that flipped in some repeat |
|---|---|---|---|---|---|
| json_schema (default) | 165 (93.8%) | 0 | 3 | 8 (4.5%) | 3 (sc01, wt04, hy04) |
| forced tool call | 165 (93.8%) | 0 | 4 | 7 (4.0%) | 4 (rv05, wt04, wx02, cr02) |

So the roughly one-in-three refusals are the smaller model's uncertainty on borderline wording, which moves around between settings and runs
rather than going away. The default stays `json_schema` (the mode of every figure here); `tool` stays available as an option. If a
borderline false refusal matters for the pilot, gpt-4.1 (0 refused, 6 clarified) is the remedy, at the cost shown above.

**Property test.** `tests/test_registry_declared_combinations.py` runs every registry metric with every dimension it declares (and every
dimension the router's validator lets through), every aggregation and grain, alone and combined, in every domain scope it supports: 138
cases. Reverting the revenue `domain` fix makes 8 of them fail. A second test pins the validator to the registry's own declarations.

**An interruption worth recording.** Partway through this round every call returned HTTP 429 `insufficient_quota` ("You have no
credits remaining") for a while, then worked again. That run was discarded and is not in the figures; the results here were taken with
credit. It is why an exhausted account now has its own non-retried error: it must not be reported as "busy, try again in a minute".

### Headline results (dev set, 176 cases, 3 repeats, prompt v4, `json_schema` mode)

| Model | Correct | Wrong (by cause) | Refused | Clarified | Cost / question | Latency median / p95 |
|---|---|---|---|---|---|---|
| gpt-4o-mini | 165 (93.8%) | 0 | 3 (1.7%) | 8 (4.5%) | $0.00048 | 0.81 s / 1.02 s |
| gpt-4.1 | 170 (96.6%) | 0 | 0 | 6 (3.4%) | $0.00640 | 0.64 s / 0.76 s |
| claude-haiku-5-5 | not run (no Anthropic key) | | | | | |

Money and headcount: 0 wrong of 117 for both. **Gate A, "dev wrong rate at most 2%", is met (0% for both), but the dev figures were tuned
against: the prompt and the cross-checks were changed in response to dev cases, so 0% is not an estimate of the held-out rate.** The other
Gate A items (every launch metric has a definition, template, parity test and eval cases; resolver and rendering tests pass; the model is
chosen and pinned) were not re-audited in this round, and the pin is provisional with one of the three candidates untested.

## 23. Decisions and checks, round two (2026-10-19)

### 23.1 Provisional default model: gpt-4.1 (json_schema mode)

`router.llm.PINNED_MODEL = "gpt-4.1"`; `gpt-4o-mini` stays selectable as the cheap option (`make_client("gpt-4o-mini")`, `--model`). Reasoning:
in a probe of 30 calls, gpt-4o-mini in its default mode answered "none" for a plain "What's our total feed cost?" every time, and in the
dev eval it refused that wording in about one repeat in three; the forced-tool-call mode fixed that wording but moved the failures to
other borderline wording (section 22). gpt-4.1 routed it correctly in every call and mode, has fewer false refusals on the dev set (0 against
3) and is under the 1-cent ceiling ($0.0066 against $0.0005 a question, about 13 times more). The pin is **provisional** until the
comparison includes the Claude candidate (no Anthropic key yet) and the locked-set run. Re-run both before any change.

### 23.2 Gate A audit (`python -m evals.gate_a_audit`, `tests/test_gate_a_audit.py`)

| Gate A item | Result | Detail |
|---|---|---|
| Every launch metric has a definition | **Pass** | 21 of 21 |
| ... a template | **Pass** | 21 of 21; the completeness test fails if a result field or row is not rendered |
| ... a parity test | **Pass with exemptions, needs sign-off** | 12 of 21 have a dashboard figure and a parity test. 9 have no dashboard counterpart (feed purchases, profit, feed cost per animal, labour, batch count, sow count, feed stock, market readiness, weather); each records why, and every one of them is checked against the independent oracle on all its dev cases. The plan's item 8 cannot be met literally where no dashboard figure exists |
| ... eval cases | **Fail against a proposed N** | The plan never set N. At a proposed 5 for the zero-tolerance metrics and 3 for the rest, 18 of 21 pass; below it: feed cost per animal 3 of 5, sow count 3 of 5, weather 2 of 3. Dev cases are Sylvester's to approve, so none were added |
| Resolver and rendering unit tests at 100% | **Pass** | all pass (800+ tests), and line coverage of `resolver/` and `render/` is 100% (621 statements; it was 98%, and closing the gap found a real bug: the second month of "from March to May" was silently dropped) |
| Dev wrong rate at most 2% | **Pass, tuned** | 0% for both candidates; tuned against, so not an estimate of the held-out rate |
| Model chosen by bake-off and pinned | **Provisional** | gpt-4.1 pinned provisionally; Claude not compared |

**Verdict: Gate A is not yet met.** Open: set N and add the missing dev cases (or accept the numbers), sign off the 9 parity exemptions, run the
Claude comparison, then confirm the pin on the locked set.

### 23.3 Quota alerts

`router/alerts.py` writes every `insufficient_quota` error to the `llm_quota_log` table (migration 004: day, provider, model, error, the
provider's own message, whether it triggered the day's email, why an email was not sent) and sends one email the first time one occurs each
Africa/Harare day, so a stalled bot is noticed without flooding the inbox. If sending fails or email is not configured, the row says why
and the next occurrence tries again. The email never contains a key. Settings come from the environment only: `ALERT_SMTP_HOST`,
`ALERT_SMTP_PORT`, `ALERT_SMTP_USER`, `ALERT_SMTP_PASSWORD`, `ALERT_EMAIL_FROM`, `ALERT_EMAIL_TO` (the recipient is configuration, not code).
**User actions, not code:** turn on billing alerts and auto-recharge on the OpenAI account, and set the `ALERT_*` variables where the app runs. The app
should call `registry.migrations.migrate` once at startup so the table exists. This round the account ran out of credit once; the email
would have named it.

### 23.4 Untuned probe: generated variants of the dev questions

`python -m evals.variants generate` makes three variants of each of the 176 dev questions: **typo** (code, seeded), **paraphrase** and
**mixed** (English with Shona or Ndebele words, from a fixed glossary so the meaning cannot drift), 523 in all (a few rewrites were refused
or unchanged and were dropped). They are in `evals/variants/dev_variants.json`, every one marked `generated: true`, and 104 (20%, stratified
by kind) are in `evals/variants/spot_check.csv` for a person to confirm "same meaning" and "natural wording". **That spot-check has not been
done**, and until it is, a "wrong" here may be a rewrite that changed the question. The variants of one source form a cluster (176 clusters).
The generating model also routes, so this probe is somewhat optimistic.

**The original untuned variant wrong rate (prompt v4, 3 repeats, before any fix made because of the probe) is: gpt-4.1 15 wrong of 523
variants (2.9%), gpt-4o-mini 17 wrong of 523 (3.3%).** These are the only untuned variant figures. After Sylvester's decision of 2026-10-20 to
remove the three rewrites whose meaning drifted (`fc06-pa`, `fp03-pa`, `pf06-mx`; recorded with reasons in `evals/variants.py` `REMOVED`, and
excluded from any regenerated or loaded set), the same untuned runs read: gpt-4.1 12 wrong of 520 (2.3%), gpt-4o-mini 17 wrong of 520 (3.3%).
Every figure from a later run on these variants is **tuned**: fixes were made from these failures, so it is not evidence about unseen questions.

| Run | Correct | Wrong | Refused | Clarified | Wrong, money + headcount |
|---|---|---|---|---|---|
| gpt-4.1, tuned dev set (176) | 96.6% | 0 | 0% | 3.4% | 0 of 117 |
| **gpt-4.1, variants, UNTUNED (523 as run)** | 74.4% | **15 (2.9%)** | 4.2% | 18.5% | 10 of 351 |
| gpt-4.1, variants, UNTUNED (520 after removal) | 74.8% | 12 (2.3%) | 4.2% | 18.7% | 7 of 348 |
| gpt-4o-mini, tuned dev set | 93.8% | 0 | 1.7% | 4.5% | 0 of 117 |
| **gpt-4o-mini, variants, UNTUNED (523 as run)** | 61.8% | **17 (3.3%)** | 16.1% | 18.9% | 13 of 351 |
| gpt-4o-mini, variants, UNTUNED (520 after removal) | 62.1% | 17 (3.3%) | 15.6% | 19.0% | 13 of 348 |

**Tuned afterwards** (not untuned): gpt-4o-mini on the 523 variants after the code fixes and prompt v5: 70.2% correct, 6 wrong (1.1%), 14.5%
refused, 14.1% clarified; typo 0 wrong, paraphrase 1 wrong, mixed 5 wrong. The tuned dev set did not regress (gpt-4o-mini 94.3%, gpt-4.1 97.2%,
0 wrong). gpt-4.1 was not re-run on the variants after the fixes (about $10 and 20 minutes), so there is no tuned gpt-4.1 variant figure.

### 23.5 Language support: what happens when a question is not in English

English is the supported language at launch. Everything downstream of the model is English: the period, "all time" and comparison words in
the resolver, the number words, and every reply (templates, clarifying questions, refusals). The router prompt is English, but the model
often understands some Shona or Ndebele, and the resolver's domain lexicon knows a few Shona and Ndebele nouns (pigs, chickens, maize;
to be confirmed by a speaker). What happens, as measured on the mixed-language variants:

- Usually the question is **not answered but turned into an English clarifying question** (28% for gpt-4.1, 30% for gpt-4o-mini): the
  model reads a section the lexicon cannot see, or the reverse, and the cross-check asks rather than picking.
- Sometimes it is **answered correctly** (64% for gpt-4.1, 39% for gpt-4o-mini), often because the numbers, months and batch codes
  were English.
- Occasionally it is **answered wrongly** (about 3%: 4 of 172 for gpt-4o-mini, 5 for gpt-4.1), because the model misreads a Shona or Ndebele verb or noun and nothing in the
  English cross-checks can see it ("takatengesa" read as a readiness question).

So the bot does not guess silently across languages, but it is not reliable in them, and **no claim should be made about Shona or Ndebele
until real wording from the client has been tested** (the step 0.5 top-20 list is the place to see it) and a speaker has reviewed a
glossary. Voice input adds transcription errors on top. The Gate C claim, when made, is about English questions only.

## 24. Step 6: the capability catalog (started 2026-10-20)

Done so far:

- **`catalog/`** is the one place that says what the bot can and cannot answer. What it can answer is generated from the registry (each
  metric's own `answers` / `does_not_answer`, grouped): `catalog/build.py` produces the reply to "help" and its variants, the reply to
  "what can't you answer", and `catalog/CATALOG.md` (regenerate with `python -m catalog.build`; a test fails if the committed file is stale).
  The hand-curated part is `catalog/untracked.py`.
- **Three classes of "no"**, as section 4 required: *not recorded* (accounts payable, sick right now, forecast weather, equipment, company
  details, payroll history), *recorded but no metric reads it yet* (staff and pay rates, crop scouting, crop field operations) and *not allowed*
  (changing data). The second class is new: those three tables hold 76 rows that the bot used to hide behind a generic "I can only
  answer questions about...". Their refusals say the data is recorded and what is shown instead; they never deny it.
- **One source for refusals.** The refusal text, the wording that must back a "not tracked" claim, the router prompt's refusal vocabulary, the
  closed refusal enum and the numbered "nearest metric or not tracked" question all read the curated list. Prompt v5 is the generated
  vocabulary; no other rule changed.
- **Schema coverage check.** A test fails if any table in the schema is neither read by a metric nor listed as unexposed with a class and a reason.
  It currently lists five: `farm_profile` and `list_values` (internal), and `staff`, `scouting_log`, `field_operations` (recorded, no metric yet).
  Whether chat may show per-person pay is decided in section 25.4: it may not.
- **`explain_gap` and `DATA_DICTIONARY` are not used by the new path** (a test scans the new packages for them). They are deleted with the
  old engine at the end of step 9, as `grounding.py` is.

Measured after the change (dev set, 3 repeats, prompt v5): gpt-4.1 171 of 176 correct (97.2%), 0 wrong, 0 refused, 2.8% clarified;
gpt-4o-mini 166 correct (94.3%), 0 wrong, 1.7% refused, 4.0% clarified. **False "we don't track that": 0 of 151 answerable dev questions for
both models** (the old engine: 7 of 142; the first router run: 2 of 151). Refusal rate: every refusal the gpt-4.1 run gave was an expected one.

Still to do in step 6: Sylvester's review of the draft dev cases for the new refusal classes (section 25.2), and the question of whether the
"recorded, no metric yet" tables should get metrics before launch (the client's top 20 will say). Section 25 continues this step.

## 25. Decisions of 2026-10-20 and what they changed

### 25.1 Parity exemptions

Sylvester's rule: any metric in the money or headcount groups that has an exemption must be fixed, not exempted; an exemption is approved only
for a metric with no dashboard counterpart or a documented difference. Of the nine exemptions listed in 23.2, four were fixed by finding the
dashboard figure that does exist and adding a real parity test, and five remain:

| Metric | Group | Zero tolerance | Was exempt because | Now |
|---|---|---|---|---|
| Feed purchases | money | yes | the dashboard shows expense by category | **Fixed.** The dashboard's "Feed" expense category must equal the registry figure (`test_parity_fetch_expense_breakdown_feed_purchases`) |
| Profit | money | yes | the dashboard never shows the difference | **Fixed.** Revenue line minus expense line of the Expenses vs Revenue chart must equal profit, all time and for a filter |
| Batch count | headcount | yes | the Data Coverage card is not a per-status figure | **Fixed for the part that exists.** The card's batches per domain must equal "N batches in total"; the status split (active, sold, closed) has no dashboard figure and stays covered by the oracle |
| Feed cost per animal | money | yes | no card shows a per-animal figure | **Fixed for the part that exists.** The Finance page's feed cost per domain must equal the numerator; the denominator (mean daily headcount over the days logged) is documented as different from the dashboard's month-end headcount and is checked against the independent oracle |
| Labour | money | yes | no dashboard page shows labour | **Remains. For approval:** there is no dashboard counterpart (the dashboard has no labour page or card); every dev case is checked against the oracle |
| Sow count | headcount | yes | no dashboard page lists sows | **Remains. For approval:** the Breeding table lists sow tags from service records, not the sow register; no counterpart; oracle-checked |
| Feed stock | operations | no | no dashboard page shows feed stock on hand | Remains. For approval: no counterpart |
| Market readiness | operations | no | no dashboard page lists market readiness | Remains. For approval: no counterpart |
| Weather | operations | no | no dashboard page shows weather | Remains. For approval: no counterpart |

Honest limit of parity in general: several dashboard queries now call the registry (decision D1), so those parity tests check that the page
adapts the registry's figure correctly, not that two independent calculations agree. Independent agreement comes from the oracle tests.

### 25.2 Case minimums, drafts and the Gate A count

Sylvester set N: **8 dev cases per zero-tolerance metric (money, headcount), 4 per other metric, 5 per refusal class that is new in step 6**,
covering phrasings, periods, domains and the refuse and clarify paths. The held-out target later is about 16 per zero-tolerance metric.
Against these minimums 11 of 21 metrics are met with approved cases (not the three assumed earlier: ten metrics fall short, six zero-tolerance
and four others). `evals/cases_dev_drafts.py` holds **43 draft cases, dev-only and not in `CASES`, awaiting Sylvester's review**: 23 for the
ten short metrics (including one refuse path, `dsw05`, and one clarify path, `dca05`) and 20 for the four refusal classes (staff names and
roles, per-person pay, crop scouting, crop field operations; 5 each). The questions were written before the router was run on them. Their
expected figures are checked against the registry by the oracle-agreement test (172 cases pass). With the drafts approved, `evals.gate_a_audit`
shows 21 of 21 metrics and 4 of 4 refusal classes at or above the minimum. Run them with `python -m evals.run_v2 --drafts`.

First (untuned) run of the drafts, gpt-4.1, prompt v6, 3 repeats: 40 of 43 correct, 1 wrong, 0 refused, 2 clarified. The wrong one is `dca05`
("How much does each animal cost us?"): the bot answered, labelled "Feed cost per animal", where the draft expects a question. Whether that is
a wrong answer or an acceptable labelled one is Sylvester's call when reviewing the case. The two clarifications: `dca01` ("What was the feed
cost per pig in August 2026?") asked "which part of the farm" although the question names pigs (the cross-check saw a domain word the model
did not return and asks rather than picks, as designed; it is an over-ask worth deciding on), and `dfo04` ("When did we last apply fertiliser to
the maize?") asked whether the user meant fertiliser spend or field operations, which is reasonable. Nothing was tuned to these.

### 25.3 Variant set

The three meaning-drifted rewrites were removed (section 23.4). The original untuned wrong rates and the tuned-afterwards figures are now
separated there.

### 25.4 Staff pay: chat does not show per-person pay (policy)

Decision: total labour cost, hours and overtime are answered; **what an individual is paid is never shown**. Per-person pay now has its own
named refusal, `staff_pay` (kind `policy`: the data exists, the farm has chosen not to show it), distinct from `staff_info` (names and roles:
recorded, no metric yet). The refusal says "I don't show what individual people are paid" and offers total labour cost, hours and overtime.
It is enforced in code, not left to the model: wording that asks what an individual earns, a pay rate, an hourly rate, a salary per worker
or "X's salary" gets the refusal whatever the model chose, while totals ("total salaries", "wages spent") still go to the labour metric.
Tests cover both sides. The labour metric has no per-person breakdown, so there is nothing else to hide. Prompt v6 adds the refusal to the
generated vocabulary; the refusal wording is not model-authored. This policy is a limit, not a claim: the Gate C statement covers answers
given, and a refused pay question is a correct refusal.

### 25.5 Proposal (not built): a deterministic guard for mixed-language questions

*Idea.* Before the model is called, count words that are neither English (a dictionary plus the registry and lexicon vocabulary) nor a
near-miss of one (a typo within one or two letters); if there are any, reply with an English clarifying question ("I understand English
questions best. Could you ask it in English?") instead of letting the model guess at Shona or Ndebele. The cross-checks cannot see a misread
foreign word, which is where the residual wrong answers come from.

*Measured offline on the saved variant runs (a throwaway prototype, nothing added to the repo), with the caveat that the English vocabulary
included the dev questions' own words, so false firing on English dev questions (0 of 176) is understated and needs a held-out English
sample:*

| Guard fires when | Typo variants | Paraphrases | Mixed-language | What it would have done to the mixed ones (gpt-4.1) |
|---|---|---|---|---|
| 1 or more unknown words | 13 of 176 (7.4%) | 3 of 173 (1.7%) | 123 of 171 (72%) | stops all 3 wrong answers; also turns 72 correct answers and 7 refusals into clarifications (41 were already clarifications) |
| 2 or more unknown words | 0 | 0 | 37 of 171 (22%) | stops none of the wrong answers; turns 12 correct answers into clarifications |

*Effect on the clarified-rate budget (5% on answerable questions).* On English traffic the guard costs the typo false-fires: at threshold 1,
7.4% of typo'd questions, so about 0.4 to 0.7 percentage points if 5 to 10% of questions have typos; at threshold 2 nothing. On genuinely mixed
traffic it moves the clarified rate from 28% to about 72% (threshold 1), which is the intended, honest behaviour for an unsupported language and
a clear cost if clients write that way. Threshold 2 is not worth building (it catches none of the wrong answers). **Recommendation: do not
build yet.** Wait for the client's real top-20 wording (step 0.5): if mixed-language questions are rare, the guard at threshold 1 is a cheap
way to remove a roughly 2% silent-wrong tail on that traffic; if they are common, the right fix is a speaker-reviewed lexicon and a real
multilingual test set, not a guard that refuses them.

### 25.6 Claude comparison: waived

Decision of 2026-10-20 (supersedes the earlier plan to run Claude on the dev set): **the Claude comparison is waived** because of Anthropic cost.
gpt-4.1 with prompt v6 is the pinned model. Revisit only if quality or pricing changes. No Anthropic call was made, and none is planned.

### 25.7 Quota detection fix

During the prompt v6 re-run the OpenAI account ran out of credit again. The error now arrives as code `credit_balance_exhausted` (type
`insufficient_quota`), which the detection did not recognise: the bot answered "busy, try again in a minute" and sent no alert. Detection now
accepts either code or the type (`is_quota_error`, tested). Credit has to be added again before any further model run. The gpt-4o-mini v6
dev run was discarded because 512 of its calls failed on this, so **there is no gpt-4o-mini figure for prompt v6** (v5: 94.3%, 0 wrong).
Cost control from here: no paid run without Sylvester's go-ahead and a stated estimate (gpt-4.1 about $0.0066 per question; a full dev run of
176 cases x 3 repeats is about $3.50, the 43 drafts about $0.85).

### 25.8 Gate A, item by item: FINAL (2026-10-20): MET

| Item | Result | Basis |
|---|---|---|
| Definition, template: every metric | **Pass** | 21 of 21 each |
| Parity test: every metric | **Pass** | 16 of 21 have a parity test; labour, sow count, feed stock, market readiness and weather are exempt, **approved by Sylvester 2026-10-20** (no dashboard counterpart; oracle-checked) |
| Eval cases: N per metric | **Pass** | 21 of 21 metrics at or above N (8 zero-tolerance, 4 other) and 4 of 4 new refusal classes at 5, after Sylvester approved the 43 drafts (dca05: the "Feed cost per animal" label counts as a valid answer; dfo04: a clarification is accepted as well as the refusal). Dev set is now 219 cases |
| Resolver and rendering tests | **Pass** | 1576 new-path tests pass; resolver and render line coverage 100% |
| Dev wrong rate at most 2% | **Pass (0 of 219), tuned** | gpt-4.1, prompt v6, 1 repeat. Tuned against, so not an estimate of the held-out rate |
| Model chosen and pinned | **Pass (comparison waived)** | gpt-4.1 + prompt v6, `json_schema` mode; Claude comparison waived for Anthropic cost; revisit only if quality or pricing changes |

Gate A permits starting shadow mode (step 8). It makes no claim about unseen questions; that is Gate C.

### 25.9 The test suite spends OpenAI credit

`tests/conftest.py` loads `~/.openai_api_key`, and about 20 old-engine test files (`test_chatbot_tier3_*`, `test_chatbot_tool_selection_eval`,
`test_ui_app`, `test_chatbot_grounding`) call OpenAI live, so **every full `pytest tests` run spends credit and fails if the account is empty**
(a run with the account empty gave 90 failures, all in those files; the next run gave 1650 passed and 1 flaky failure,
`test_chatbot_tier3_breeding_summary`, which passes alone and on the previous commit). The new-path tests (`router`, `registry`, `resolver`,
`render`, `catalog`, `evals`) use no key. Until the old engine is deleted (step 9) run the new-path tests with
`python -m pytest tests -q --ignore-glob='tests/test_chatbot*' --ignore=tests/test_ui_app.py` when a quick, free check is wanted. Nothing in the old
engine or its tests was changed.

### 25.10 Final dev run: prompt v6 against prompt v5, same 219 cases (gpt-4.1, 1 repeat, `json_schema`)

Cost about $2.90 of the $4 cap (438 calls at $0.0066). v5 was run from a temporary git worktree at `dfdd7af` with the current cases, so it also lacks
the staff-pay code guard: the comparison is of the two versions of prompt plus code, not of the prompt alone. One repeat, so a case that flips between
runs counts once (rc07 changed from a question to an answer with no change that touches it: noise).

| | Correct | Wrong | Refused | Clarified | Wrong, money + headcount | Cost per question | Median latency |
|---|---|---|---|---|---|---|---|
| v5 | 207 (94.5%) | 0 | 0 | 12 (5.5%) | 0 of 135 | $0.00659 | 0.71 s |
| v6 | 213 (97.3%) | 0 | 0 | 6 (2.7%) | 0 of 135 | $0.00663 | 0.71 s |

v6 clarifies less because the five per-person-pay and staff questions that v5 turned into "do you mean labour or payroll history?" now get the
named answer. The remaining six clarifications are the same in both: "to date" (ex01), three domain over-asks (ex12 "day-old chicks", ca01 "per pig",
dca01 "per pig in August 2026"), "vet care" category (he02) and "any pigs being treated for illness" (he06). The domain over-asks are the one
usefulness gap: the question names the section and the bot still asks (the cross-check sees a domain word the model did not return and asks, as designed).

Result per metric (correct / wrong / clarified / refused, v5 then v6; zero wrong everywhere): feed consumed cost 29/0/0/0 both; feed purchases 8 both;
expenses 18 + 2 clarified both; revenue 8; profit 8; feed cost per animal 6 + 2 clarified both; receivables 7 + 1 clarified (v5), 8 (v6); labour 8;
active headcount 12; batch count 8; mortality 10; sow count 8; FCR 4; weight 4; harvest yield 4; breeding 5; crop plantings 4; feed stock 4; market
readiness 4; health events 4 + 2 clarified both; weather 4; refusals and clarify cases with no metric (45): 40 + 5 clarified (v5), 45 (v6).


### 25.11 Domain over-ask fixed (2026-10-20)

A domain word in the question ("pig", "bird", "chick", "broilers"...) now names the section even when the model returned no domain: the scope is
built from the user's own words, so that is not a disagreement and the bot answers instead of asking "which part of the farm?". Asking remains
for a model that names a *different* section from the words, and for a model that names a section the words never mention. Tests updated and added
(the old tests built their disagreement from the model-silent case). Checked live on `ex12`, `ca01`, `dca01` (3 gpt-4.1 calls, about $0.02):
all three now answer correctly with the section in the first line. Not re-run on the full dev set.

Full dev run after the fix (gpt-4.1, prompt v6, 219 cases, 1 repeat, about $1.45): 215 correct (98.2%), 0 wrong, 0 refused, 4 clarified (1.8%), 0 wrong of
135 money and headcount. Against the run before the fix: `ex12`, `ca01`, `dca01` went from a question to a correct answer; `rc07` went the other way
(answer to question) and `mo09` changed wording. Neither is caused by the fix: `rc07` has flipped between runs (v5 asked, the first v6 run answered,
this run asked) and `mo09` is the model choosing whether to add a per-batch breakdown. All nine cases that should clarify still do.

## 26. Step 7: sync gates (built 2026-10-20, nothing deployed)

**What exists** (package `gates/`; migration `005_sync_gates`; the old engine and `grounding.py` untouched; no paid call, no push, no deploy):

- **Staging and swap (`gates/run.py`).** `gated_sync_workbook` / `gated_sync_sheet` load the upload into a `staging` schema inside one transaction, using
  the existing sync code unchanged (it gained an optional `conn` argument), run the gates on that copy, and then either replace the live tables or roll back.
  A rollback leaves the live tables exactly as they were, which is the "last good snapshot". The result, every firing and the snapshot state are logged on a
  separate connection. It never raises; a load that cannot finish is an `error` outcome with the live tables untouched, and also emails.
- **Gates (`gates/checks.py`).** Block: missing or invalid currency (ISO 4217 list), mixed currency (a different currency named in expense, revenue or labour
  text), units outside the workbook's own lists (`UNIT_GENERAL`, `UNIT_SALES`, `UNIT_FIELD`), duplicate primary keys (an insert that conflicts with an
  earlier row of the same upload). Warn: a month with no rows, a 10x jump or drop in an expense category between consecutive months, rows the sync rejected,
  and a value outside its `99_LISTS` list that the sync does not itself reject (a typo'd expense category). Report only: feed reconciliation, per farm tolerance
  from `farm_settings`; it never produces a banner or a caveat.
- **Last good snapshot, banner, staleness (`gates/status.py`).** After a block the chat and the dashboard status line show "Data last verified <date>. A newer
  upload is being reviewed."; once the verified snapshot is more than 7 days old it becomes "⚠️ Data last verified <date> (N days ago). A newer upload is
  still being reviewed, so these figures may be out of date." A passing upload clears it. Every answer already says "Data through <date>".
- **Caveats.** A live, unacknowledged warning adds "Note: <what is wrong> (data-quality warning, not yet reviewed)" under answers for the metrics that read the
  affected table (derived from each metric's `sources`), and only for answers whose period overlaps the warning's period. Report-only items add nothing.
- **Logs.** `sync_runs` (outcome, rows, whether the email went), `gate_firings` (gate, severity, farm, table, rows affected, period, status open /
  acknowledged / superseded / resolved, went live), `gate_acks` (reviewer, reason, time), `data_snapshot`. `store.acknowledge` accepts warnings only (never a block
  or a report item), needs a reviewer and a reason, can be limited to named reviewers (Netrisyl during the pilot), and an acknowledged issue stays acknowledged
  when the next upload shows it again. `status.data_quality_report` lists it all.
- **Email on a block** reuses the `ALERT_*` settings; each block (and each failed load) emails; a failure to send is recorded in `sync_runs`.
- **Dirty-data fixtures (`gates/fixtures.py`).** Nine defects injected into a fresh copy of the real workbook, plus an unmodified control: invalid currency,
  blank currency, four April expenses noted in ZWL, an expense in grams, a duplicated May expense row, two expenses with category "Feeed", all May expenses
  missing, July feed expenses 12x June's, February inventory use triple the daily logs.
- **Wiring.** The chat adds the banner and caveats (and does nothing if the gate tables do not exist). The Gradio app uses the gated sync only when
  `GATED_SYNC=1`; the default is the old direct sync, so nothing changes until the cutover.

**Results (`python -m evals.dirty_report`, no model calls):**

| Measure | Result |
|---|---|
| Gate false positives on the clean workbook | **0 blocks, 0 warnings**; 15 report-only reconciliation items (see below) |
| Dirty fixtures caught by the gate built for them | **9 of 9** (5 block, 3 warn, 1 report-only); the control fires nothing |
| Blocked uploads that changed the live data | 0 of 5 |
| Answers that changed with no banner or caveat (10 fixtures x 173 gold-spec dev questions = 1,730 answers) | **0 silent-wrong** (0 of the 134 zero-tolerance questions per fixture); 39 answers changed and were all caveated |

Tests: 39 for the gates end to end (`tests/test_gates_dirty.py`, `tests/test_gates_checks.py`) and one that runs all fixtures and fails on any silent change
(`tests/test_gates_silent_wrong.py`). The new-path suite is 1,622 passing.

**Design choices to confirm (Sylvester):**

1. **Replace, not merge.** The live tables are now replaced from staging, so a row deleted from the sheet disappears from the app. The old sync only upserted and
   kept deleted rows. This is the behaviour the dashboard's docstring already assumed.
2. **Two warnings beyond the plan's table:** "rows the sync rejected" and "value outside its list". Both are missing or mislabelled money, so they carry caveats; say
   if either should block.
3. **Month-without-rows is batch-aware for the daily logs.** A month in which no batch was on the farm is not a gap (the clean workbook has four such poultry months and
   a plain check warned on all four). Months inside a batch's span with no log rows do warn. Other tables use first month to last month.
4. **A failed load is an `error`, not a hold-back.** It emails, and one failure shows no banner ("a newer upload is being reviewed" would not be true). **Decided 2026-10-20:
   after 2 consecutive failed loads the stale banner shows** ("⚠️ Data last verified <date> (N days ago). The last N uploads could not be loaded, so these figures may be out of
   date."); a block or a good load breaks the streak. Choices 1, 2, 3 and 5 below were approved the same day.
5. **Reconciliation at the default 5% flags 15 months of the clean synthetic workbook** (the daily logs and the inventory sheet were generated separately). It is
   report-only as planned; the tolerance is a guess until the first month of real data.

**Not done, and risks:** (a) the Google Sheets path (`gated_sync_sheet`) is a thin wrapper and was not run against a real Sheet; (b) the single-transaction load
with `SET LOCAL search_path` is written for Supabase's transaction pooler but not tested there; (c) more fixtures would help (text in number cells, a missing tab,
dates in the wrong format); (d) the gate false-positive rate is measured on one clean workbook, so it is an upper-bound check, not a rate.
**User actions:** call `registry.migrations.migrate` once at app start (creates the four tables); set the `ALERT_*` variables where the app runs; set `GATED_SYNC=1`
only at the cutover (step 9). Nothing was pushed or deployed.

## 27. Step 8: shadow mode (built 2026-10-20, not switched on anywhere)

**What exists** (package `shadow/`; migration `006_shadow_mode`; the old engine and `grounding.py` untouched; no paid call, no live connection, no push, no deploy):

- **Running beside the old engine (`shadow/runner.py`).** With `SHADOW_MODE=1`, `handle_message` still returns the old engine's answer unchanged and undelayed; it then
  hands the question, the old `Answer` and the dashboard date range to a background pool (2 threads). The new engine answers on its own connection and the result goes to
  `shadow_log` only: the new answer's text, kind, reason code, metric, scope, model, prompt version, latency, cost, and the old engine's kind, source and reason. It never
  raises, and a missing table, an exhausted ceiling or a crash in the new engine is logged or skipped, never shown. Verified by test that shadow writes to no table but its own.
- **Bounded cost.** `SHADOW_SAMPLE` (default 1.0) shadows a fraction of questions; `SHADOW_DAILY_LIMIT` (default 200) is a hard daily ceiling, so the most it can spend is
  200 x about $0.0066 = about $1.30 a day with gpt-4.1. `SHADOW_MODEL` defaults to the pinned model.
- **Comparing (`shadow/compare.py`).** The old engine returns prose, so figures are compared by the numbers in the text (dates, years, batch codes and the data-through line
  removed). Classes: `agree` (one set of figures inside the other), `disagree`, `new_asks` and `new_refuses` (old answered, new did not), `old_misses` (old declined or
  asked, new answered), `both_decline`, `unclear` (no figures to compare) and `new_error`. Everything except `agree` and `both_decline` waits for a human label.
- **Disagreement report and labels (`shadow/report.py`).** `text_report` and `export_label_sheet` (a CSV with blank label and note columns); labels `old_right`, `new_right`,
  `both_right`, `both_wrong`, `unclear`, each with a reviewer. `new_wrong` (labelled old_right or both_wrong) is the live-wrong evidence step 9 needs, also per metric.
- **"Report wrong answer" button (`shadow/reports.py`, `ui/app.py`).** Sits in the chat tools; saves the last question and answer, an optional note, the engine, and a link to the
  shadow row, to `wrong_answer_reports`. Hidden unless `SHADOW_MODE=1` or `REPORT_BUTTON=1` (the pilot switch). `export_for_review` writes the reports as a CSV of draft cases;
  nothing adds an eval case without Sylvester.
- **`query_log` sampling (`shadow/sample.py`).** A seeded, reviewable sample of what people asked the old engine, with questions the written set and the variants already cover
  removed (compared after normalising case and punctuation); every question the old engine failed on, was scoped out of or asked about comes first, then a random draw of answered
  ones; CSV with blank columns for "what should it say" and "add to dev set".

**Tests:** 32 in `tests/test_shadow.py` (classification matrix, each outcome class, a crashing new engine, writes only to `shadow_log`, sampling and the daily ceiling, off by
default, background submit, the user always getting the old answer even when shadow fails, button visibility, labelling, the report, sampling).

**Design choices to confirm:**

1. **No conversation state in shadow.** The old engine has no multi-turn memory, so shadow calls the new engine with no session: a reply like "1" to a clarifying question is logged as a
   follow-up without context, not compared. Real conversational behaviour is tested by the eval, not by shadow.
2. **Number matching is a rough comparator.** It will call two different-looking but consistent answers `unclear` and send them to a person; it can call two answers with a shared
   figure `agree`. That is acceptable for finding missed cases, not for the claim.
3. **The shadow run costs model calls on real traffic.** At 20 to 100 questions a week it is cents a week; the ceiling is for safety.

**Not done, and what stands between this and live (all need Sylvester's go-ahead; none was touched):** run `registry.migrations.migrate` on the Supabase database (creates
`shadow_log` and `wrong_answer_reports`); make `OPENAI_API_KEY` available to the app process; set `SHADOW_MODE=1` (and `REPORT_BUTTON=1` for the pilot); a manual Render deploy,
verified live. Not tested here: the background pool inside the real Gradio process, and the Supabase transaction pooler with a second connection per shadow run.

### 27.1 Supabase migration for steps 7 and 8 (run 2026-10-20)

Migrations `005_sync_gates` and `006_shadow_mode` were applied to the production Supabase database (Sylvester confirmed it is the database Render uses; pooler `aws-0-us-west-2.pooler.supabase.com:6543`, database
`postgres`) with `registry.migrations.migrate_in_transaction(only=...)`: one transaction, a transaction-scoped lock, create-only SQL. Migrations 001 to 004 were NOT applied
(they would add columns to `query_log` and create `farm_settings` and `llm_quota_log`; nothing in steps 7 and 8 needs them yet). Verified afterwards: the seven new tables exist
(`schema_migrations`, `sync_runs`, `gate_firings`, `gate_acks`, `data_snapshot`, `shadow_log`, `wrong_answer_reports`), and the row count of each of the 23 existing tables is unchanged
(including `query_log` at 343 and `labour_log` at 1,143). `GATED_SYNC` and `SHADOW_MODE` stay unset everywhere, so nothing uses the new tables yet.
Rollback, only the new objects (not run): `DROP TABLE IF EXISTS wrong_answer_reports, shadow_log, gate_acks, gate_firings, data_snapshot, sync_runs, schema_migrations;`
(indexes and sequences go with their tables). Row-level security is off on the new tables, as on the existing ones: check the Supabase API exposure of `public`.

### 27.2 Shadow failures made visible (2026-10-21)

The first live run wrote no `shadow_log` rows. A crash of the new engine itself would still write a row (`new_kind = error`), so the failure had to be before the insert: the
shadow thread is the first place the production process imports `router`, `resolver`, `render` and `catalog` (the dashboard only imports `registry`), and `resolver/periods.py` builds
`ZoneInfo("Africa/Harare")` at import time while `requirements.txt` had no `tzdata`. That is the leading suspect, unconfirmed. Whatever the cause, the code hid it: the app's `_shadow`
hook swallowed every exception with no log, and `run_shadow` logged only the exception's type name. Now: failures log type, message and traceback (never the question or the DSN) under the
`shadow` logger; the app configures logging at start-up (`%(asctime)s %(levelname)s %(name)s`) and says whether shadow mode is ON, or warns when `SHADOW_MODE` is set to anything other than
exactly `1`; skips (sampling, daily ceiling) and each logged row are INFO lines; `tzdata` is in `requirements.txt`. Tests cover each. Needs a push and a manual Render deploy to take effect.

### 27.3 Named-entity answers (2026-10-21)

Found in `shadow_log`: "How many deaths were there in batch BRO-P02?" was answered with a ranking of all eight batches led by "Highest: PIG-B02 at 15.38%", under a first line that said
"batch BRO-P02". **Cause (code read):** the model added `dimension = batch`; in `registry/headcount.py` the dimension branch (and the monthly branch) ran before the named-batch branch and
ignored `scope.batch_code`, so the filter was printed on the first line and not applied. The dev scorer passed it, because the right figure (42 deaths) was in the list.

**The same pattern elsewhere (list):** (1) `mortality`: dimension and month views ignored the named batch (fixed); (2) `fcr`: a named batch led with "Best: X; worst: X" (a ranking of one); (3) `weight`: a
named batch led with a generic header line; (4) the larger one: only `mortality`, `fcr` and `weight` read `scope.batch_code`. Every other metric (feed cost, cost per animal, headcount, health events,
market readiness, expenses, revenue ...) ignored a batch code in the question while the first line still said "batch X": a farm-wide figure labelled as one batch's. `harvest_yield` and `breeding` also
open with a best-and-worst line, but have no entity filter at all (a plot or sow name is not part of the scope), so they are not misleading; they are listed for later.

**Fix.** (a) `Metric.batch_filter` says which metrics can answer for one batch (`mortality`, `fcr`, `weight`). (b) The resolver refuses a batch code on any other metric with a named message
(`batch_filter_unsupported`: "I can't show <metric> for a single batch yet. I can show it for the whole farm or one section: ask again without the batch code."), so a batch label is never printed
over a figure that is not about that batch; and more than one batch code is a question (`multiple_batches`), not a silent pick of the first. (c) `mortality` answers a named batch first whatever
dimension or grain was added, and its monthly view honours the batch. (d) `fcr` returns `{batch, fcr}` for a named batch (no best and worst); `weight` leads with the batch row. Without a named batch
the rankings are unchanged ("Which batch has the worst mortality?", "worst FCR"). 32 tests in `tests/test_named_entity.py` (mortality, fcr, weight, the refusal for every metric without batch support,
two batches, and a property test that every batch-filtering metric returns only the named batch in every dimension and grain); the mortality ones fail on the old code.

**Dev run after the fix** (gpt-4.1, prompt v6, 219 cases, 1 repeat, about $1.45): 216 correct (98.6%), 0 wrong, 0 refused, 3 clarified (1.4%); 0 wrong of 135 money and headcount. Nothing got worse.
Changed: `he02` clarified to correct (a flip between runs, unrelated); `mo09`, `fcr3`, `dfr01`, `wt01`, `wt04` kept their outcome and now lead with the named batch's figure. Follow-ups for
Sylvester: (1) the scorer could require that `mo09` contain no "Highest:" (it passed the broken answer; a dev-case change, so not made); (2) real per-batch support for headcount, feed cost and
market readiness would turn the new refusals into answers; the data supports it.
