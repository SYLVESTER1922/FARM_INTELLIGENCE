# Handoff: Farm Intelligence App

Session focus, across the project's full history: turning a 23-tab Netrisyl Farm
Intelligence Google Sheets workbook into a populated demo dataset, syncing it into a real
Postgres/Supabase database, and building a full chatbot answer engine on top of it —
landing a working, tested pipeline that answers the project's original motivating question
("how does feed cost split between pigs and chickens") in plain language, for real,
against the cloud database.

## Repo state

- Working dir: `/Users/vharsh/Farm-Intelligence-App` — git repo.
- Remote: `https://github.com/SYLVESTER1922/FARM_INTELLIGENCE.git` (`origin`). Both
  `main` and `prototype/supabase-domain-join-test` are pushed and tracking their remote
  counterparts. Working tree clean.
- `main` branch, commits in order (oldest to newest):
  - `d4cdbaa` — initial workbook + 12 months of synthetic data + generation scripts.
  - `21bd86e` — fix to `06_FEED_INVENTORY` grain (domain+feed_type+week).
  - `0bbdf46` — `spec-supabase-sync.md`.
  - `daaf0a6` — six local tickets under `.scratch/supabase-sync/issues/`.
  - `07e0c1b` → `fda9117` — sync tickets 01–06, all `done`. Sync spec fully implemented.
  - `2ec2fd3` / `13d5a83` — gitignore entries for `.env.supabase` and `supabase/`.
  - `763611b` — `spec-chatbot-answer-engine.md` + four local tickets under
    `.scratch/chatbot-answer-engine/issues/`.
  - `c5e0fd0` — switched the chatbot's LLM provider from Claude to OpenAI GPT-4o-mini,
    before any ticket code was written against the old provider.
  - `8a60063` — corrected tickets 01/03: phrasing is always an LLM call (caught before
    implementation started; "zero LLM calls" only ever applied to pure-refusal tests).
  - `7eddd6a` → `7cab355` — chatbot tickets 01–04, all `done`. Chatbot spec fully
    implemented.
- Throwaway branch `prototype/supabase-domain-join-test` (`447dbec`) — the SQLite
  prototype that first found the sync's feed_inventory grain issue. Deliberately not
  merged into `main` (prototypes are a primary source kept on their own branch here).

## What's built, in two layers

**Both specs below are complete.** Read them plus their ticket files for full design
rationale and acceptance criteria — this doc summarizes, it doesn't duplicate them.

### 1. Sync engine (`sync/`) — `spec-supabase-sync.md`, tickets 01–06

`sync/engine.py` + `sync/workbook_reader.py`: one seam,
`sync_workbook_to_supabase(filepath, farm_code, dsn) -> SyncReport`, syncing the entire
23-tab workbook into Postgres. Key facts:

- `06_FEED_INVENTORY` is synced at `domain + feed_type + week` grain — the fix that
  makes cross-domain feed-cost queries resolve cleanly (found via a throwaway SQLite
  prototype before the real sync was built).
- Real Postgres FK constraints where one target table exists; a `_validate_batch_ref`
  helper for polymorphic references (piggery vs. poultry) a single FK can't express.
  Every violation is caught and reported in `SyncReport.errors`, never raised. Every
  sync is idempotent.
- **Two real bugs found by `tests/test_sync_full_workbook.py`** (the full-workbook
  regression, run against real data, not fixtures — neither bug was caught by 47 passing
  fixture-based tests beforehand):
  1. `00_FARM_PROFILE` and `01_STAFF` are singleton/registry tabs where real data starts
     at row 3, not row 4 (the general convention) — `01_STAFF`'s row 3 holds a staff
     member referenced 286 times elsewhere. `read_tab_rows` gained a `min_row` param to
     handle this.
  2. `07_HEALTH_LOG`'s reference column is `batch_ref`, not `batch_code` as I'd assumed
     and written throughout — including in my own test fixtures, which is why it went
     uncaught until the sync ran against the real header row.
- Local dev environment: Postgres 16 via Homebrew (`brew services`), test database
  `farm_intelligence_test`, trust auth. Project venv at `.venv/`.
- Three planted findings, confirmed queryable end-to-end (local Postgres *and* real
  Supabase): poultry batch `BRO-P02` (mortality spike), pig batch `PIG-B02` (disease
  outbreak), crop sale product `Soya` (not `"Soyabean"` as earlier notes said) /
  `batch_ref='SB-PL2-25A'` — still `payment_status='Owing'`.

**Supabase cloud deployment**: real project `farm-intelligence` (ref
`bfetyunxnmqfvtiqirsr`, region `us-west-2`, org `gwemzvnyvfifialranlt`), created via the
`supabase` CLI. Verified: sync ran against it with zero errors, all row counts matching
the local-Postgres regression exactly, feed-cost-split query resolving cleanly there too.

- Auth note: the Supabase CLI's OAuth flow doesn't work at all in this sandboxed
  environment (no TTY) — only a personal access token works.
- Account is free-tier, 2-active-project cap — creating `farm-intelligence` required
  pausing an existing project (`JCC-Chatbot`, ref `gsdvxywkbhthrjhmffnm`) via the
  Management API, with the user's explicit go-ahead. **Still paused** — see Open Items.
- Credentials, none committed: `~/.supabase_access_token`, `~/.supabase_farm_db_password`,
  `.env.supabase` (project root, gitignored — `SUPABASE_PROJECT_REF` +
  `SUPABASE_DB_DSN`), `supabase/` (gitignored, CLI-local state only).

### 2. Chatbot answer engine (`chatbot/`) — `spec-chatbot-answer-engine.md`, tickets 01–04

`chatbot/` package, one seam mirroring the sync's:
`answer_question(question, farm_code, dsn) -> Answer`. Design was fully grilled via
`/grill-me` before the spec was written (tiered intent resolution, module scoping, strict
no-LLM-arithmetic split — all explicitly settled decisions, not open for re-litigation).

- `catalog.py` — the query catalog: `feed_cost_split` (cross-domain, requires an
  explicit `<Month> <Year>` parameter extracted from the question text),
  `poultry_mortality_spike`, `piggery_disease_outbreak`, `crop_debtor` (the three
  planted findings, no required params). Each entry declares which `domains` it
  touches, for scoping.
- `matcher.py` — tier-1 deterministic matcher: pure Python, curated phrase clusters,
  normalized token-overlap scoring, zero LLM/network calls. Modeled explicitly on a
  lesson from a prior Netrisyl pharmacy chatbot project: flat keyword lists were
  brittle, and full LLM-per-question was unnecessary machinery for a small known
  catalog.
- `fallback.py` — tier-2: one OpenAI (GPT-4o-mini) call only when tier 1 misses,
  validated against the exact same closed vocabulary tier 1 uses before being trusted.
  No retry loop.
- `engine.py` — orchestrates: tier-1 match → tier-2 fallback if needed → module scoping
  (one uniform check, applied regardless of which tier resolved intent, cross-domain-safe
  — a query touching multiple domains is scoped out if *any* touched domain's module is
  inactive) → SQL execution → OpenAI phrasing (only ever sees already-computed final
  values, never raw rows) → fire-and-forget `query_log` write.
- **LLM provider is OpenAI GPT-4o-mini, not Claude** — switched mid-build per explicit
  user decision, to match what other Netrisyl products already use (JCC-Chatbot, the
  pharmacy assistant). Reads `OPENAI_API_KEY` from the environment only, never a
  hardcoded path; `tests/conftest.py` sets it from `~/.openai_api_key` for local test
  runs only.
- **`query_log`** (Supabase table, created idempotently): logs every question, answered
  or not — `intent_source` (`deterministic`/`llm_fallback`/`unresolved`), `query_id`
  (populated whenever resolution succeeded, including scoped-out cases),
  `failure_reason` (genuine catalog gaps only: `no_match`/`ambiguous`/
  `missing_parameter`/`invalid_llm_intent`), `scoped_out_reason` (the module name
  itself, kept structurally separate from `failure_reason` so the two "no answer" kinds
  don't pollute each other's later analysis).

**Three real bugs/gaps found while implementing** (full detail in each ticket file's
notes):
1. First phrasing prompt only told the model to preserve numeric values exactly, not
   identifiers — it correctly computed `PIG-B02`'s data in SQL but the phrased answer
   never named the batch. Fixed by requiring every field, identifiers included, verbatim.
2. First fallback-validation pass conflated "the LLM honestly declines" with "the LLM
   names an unknown `query_id`" — both mapped to `invalid_llm_intent`, which silently
   overwrote every tier-1 `unresolved` reason whenever fallback was attempted and also
   failed, breaking "all tier-1-only tests keep passing unmodified." Fixed by threading
   tier 1's original reason through, and further distinguishing "unknown `query_id`"
   (real `invalid_llm_intent`) from "right `query_id`, question just lacks a required
   parameter" (still `missing_parameter` — same root cause tier 1 uses that label for).
3. `invalid_llm_intent` turned out untestable via the real API: GPT-4o-mini, given the
   extraction prompt, empirically never hallucinates an unknown `query_id` — it either
   resolves correctly or honestly declines, even under mild adversarial prompting
   (probed directly before concluding this). Agreed with the user to test this one
   branch via a deterministic unit test directly on `validate_llm_intent` instead of a
   live call — an explicitly-agreed, narrow second seam (validating our own
   closed-vocabulary check, not model behavior), not a silent black-box violation.

**Known limitation, not a bug**: the query catalog only covers its 4 designed queries
(`feed_cost_split`, `poultry_mortality_spike`, `piggery_disease_outbreak`,
`crop_debtor`). Real usage against the deployed app (see `query_log`) confirmed this
working as intended — e.g. "who owes us money?" resolves correctly via tier 1, but
"what happened to the poultry in January?" and "what can I ask you?" both correctly
refuse (`no_match`, with the LLM fallback genuinely tried and honestly declining both
times, not a matching failure) because no catalog entry answers a general status
summary or a capabilities/help question. This is the catalog's current scope working
exactly as designed, not something broken — but "what can I ask you" being unanswerable
is a real rough edge for a first-time user, worth a dedicated help/capabilities response
at some point. Deliberately left as a known gap for a future session — expanding the
catalog (or adding a help intent) is new scope, not a fix.

### 3. Chatbot UI (`ui/`) — `spec-chatbot-ui.md`, tickets 01–02

`ui/app.py`: a thin Gradio `ChatInterface` wrapper over `answer_question` —
`handle_message(question) -> str` is the one seam under test, reading `FARM_CODE`
(hardcoded, single farm) and `FARM_INTELLIGENCE_DB_DSN` from the environment, and
catching any exception into a fixed generic error message so a farm owner never sees a
raw traceback.

**Deployed and live**: `https://netrisyl-farm-intelligence.onrender.com` — Render's free
web service tier, public, no access control (this is synthetic demo data, the same
situation as JCC-Chatbot and the Pharmacy Assistant). Verified with real questions
against the live URL via `gradio_client`, not just a "build succeeded" assumption:
"Who owes us money?" answers correctly; out-of-catalog questions ("What happened to the
poultry in January?", "What's the weather like today?") refuse cleanly instead of
erroring.

**The platform ended up being Render, not Hugging Face, despite the spec's original
intent** — full account in `.scratch/chatbot-ui/issues/02-deploy-public-web-app.md` and
`spec-chatbot-ui.md`'s Further Notes. Short version: every free, compute-backed HF path
was tested directly and confirmed blocked (`Netrisyl` org `cpu-basic`/ZeroGPU both need a
paid org plan; the personal account's ZeroGPU tier has no GPU workload for this chatbot
to legitimately satisfy ZeroGPU's `@spaces.GPU` startup check; the personal account's
`cpu-basic` needs a PRO subscription). Render was the fallback: free web service, deploys
straight from the public GitHub repo. Needed a root `requirements.txt` (HF Spaces
provides this implicitly via the README's YAML frontmatter; Render doesn't), `ui/app.py`
binding to Render's `$PORT`/`0.0.0.0` instead of Gradio's defaults, and running as
`python -m ui.app` (not `python ui/app.py`) so the `chatbot` package resolves from the
repo root.

**A real deployment bug found and fixed**: the first live Render deploy answered every
question with the generic error message despite verified-correct `OPENAI_API_KEY` and
`FARM_INTELLIGENCE_DB_DSN`. Root cause: Supabase's **direct** DB host
(`db.<ref>.supabase.co`) resolves only to IPv6 (`AAAA`, no `A` record) on this project's
tier, and Render's free web services have no IPv6 egress — every DB connection attempt
failed silently into the generic error message, with nothing logged (the handler
deliberately swallows exceptions). Fixed by switching `FARM_INTELLIGENCE_DB_DSN` to
Supabase's connection pooler (Supavisor) instead: `aws-0-us-west-2.pooler.supabase.com:
6543`, user `postgres.<project_ref>`, transaction pool mode — this resolves to IPv4.
Verified with a direct `psycopg` connection before rolling the change out to both
`.env.supabase` and Render's env var.

**A security incident during this diagnosis, disclosed and corrected in-session**: while
inspecting the DSN to debug the above, a shell command's secret-redaction regex only
matched `://user:pass@` URL syntax and missed this DSN's actual libpq `key=value` format
— the real Supabase DB password was printed into the chat transcript in plaintext. This
was flagged to the user immediately, the password was rotated via the Supabase
Management API (new value never printed, generated locally and saved straight to
`~/.supabase_farm_db_password`), and the rotation was verified with a real `psycopg`
connection before `.env.supabase` and Render were updated to match. **Take this as a
standing lesson, not just a one-off fix**: never assume a generic secret-redaction
pattern covers every credential format — libpq DSNs, JSON blobs, and multi-field
credentials each need their own check, and a password appearing in a DSN string is easy
to miss if only URL-style credentials are guarded against.

**Testing conventions established across all three layers** (precedent for future work):
black-box only, through the one public seam; real local Postgres for every test, no
mocking; a *small* number of tests hit real external services end-to-end (Supabase, then
OpenAI) rather than exhaustive scenario coverage against a paid/slow API; a narrow,
explicitly-agreed-with-the-user exception when a live service genuinely can't be made to
exercise a specific branch (the UI layer's exception-handling test injects a failure at
the `handle_message` boundary for the same reason).

- Combined test suite: **71 tests, all passing**, stable across repeated full-suite runs.
  Run with `source .venv/bin/activate && python -m pytest tests/`.

## Open items — unresolved, don't assume either way

- **`~/.claude/settings.json` question still never answered.** Whether to set
  `permissions.blockReadsOutsideWorkingDirectories` from `true` to `false` (a global,
  not project-scoped, sandboxing setting). Still `true`. Ask before touching it.
- **Supabase `JCC-Chatbot` project is deliberately still paused, and must stay that
  way** — paused to free a slot under the account's 2-active-project free-tier limit
  when `farm-intelligence` was created. The user was asked whether to unpause it and
  explicitly confirmed it should stay paused: unpausing it would require pausing
  `farm-intelligence` back in exchange (only one can be active on the free tier), which
  would take this project's own database down. **Do not unpause JCC's Supabase project
  without the user explicitly re-confirming that tradeoff.**
- **Hugging Face `JCC_AFM_CHAT_BOT` Space (org `Netrisyl`) has been unpaused** (it was
  paused during this project's HF deployment attempts, to test whether freeing a slot
  would satisfy HF's org-level billing gate — it didn't; the actual blocker was a
  plan-tier requirement, not a slot count). The user asked for it to be unpaused, which
  is done — the Space is active again, not `PAUSED`. It will still show a
  `RUNTIME_ERROR` on startup (`httpx.ConnectError` reaching its Supabase backend), because
  its own Supabase project remains intentionally paused per the item above. This is an
  accepted, known tradeoff, not something to fix by unpausing JCC's database.
- ~~Leftover Hugging Face Space `Sylvester1922/Netrisyl_farm_intelligence`~~ — **resolved,
  nothing to clean up.** It was created during this project's now-abandoned HF deployment
  attempt, but had already been deleted mid-session (during hardware-downgrade
  diagnosis) before the user asked for cleanup; the subsequent recreate attempt failed
  outright (402) without creating a repo. Confirmed via `list_spaces(author=
  "Sylvester1922")`: no such Space exists.

## Key facts about the workbook (reference, don't re-derive)

- 23 tabs: `README`, `99_LISTS`, `00_FARM_PROFILE`, `01_STAFF`, `02_EXPENSES`,
  `03_REVENUE`, `04_LABOUR_LOG`, `05_WEATHER_LOG`, `06_FEED_INVENTORY`, `07_HEALTH_LOG`,
  `P1`–`P5` (piggery), `C1`–`C3` (poultry), `F1`–`F5` (crops).
- Row convention: row 1 = purpose/cadence note, row 2 = headers, row 3 = sample, row 4+ =
  data — **except** `00_FARM_PROFILE` and `01_STAFF`, where row 3 holds real data (see
  sync bug #1 above). Never touch rows 1–3 when writing to the workbook itself.
- **Correction to an earlier claim in this doc**: a previous version stated the 7
  formula-bearing columns (`02_EXPENSES.total_cost`, `03_REVENUE.total_amount`,
  `04_LABOUR_LOG.labour_cost`, `P2_PIG_DAILY_LOG.closing_count`,
  `P3_PIG_WEIGHTS.age_days`, `P5_BREEDING_FARROWING.expected_farrow_date`,
  `F5_HARVEST_LOG.quantity_kg`) were "confirmed clean via LibreOffice recalculation in an
  earlier session: 1,876 formulas, 0 errors." **That claim was never actually verified
  against this file and turned out to be false.** Direct inspection found 100% of cells
  in all 7 columns (1,869 rows total) had `None` cached values — `openpyxl` cannot
  evaluate formulas, it only reads whatever a real spreadsheet engine last cached, and
  this file's cache was never populated. This was invisible to every test in the project
  (row counts and zero-sync-errors were checked, never these specific values) until a
  live chatbot answer surfaced a `null` dollar amount. **Fixed**: these 7 columns'
  formula strings were replaced with statically computed values (each formula's logic
  replicated in Python from the literal formula text, e.g. `total_cost = quantity *
  unit_cost`) via `gen_scripts/fix_formula_cached_values.py` — they are plain numbers/
  dates now, not live formulas. Re-synced into both local Postgres and the real
  Supabase project; confirmed with a live query that the crop debtor's `total_amount`
  is `8681.12`, not `null`. One bug caught and fixed in the same pass: the fix script
  initially missed staff member `S01`'s labour rate because `01_STAFF`'s row-3
  exception (see the sync bug above) applied here too and wasn't accounted for at
  first — every `S01` `labour_cost` came out `0` until that was fixed.
- `gen_scripts/`: `generate_data.py` (full generator, seed=42), `write_workbook.py`,
  `verify.py`, `regenerate_feed_inventory.py`, `Netrisyl_Farm_Intelligence_Workbook.original_backup.xlsx`.

## Ultimate goal (stated by user) — now fully done, end-to-end

Build a chatbot on top of this farm data, able to answer cross-domain questions in plain
language. **The data layer, the answer-engine backend, and a public deployed UI are all
done, tested, and live**: a real Supabase Postgres database populated from the workbook;
a working `answer_question` seam that resolves questions (deterministic → LLM fallback),
respects module scoping, never lets an LLM touch raw-row arithmetic, and logs everything
for future catalog improvement; and a Gradio chat app anyone can reach at
`https://netrisyl-farm-intelligence.onrender.com`, verified end-to-end with real
questions against the live URL.

**Not built**: multi-turn conversation handling (explicitly out of scope — each question
resolved independently), any analysis/dashboarding on top of `query_log` (the table and
write path exist; nothing reads it yet), farm-switching UI or a module selector
(explicitly deferred — there's only one real farm today), and a dedicated help/
capabilities response for questions like "what can I ask you?" (a known, documented rough
edge — see the catalog-scope limitation above).

## Suggested skills for the next session

- **mattpocock-skills:grilling** / **to-spec** / **to-tickets** — if the next concrete
  step (catalog expansion, a help/capabilities intent, multi-farm support) has open
  design questions worth stress-testing first, the same way the sync, chatbot-engine,
  and chatbot-UI designs were all grilled before being spec'd here.
- **mattpocock-skills:tdd** — for any further catalog growth or new capability on
  `answer_question`; the seam and testing-split conventions above are now
  well-established precedent to follow.
- **code-review** or **simplify** — `sync/engine.py` (20 near-identical per-table sync
  functions) and `chatbot/catalog.py` (a growing list of near-identical `CatalogQuery`
  entries) are both candidates for a table-driven refactor now that the pattern is
  proven several times over. Deliberately not done mid-TDD-loop — refactoring is a
  separate step per the TDD skill.
- **mattpocock-skills:domain-modeling** — if formalizing the workbook's domain
  vocabulary (a `CONTEXT.md` or ADR) makes sense now that the schema has been through
  several real design fixes across both the sync and chatbot builds.
