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
| D1 | **Feed.** The daily log (`feed_kg` priced from `feed_inventory`) is the single "feed consumed cost" metric. `expenses.category = 'Feed'` is a separate metric, "feed purchases". Feeding page and Finance page both use the registry definition. Sync flags any month where daily-log consumption and `feed_inventory.used_kg` differ by more than **5%** (default tolerance, calibrate on real data). |
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
| **Headcount (zero-tolerance)** | active headcount; batch count (**new**); deaths and mortality rate (one definition) |
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
| **Warn** | feed consumption mismatch above 5%; a month with no rows; 10× jump or drop in an expense category between consecutive periods |

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

### Gate A: internal ready (start shadow mode)

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

9. The 5% reconciliation tolerance is a guess until real data exists.
10. Voice input adds transcription noise; the eval includes it.
11. Tenancy is only partly designed: it matters for the exploratory lane (item 5) and for any multi-farm deployment.
