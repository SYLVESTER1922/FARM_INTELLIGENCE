# Handoff: Farm Intelligence App

Session focus, across the project's full history: turning a 23-tab Netrisyl Farm
Intelligence Google Sheets workbook into a populated demo dataset, syncing it into a real
Postgres/Supabase database, building a full chatbot answer engine on top of it, deploying
it as a public web app, and then growing that into a full intelligence platform (a
sidebar-nav dashboard with 9 pages alongside chat) — landing a live, deployed system
that answers the project's original motivating question ("how does feed cost split
between pigs and chickens") in plain language, for real, against the cloud database, at
`https://netrisyl-farm-intelligence.onrender.com`.

**Most recent phase**: the chatbot's fixed 4-query catalog grew into a real, safe
expansion mechanism — a tier-0 (greetings/help) and a tier-3 (OpenAI native tool-calling
over real Python query functions, never LLM-generated SQL) sitting alongside the
original tier-1/tier-2 catalog, unchanged. This formally resolved a `/grill-me` session
that had been parked mid-flight for most of this project's history. See section 6.
Before that, the data source went fully live: a real Google Sheet now feeds Supabase on
a lazy poll-on-request cycle (no more manual `.xlsx` re-sync), and a global date-range
filter reaches every dashboard page and the chat's inject-and-narrate queries — both
modeled on the sibling Savanna QSR Intelligence product's actual architecture (read
directly from its repo, not assumed). See section 5.

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
  - `85c91b7` — `spec-chatbot-ui.md`, `1642ff9` — its two local tickets.
  - `06d1e1d` — ticket 01: local Gradio chat app. `73964ea` — fixed the missing-env-var
    bug (every question returned the generic error). `43f339f` — fixed the 7
    formula-bearing columns' null cached values (see the workbook section below).
    `2b92e5a` — documented the catalog's narrow scope as a known limitation, not a bug.
  - `eccf091` — corrected the UI spec from private/password-protected to public/no-auth.
    `1d4ba1b` → `e30044b` — ticket 02: deployed to Render (not HF — see below) at
    `https://netrisyl-farm-intelligence.onrender.com`.
  - `5b2c42c` / `f669b57` — doc corrections after HF Space cleanup and clarifying the
    JCC pause tradeoff (see Open Items).
  - `1e6dbf2` — added the dashboard: Herd & Flock, Financials, Findings & Alerts, Data
    Coverage tabs (see section 4 below).
  - `27af680` — this doc's previous update (dashboard section, Render history, mid-flight
    grilling session note).
  - `3a47315` — fixed dashboard chart layout bugs: `gr.Blocks(fill_width=True)` +
    explicit CSS `width:100%` (the app was shrink-wrapped to ~490px even at a 1400px
    viewport - root cause of the legend/title overlap and cramped axis labels reported
    against the live site), legends moved below plots, date-axis labels thinned/rotated,
    `automargin`/`cliponaxis` fixes for clipped text, and a real bug caught via
    screenshot review (not user-reported): `headcount_chart`'s x-axis category order was
    scrambled because Plotly orders categories by first-appearance-per-trace.
  - `5b06284` — added the Netrisyl logo to the header (inline base64,
    `assets/netrisyl-logo.png`) and swapped three chart types for readability
    (Mortality/Expenses-vs-Revenue: bars → lines; Records by Domain: bar → donut) — see
    section 4.
  - `49fdefc` — this doc's previous update (chart layout bug fixes, logo/chart-type
    changes).
  - `5713a62` — moved the header logo from left to right (dropped the `.hero-left`
    wrapper so `.titles` and the logo are the hero's two direct flex children, letting
    `justify-content:space-between` push the logo right) and enlarged it, 90px → 140px.
  - `943324a` — this doc's previous update (header logo move/enlarge).
  - `44382ee` — **major redesign**: replaced the top `gr.Tabs` bar with a fixed-width
    left sidebar nav (9 items) + slim top header + a new Dashboard landing page (4 stat
    cards + 2×2 chart grid). Added three real new pages (Feeding, Health, Breeding) and
    a Settings page, all reading previously-unused real tables. See section 4.
  - `47a5adf` — fixed a real CSS selector bug that made the new sidebar render as boxed
    white pills instead of one continuous panel, enlarged the header logo further
    (72px), and replaced two stat cards' misleading "0.0% vs 30 days ago" with honest
    "Since &lt;date&gt;" captions. See section 4.
  - `55bfc45` — this doc's previous update (sidebar redesign, new pages, CSS-bug and
    stat-card fixes).
  - `ef0f577` → `e26ff0e` — five rounds of header/layout polish driven by direct user
    visual feedback: logo repositioned right + resized several times, dashboard chart
    row order swapped (financial charts lead), sidebar nav spread evenly across full
    height, header background/accent treatment to read as one cohesive bar, and a
    full text-hierarchy rework (eyebrow label now the dominant line). Includes one
    real overcorrection (`154abfb`) caught and reverted the same session
    (`c0d3de2`) - see section 4 for the full blow-by-blow and the lesson from it.
  - `3e74c9b` — this doc's previous update (five rounds of header/layout polish).
  - `568fe93` — **Phase 1 of the live-data architecture**: added live Google Sheets
    ingestion (`sync_sheet_to_supabase`), a service-account-authenticated read of a real
    Google Sheet adapted through `sync/sheets_io.py` to satisfy `sync/engine.py`'s
    existing per-table sync functions unchanged. Verified end-to-end against local
    Postgres and real Supabase before being wired into the app. See section 5.
  - `0eb125a` — **Phase 2**: added global date-range filtering across every dashboard
    page and the chat's inject-and-narrate queries, consolidated the app's nine
    `demo.load()` calls into one `load_all()` orchestrator, and fixed a real bug this
    surfaced (`prepare_threshold=None`, see section 5) that was silently breaking
    Sheets syncs against Supabase's pooled connection.
  - `9c41fba` — this doc's previous update (live Google Sheets sync + date-range
    filtering).
  - `5daf933` — switched the app's font from Inter to Plus Jakarta Sans, with explicit
    weights (400/500/600/700/800) rather than Gradio's `GoogleFont` default (400, 600),
    which would have left the CSS's existing 700/800-weight text browser-synthesized
    ("fake bold") instead of using the real font.
  - `bc00340` — `spec-chatbot-catalog-expansion.md`, formally closing out the parked
    NL-to-SQL grilling session (see section 6) with a hard constraint the user set
    partway through this project's life: no free-form LLM-generated or executed SQL.
  - `c51edca` — tickets 01–06 implemented: tier-0 (greetings/help), a targeted
    `missing_parameter` clarifying response, and tier-3's core dispatch mechanism plus
    three starter tools (headcount, crop area planted, weather lookup). See section 6.
  - `872aaaa` — tickets 07–08: two more tier-3 tools (crop types listing, cumulative
    expenses to date), both sourced from real `query_log` evidence generated within
    minutes of the tickets 01–06 deploy going live. See section 6.
- Throwaway branch `prototype/supabase-domain-join-test` (`447dbec`) — the SQLite
  prototype that first found the sync's feed_inventory grain issue. Deliberately not
  merged into `main` (prototypes are a primary source kept on their own branch here).

## What's built, in six layers

**Layers 1–3 and 6 each have a complete spec** — read them plus their ticket files for
full design rationale and acceptance criteria; this doc summarizes, it doesn't duplicate
them. **Layer 4 (dashboard) was built directly, by explicit user instruction, with no
spec/ticket ceremony** — see section 4 for why and what that means for its documentation
here. **Layer 5 (live-data architecture)** was grilled first, then built directly
without a formal written spec (the grilling session's settled decisions served that
role) — see section 5.

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

### 4. Dashboard (`ui/queries.py`, `ui/charts.py`) — built directly, no spec/tickets

**Current layout (as of `44382ee`): a left sidebar nav, not top tabs.** Turns the
chat-only app into a full platform: a fixed-width (200px) dark navy/green sidebar with
9 items — **Dashboard** (landing page), **Chat**, **Herd & Flock**, **Feeding**,
**Health**, **Breeding**, **Finance**, **Reports**, **Settings** — each toggling a
`gr.Column` "page" in a single content area (not `gr.Tabs` — see the CSS-bug note
below for why that distinction mattered), under a slim top header (logo + branding).
Built by explicit user instruction to skip the spec/ticket process ("just build it
against the real Supabase data we already have synced, and I'll review as it comes
together") — so unlike the three layers above, there is no `spec-*.md` file or
`.scratch/*/issues/` tickets for this work, and no automated tests were written for
`ui/queries.py` or `ui/charts.py` (verified instead by running every query/chart
function, and the full deployed app via Playwright screenshots, against real data — see
below). If this layer grows further, consider whether it's earned a proper spec at that
point.

**Nav-item content mapping** (only 4 of the 9 items existed before the redesign; the
rest are genuinely new real-data pages, not placeholders):
- **Dashboard** (new): 4 stat cards (Total Livestock Placed, Active Headcount, Piglets
  Born, Mortality Rate — see the stat-card methodology and caption-vs-percentage note
  below) + a 2×2 chart grid reusing existing chart-building functions (Herd Growth =
  `headcount_chart`, FCR = `fcr_chart`, Cost vs Revenue = `expenses_vs_revenue_chart`)
  plus one new chart, `expense_breakdown_chart` (donut, expenses grouped by
  `expenses.category` — Feed/Labour/Vet/etc. — distinct from the existing Feed Cost by
  Domain bar on the Finance page, which was left untouched).
- **Herd & Flock**, **Finance**: unchanged content from the original tab-based layout,
  just now a sidebar destination instead of a tab.
- **Reports** (new, houses two prior tabs): **Findings & Alerts** and **Data Coverage**
  both live here, stacked with section headers — neither item was in the user's
  literal 9-item nav list, so this was a judgment call (both are "reporting" views, and
  splitting them across mismatched domain-named items would have fragmented
  self-contained content the user asked to keep intact).
- **Feeding** (new): `feed_cost_trend_chart` — monthly feed cost by domain, a line
  chart, from `feed_inventory` (previously only aggregated to a single full-period
  total on the Finance page).
- **Health** (new): `health_cost_chart` (grouped bar, vet/health cost by event type ×
  domain) + a real recent-events table, both from `health_log` (previously unused by
  any UI page).
- **Breeding** (new): a real summary (completed litters, total born alive, total
  weaned) + a farrowing-records table, from `breeding_farrowing`/`sow_register`
  (previously unused). Only 3 real records exist in this dataset (2 completed litters,
  1 pending) — small but real, not padded out.
- **Settings** (new): read-only farm configuration (farm code/name, region, currency,
  total hectares, financial year start, active modules) from `farm_profile`
  (previously unused by any UI page) — explicitly labeled "read-only... no editable
  settings system in this demo" rather than building a fake settings UI with nothing
  behind it.
- **Chat**: placed second in the sidebar (right after Dashboard), not a floating
  button — the user's own "your call" latitude on this specific point.

- **Reference app**: the user pointed at a sibling Netrisyl product,
  `github.com/SYLVESTER1922/stores-intelligence-assistant` (Lobels Biscuits
  Intelligence — Chat, Intelligence Reports, Material Lookup, Data Coverage tabs), as
  the pattern to follow. Cloned read-only into an isolated scratch folder (never the
  project directory, never modified), studied its tab structure, Plotly-in-`gr.Plot`
  charting, `gr.Blocks`/`gr.Tabs`/`gr.themes.Soft` layout, and its `_layout`/
  `empty_fig`/`_safe` chart-helper pattern — then adapted it with farm branding and farm
  data, not copied verbatim. `ui/charts.py`'s color palette (green for piggery, gold for
  poultry) and helper functions mirror Lobels' structure directly; the CSS hero-header/
  sidebar-card pattern in `ui/app.py` does too, restyled.
- **`ui/queries.py`**: read-only SQL against the real synced schema — monthly mortality
  and headcount by domain, FCR by batch (methodology note below), expenses-vs-revenue by
  month, feed cost by domain (the project's original founding question, now a chart, full
  period rather than one month), a debtor/outstanding-payments query, and the three
  planted findings pulled via the *exact same* `CatalogQuery` SQL constants
  (`chatbot/catalog.py`) the chatbot itself answers from — not hand-typed numbers.
- **`ui/charts.py`**: Plotly figure builders consuming that data. No arithmetic beyond
  what SQL already computed, same principle as the chatbot's SQL-then-phrase split.
- **FCR methodology** (worth knowing if these numbers are ever questioned): feed
  conversion ratio = total feed fed to a batch ÷ its total liveweight gain.
  Liveweight gain is approximated as `(latest sampled avg weight − starting avg weight) ×
  latest closing headcount` for pigs, and `(latest sampled avg weight in kg) × latest
  closing headcount` for poultry (day-old chick weight, ~40g against a ~2kg market
  weight, is treated as negligible — standard practice for a rough broiler FCR, and there
  is no chick starting-weight column in `poultry_batches` to subtract anyway). Verified
  against real data: results came out in realistic ranges (pigs ~2.3–2.65, broilers
  ~1.6–2.0), which is a sanity check, not a formal accuracy claim.
- **Data Coverage's "freshness" indicator is deliberately not a fabricated sync
  timestamp**: the sync is an idempotent truncate+reload with no write-audit column, so
  there is no real "last synced at" fact to show. Mirrors exactly how the Lobels
  reference app solves the identical problem — using the latest real record date across
  the domain tables as the freshness signal instead of inventing a sync-log timestamp
  that doesn't exist.
- **Verification**: every query/chart function run directly against real Supabase data;
  the full app run locally (`python -m ui.app`) and exercised through the real Gradio
  HTTP API via `gradio_client` (all 5 endpoints: `/_chat_fn` plus the four
  `demo.load`-wired dashboard endpoints); then redeployed in place to the same Render URL
  and re-verified there the same way, not assumed from "the deploy succeeded."
- **New public API surface**: `/load_herd_flock`, `/load_financials`, `/load_findings`,
  and `/load_data_coverage` are exposed as public Gradio API endpoints on the deployed
  app, callable directly by URL, same as `/_chat_fn` already was. Consistent with the
  app's existing public/no-auth posture (synthetic demo data), but worth knowing this is
  now four endpoints of surface area, not one.
- **Real layout bug, found after initial ship, now fixed**: the user reported legend/
  title overlap, cramped x-axis labels, and a clipped FCR chart on the live deployment.
  Root cause turned out to be architectural, not per-chart: `gr.Blocks()` defaults to
  `fill_width=False` in Gradio 6, so the *entire app* was shrink-wrapped to ~490px even
  at a 1400px viewport - explaining all three symptoms at once. Fixed with
  `fill_width=True` **plus** an explicit CSS `width: 100% !important` on
  `.gradio-container` (the `fill_width` flag alone added the right class but the
  computed width didn't actually change - needed the direct override too; this is worth
  knowing if a future Gradio upgrade reintroduces a similar shrink-wrap issue). On top of
  that, per-chart Plotly fixes: legends moved below the plot (were overlapping the title
  at `y=1.15`), date-axis labels thinned to ~6 evenly-spaced rotated ticks,
  `automargin=True` on every axis, `cliponaxis=False` + range padding for outside-bar
  text. **A second real bug was caught during screenshot review, not reported by the
  user**: `headcount_chart`'s x-axis rendered "Oct 2025" after "Aug 2026" because Plotly
  orders categories by first-appearance-per-trace, and the piggery/poultry lines cover
  different date ranges - fixed with explicit `categoryorder="array"` pinned to the full
  chronological label list. **Verification method going forward**: Playwright (with a
  headless Chromium binary) was installed into the project venv specifically to take
  real screenshots of the deployed app - not just "the code runs" or "the API returns
  data." This is a dev-only tool (screenshot verification), not a production dependency,
  and isn't in `requirements.txt`.
- **Visual polish pass**: the Netrisyl Insights logo now appears in the header, embedded
  inline as base64 (`assets/netrisyl-logo.png`, resized from a 1.2MB/1672×941 source the
  user dropped at the repo root - `NI_logo.png`, intentionally left untracked/uncommitted
  since it's not what's actually used - down to a 130KB/533×300 web copy) rather than
  linked externally, so it always renders regardless of static-file hosting - same
  pattern as the Savanna QSR app. Also, three chart types were swapped for readability,
  a data-driven choice per explicit instruction, not aesthetic: Mortality by Month and
  Expenses vs Revenue by Month went from grouped bars to lines (both are time-trend
  questions a line reads more clearly for); Records by Domain went from a bar chart to a
  donut (a share-of-total question). FCR and Feed Cost by Domain were explicitly left as
  bars - those are precise value rankings/comparisons, where bars are still correct.
  **Follow-up per user request**: the logo was later moved from the left side of the
  header to the right, and enlarged (90px → 140px) - a one-line CSS/HTML change
  (`#farm-hero`'s `justify-content: space-between` now applies directly between
  `.titles` and the logo `<img>`, no wrapper div needed).
- **Sidebar redesign** (`44382ee`) replaced the top `gr.Tabs` bar with the 9-item
  sidebar described above. Page-switching uses `gr.Column(visible=...)` toggled by
  `gr.Button.click()` handlers (18 outputs per click: 9 page-visibility updates + 9
  nav-button `elem_classes` updates for the active-state highlight) — **not**
  `gr.Tabs`, because full control over the sidebar's visual structure (fixed width,
  vertical layout, custom active-state styling) was easier to get right with plain
  buttons + columns than by re-skinning Gradio's own tab-nav DOM via CSS.
  `demo.load()` eager-population still fires for every page regardless of which one is
  visible on load, same as before - switching from `gr.Tab` to `gr.Column(visible=...)`
  didn't change that.
- **Stat-card "as of a past date" methodology**: `pig_batches.status`/
  `poultry_batches.status` are current-only (no historical log), so "was this batch
  active 30 days ago" can't honestly be read from today's status column - it's
  derived instead from each batch's own logged date range (active as of date D if it
  has `pig_daily_log`/`poultry_daily_log` rows both on/before and on/after D). This
  avoids a real staleness bug a naive "check current status" approach would have
  introduced.
- **A real CSS bug found and fixed** (`47a5adf`): the sidebar initially rendered as
  "individually boxed white pills with dark gaps between them" instead of one
  continuous panel. Root cause: the CSS selector was `.nav-btn button { ... }` (a
  descendant selector), but `nav-btn` is a class Gradio applies directly to the
  `<button>` element itself (via `elem_classes`), not to a wrapper around one - so the
  selector never matched anything, and every nav item silently fell back to Gradio's
  default white/boxed button styling plus the containing column's default 16px flex
  gap. Fixed by changing the selector to `button.nav-btn` and setting the sidebar
  column's `gap: 0 !important`. **Lesson for any future `elem_classes` CSS**: always
  verify with a real DOM inspection (`getComputedStyle` via Playwright) that a
  selector actually matches before assuming a "not working" style is a specificity
  problem rather than a selector-shape problem - this one silently did nothing for an
  entire redesign pass before being caught by screenshot review.
- **Stat-card percentage fix** (`47a5adf`): "Total Livestock Placed" and "Piglets Born"
  are lifetime cumulative totals, so a "vs 30 days ago" percentage on them reads as
  ~0% on almost every real day even though the total itself (2,102 / 24) is large and
  meaningful - a real misleading pattern the user caught. Both now show an honest
  "Since &lt;earliest real date&gt;" caption instead (e.g. "Since 2025-10-10"), computed
  from real `MIN(start_date)`/`MIN(farrow_date)` queries, not hand-typed. Active
  Headcount and Mortality Rate kept their genuine percentage comparisons since those
  are real flow/snapshot metrics that actually vary period to period.
- **Header went through five more iterations after the sidebar redesign shipped**
  (`ef0f577` → `3b86982` → `154abfb` → `c0d3de2` → `e26ff0e`), all user-driven visual
  feedback rounds, each verified locally at multiple viewport widths via Playwright
  before deploying:
  1. `ef0f577` — logo moved back to the right (112px), dashboard chart rows reordered
     (financial charts now lead: Expenses vs Revenue + Expense Breakdown on top,
     Headcount Trend + FCR below), sidebar nav switched to `justify-content:
     space-evenly` + `align-self: stretch` so the 9 items spread across the full
     available height instead of clustering at the top.
  2. `3b86982` — fixed "two corners with a dead-space gap" on wide viewports: added a
     horizontal gradient band (white → light green tint → white) across the header
     plus a thin bottom accent bar, so the empty middle reads as one designed surface
     instead of flat nothing between two isolated blocks.
  3. `154abfb` — **an overcorrection, reverted next commit**: tried to make the logo
     "twice as big" by jumping straight to 260px and growing the header's own padding
     to 40px/48px to match, which grew the *whole bar*, not just the logo - reported
     back almost immediately ("you increased the width of the header").
  4. `c0d3de2` — corrected: logo settled at a moderate 190px (up from the original
     130px), header padding pulled back down near its original size (30px/36px).
     Confirmed via a PIL bounding-box check that the source logo file has zero
     trimmable whitespace (content fills the full 1672×941 canvas edge to edge), so
     "bigger lengthwise" necessarily means height and width grow together at the
     source's fixed ~1.78:1 aspect ratio - there's no way to widen it independently
     without either distorting or re-cropping the source art.
  5. `e26ff0e` — reworked the text block's hierarchy: "FARM INTELLIGENCE PLATFORM" is
     now the *largest, boldest, gold-accented* line (was the smallest), "Chiedza Mixed
     Farm" is the medium navy line, the domain tags are the smallest. The block also
     picked up `flex: 1 1 auto; max-width: 760px` - the bigger, wider-tracked line-1
     type is what actually extends it toward the logo, not an artificial stretch of
     short left-aligned text.
  **Lesson for any future logo/branding resize request**: check the source image for
  trimmable whitespace *before* promising an aspect-ratio-independent resize, and when
  a user says "make X bigger," prefer a moderate, easily-adjustable first pass over a
  large jump - the 154abfb→c0d3de2 round-trip cost two extra deploy cycles that a
  smaller first move would have avoided.

### 5. Live data architecture: Google Sheets sync + date-range filtering

Built by explicit user request to make the dashboard's data source live, reusing the
same "Supabase backing store + inject-and-narrate" architecture as sibling product
Savanna QSR Intelligence (`github.com/SYLVESTER1922/savvana-qsr-intelligence`) — checked
directly against that repo's actual code before designing anything, not assumed. Two
premises from the initial request turned out false and were corrected via a `/grill-me`
session before implementation: Savanna has **no** Google Sheets sync code at all (its
Supabase population happens entirely outside that repo), and its "live" read layer is
just a 5-minute in-process TTL cache over Supabase's REST API plus a manual refresh
button — simpler than what this project already had. What *did* carry over faithfully:
Savanna's `date_from`/`date_to` + "Apply Filter" pattern, and its query-first-narrate-
second split (there via OpenAI tool-calling; here via the existing tier-1/tier-2
`chatbot/` engine, deliberately kept rather than rewritten — two different mechanisms
upholding the same principle).

**Phase 1 — live Google Sheets ingestion** (`568fe93`):

- `sync/sheets_io.py`: a minimal adapter making a Google Sheet satisfy the exact minimal
  interface `sync/engine.py`'s 21 `_sync_*` functions already expect from an openpyxl
  `Workbook` (`.sheetnames`, `wb[name][row]`, `.iter_rows(...)`) — so all ~1,384 lines of
  already-tested per-table sync logic run completely unchanged against either source.
  Reads via `sheets.values().batchGet(..., valueRenderOption="UNFORMATTED_VALUE")` (native
  types, not formatted strings — dates come back as serial day-counts, converted manually
  from the `1899-12-30` Sheets epoch, since formatted-string dates are locale-ambiguous).
  Blank cells convert to `None`, not `""` (openpyxl's real behavior) — Postgres rejects
  `""` for `NUMERIC` columns, and this was caught by a real sync failure before shipping.
- `sync/engine.py` gained `sync_sheet_to_supabase(sheet_id, farm_code, dsn, creds_json)`,
  extracted the shared logic into `_sync_from_workbook(wb, farm_code, dsn)` so both the
  `.xlsx` and Sheets paths call the identical per-table functions.
- **New live Google Sheet**: "Netrisyl Farm Intelligence-Live", ID
  `1bmjuyGFpqc9qaXf7s-jqVtBxIamE_XcBGb9qGUAjgXE`, owned by the user's own Google account,
  shared as Editor with service account
  `farm-intelligence-sync@netrisyl-farm-intelligence.iam.gserviceaccount.com`. Same 21
  domain tabs as the original workbook plus `99_LISTS`, seeded from real current Supabase
  data, with a simplified convention (row 1 = headers matching Postgres column names
  exactly, row 2+ = data — no purpose-note/sample rows like the original workbook).
- **Credentials**: the service account key lives at
  `~/.config/farm-intelligence/google-service-account.json` locally (never printed,
  verified only by structural checks — `client_email`, `type`, presence of
  `private_key`). On Render, passed as the key's raw JSON *content* via the
  `GOOGLE_SERVICE_ACCOUNT_JSON` env var (not a file path — Render's filesystem isn't
  persistent), read with `service_account.Credentials.from_service_account_info(...)`.
  `FARM_INTELLIGENCE_SHEET_ID` is also an env var (not secret, kept consistent with the
  other config). Both are set on the Render service already.

**Phase 2 — global date-range filtering** (`0eb125a`):

- A shared `date_filter_sql(column, date_from, date_to, params, param_prefix="")` helper
  lives in `chatbot/catalog.py`, not `ui/queries.py` — `chatbot` must never depend on
  `ui`, and `ui/queries.py` already imports SQL constants from `chatbot/catalog.py`, so
  this follows the same existing dependency direction. Returns a SQL fragment (or `""`)
  filled into a `{date_filter}` formatting placeholder on every filterable query string.
- Every `ui/queries.py` `fetch_*` function and `chatbot/engine.py`'s `answer_question`
  gained optional `date_from=None, date_to=None` parameters — default `None` preserves
  all pre-existing behavior and all 71 tests unchanged. `answer_question`'s catalog
  execution step now looks up which column each catalog entry's date filter applies to
  (`CATALOG_DATE_COLUMNS`, keyed by `query_id`) and folds the filter into the SQL before
  running it — same inject-and-narrate order as always, the LLM never sees raw rows.
- **`ui/app.py`**: a filter bar (From/To `Textbox` + "Apply Filter" + "🔄 Refresh Data" +
  a live sync-status caption) sits above the sidebar, visible on every page. The nine
  previously-separate `demo.load()` calls were consolidated into one `load_all()`
  orchestrator (wired to initial page load, Apply Filter, and — via
  `refresh_and_load_all()`, which force-syncs first — the Refresh button), so one click
  updates every page at once. Chat's `additional_inputs=[date_from_box, date_to_box]`
  means chat questions are always scoped to whatever range is currently selected — a
  date named in the question text (e.g. "in March") narrows *within* that range, per the
  Savanna-matched design, it doesn't override it.
- **Lazy sync, not a background poller**: `_maybe_sync_sheets()` checks a module-level
  `last_synced_at` timestamp on every dashboard connection and re-syncs at most once per
  `SHEETS_SYNC_TTL_SECONDS` (300s); Refresh Data bypasses the TTL via
  `force_sync_sheets()`. Deliberately not a real background scheduler — Render's free
  tier can cold-start between requests, which would silently kill an in-process poller
  with no visibility that it died.
- **Dashboard stat-card semantics under a filter** (settled via grilling): cumulative
  lifetime totals (Total Livestock Placed, Piglets Born) use the filter's end date (or
  the latest real date) as an "as of" cutoff and gain a `"(through <date>)"` caption
  suffix — never a fabricated percentage. Flow/snapshot metrics (Active Headcount,
  Mortality Rate) use the selected range itself as the comparison window, against a
  same-length immediately-prior period, when both bounds are set; otherwise they fall
  back to the original fixed 30-day window.
- **Findings & Alerts respects the filter honestly**: a finding whose underlying event
  falls outside the selected range comes back `None`, and `ui/app.py`'s fallback text
  distinguishes "never happened" (no filter) from "didn't happen in this range" (filter
  active) rather than using one generic message for both.
- **A real bug found and fixed, not present before this phase's live-sync work**:
  Supabase's DSN is the **transaction pooler** (pgbouncer, port 6543), which is
  incompatible with psycopg3's default server-side prepared statements — a connection
  that runs enough repeated queries can get routed to a different backend mid-session,
  and a statement prepared on the old backend surfaces as a real
  `prepared statement "_pg3_N" does not exist` error. First caught live, mid-verification,
  not in a test. Fixed with `prepare_threshold=None` on all three `psycopg.connect` call
  sites that use this DSN (`sync/engine.py`, `ui/app.py`, `chatbot/engine.py`) — the
  documented fix for psycopg3 against pgbouncer transaction-mode pooling.
- `requirements.txt` gained `google-auth`, `google-api-python-client` (Phase 1) and
  `openpyxl` (Phase 2 — `ui/app.py` now imports `sync/engine.py`, which imports
  `openpyxl` at module level even though only the Sheets path is actually called from
  the app; this was missing from `requirements.txt` until caught during Phase 2
  deployment verification).
- **Verification, matching this project's "real proof, not assumption" discipline
  throughout**: local test-DB sync, then real-Supabase sync, both with zero errors and
  exact value-level correctness (all three planted findings, boolean conversions, real
  dates). The full assembled app was run locally and exercised through its real Gradio
  HTTP API via `gradio_client` — unfiltered dashboard stats, a date range that correctly
  excluded the piggery disease outbreak finding (all its real treatments fall in
  April–May 2026) and a range that correctly included it, and chat correctly answering
  "no" vs. "yes" to "is there a disease outbreak in the piggery" depending on which range
  was active. The same checks were then repeated **against the live Render URL** after
  redeploying, not assumed from "the deploy succeeded" — including a real live Sheets
  sync completing successfully in production.
- **Deploy note worth knowing for next time**: this service's `autoDeploy` setting is
  `yes` and tracks `main`, but the push to `main` did **not** trigger a deploy on its
  own (checked via the Render API: no deploy existed for the new commit after 8+
  minutes). Had to trigger it manually via `POST /v1/services/{id}/deploys`. Cause not
  diagnosed — possibly a webhook delivery issue on GitHub's or Render's side. Worth
  checking the Render dashboard's deploy history after any future push, rather than
  assuming auto-deploy fired.
- **New public API surface**: `/load_all` and `/refresh_and_load_all` are now public
  Gradio endpoints on the deployed app (in addition to the per-page `/load_*` endpoints
  already there from section 4's work), consistent with the app's existing public/no-auth
  posture.

### 6. Chatbot catalog expansion: tier-0 + tier-3 — `spec-chatbot-catalog-expansion.md`, tickets 01–08

**Context this closes out**: since early in this project, a `/grill-me` session on
expanding the chatbot beyond its fixed 4-query catalog had been parked mid-flight -
round 1 settled (hybrid tiering, full schema scope, honest refusal, one-shot), round 2's
six questions asked but never answered. The user later set a hard constraint that
reframed the whole design space: **no free-form LLM-generated or executed SQL, in any
form** - ruled out entirely as a safety/correctness risk, not deferred. This required a
fresh three-round grilling session (not a resumption of the old one, since several of
round 2's original six questions - SQL safety guardrails, retry policy on malformed
generated SQL - were specifically about free-form SQL and had to be reframed or retired
once that was off the table) that also required re-reading, not assuming, how two
sibling Netrisyl products actually work: Savanna QSR Intelligence and Lobels Stores
Intelligence. **A wrong claim made mid-session and corrected**: Savanna's chat was
initially believed to be one-shot like this project's; re-cloning and reading its actual
`chat()` function directly showed it threads conversation `history` into every call,
same as Lobels - both sibling products are genuinely multi-turn, this one deliberately
isn't (see below).

**What both siblings actually do, verified by reading their real code, not assumed**:
neither writes SQL. Both register ~10-12 medium-granularity Python functions as OpenAI
native tools (`tool_choice="auto"`); the model picks one, the real function runs (pandas
on a pre-filtered dataframe for Savanna, Supabase REST + Python aggregation for Lobels),
a second call narrates only the JSON result. This is the pattern tier-3 below adopts.

**Settled design** (full detail and rationale in the spec):
- **Tier-0** (new, cheapest, checked first): a curated, small set of greeting/
  capability phrases (`chatbot/greetings.py`), matched by exact normalized-token-set
  equality against the whole question - deliberately *not* tier-1's fuzzy recall
  scoring, which was found during implementation to be unsafe for this use (a short
  phrase like "hi" would score a perfect match against any question merely containing
  the word "hi" anywhere in it, including a real data question). Zero LLM calls.
- **`missing_parameter` now gets a targeted clarifying response** (e.g. "which month?")
  instead of the same generic wall as a true no-match, and never escalates further -
  tier-1/tier-2 already knew *which* query type this was, just not one required detail.
- **Tier-3** (`chatbot/tools.py`): OpenAI native tool-calling over medium-granularity
  Python functions, reached only on a true `no_match`/`ambiguous` from tiers 1-2 (never
  `missing_parameter` or `scoped_out`). Every tool executes parameterized queries only;
  closed-vocabulary arguments (a domain name) are validated against a fixed list before
  querying and fail as a single, final failure with no retry (same precedent as
  tier-2's own validation); free-text arguments are trusted to the database. Module
  scoping is statically declared per tool (a tool that can touch multiple domains
  declares all of them, mirroring the existing catalog's rule) and reuses the exact
  same uniform check. The global date-range filter applies via whichever mechanism
  actually fits a given tool's query shape - a point-in-time cutoff for a snapshot tool
  (headcount, weather), the same `{date_filter}`/`date_filter_sql` range pattern
  tiers 1-2 already use for a genuine range aggregate (crop area, crop types, expenses
  to date) - both are the "same mechanism" in spirit (respecting whichever range is
  currently selected), just applied differently depending on query shape, not two
  inconsistent systems.
- **`chatbot/data_dictionary.py`**: a curated, hand-maintained (never live schema
  introspection) description of what the farm's data does and doesn't track backs one
  more bounded LLM call, made only on a genuine full miss at every tier, so the chatbot
  can honestly distinguish "not tracked at all" (e.g. accounts payable - money the farm
  owes suppliers) from a generic wall, rather than treating every unanswerable question
  identically. Never surfaces raw table/column names.
- **`query_log`** gained `tool_name`/`tool_arguments` columns (via
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, idempotent against the already-existing
  production table, same pattern the sync engine already uses) - every tier-3 hit
  records which tool and which validated arguments, so real usage can drive which tool
  to build next (see below - this happened almost immediately).
- **Testing**: the primary seam (`answer_question`) is unchanged; one new, narrow,
  explicitly-agreed secondary seam (`resolve_tool_call`) is tested directly with real
  OpenAI calls, asserting *which* tool gets selected for canonical phrasings - the direct
  analogue of tier-2's `validate_llm_intent` already being tested this way, and the only
  way to catch a future tool's registration silently changing which tool gets picked for
  an existing one's intended phrasing.
- **Multi-turn conversation memory was explicitly re-evaluated and still deferred** -
  now with the correct fact that both sibling products support it, not the earlier wrong
  belief that only one did. Kept separate scope deliberately, not bundled in.

**Tickets 01-06** (`.scratch/chatbot-catalog-expansion/issues/`), all done: 01 tier-0,
02 the `missing_parameter` fix, 03 tier-3's core dispatch + first tool (real pig/poultry
headcount, reusing the dashboard's existing "active as of a date" methodology -
**relocated** from `ui/queries.py` into `chatbot/catalog.py`'s new
`active_headcount_asof`, mirroring `date_filter_sql`'s existing placement there, so
tier-3 and the dashboard share one source of truth instead of two copies), 04 crop area
planted, 05 weather-log lookup, 06 the data-dictionary honest refusals. **Two real bugs
found and fixed along the way**: `_find_inactive_domain` produced invalid SQL
(`SELECT  FROM farm_profile...`) for a tool declaring zero domains (weather is
farm-wide, not owned by any single module) - every existing catalog entry always
declared at least one domain, so this was never hit before tier-3. **One real
limitation found and honestly documented, not fixed** (ticket 06): the real logged
phrasing "Do we owe anyone money?" is genuinely borderline enough (shares vocabulary
with `crop_debtor`'s own catalog phrase "who owes US money") that tier-2's classifier
occasionally, non-deterministically misroutes it there instead of reaching the new
gap-explanation path - documented in the test file as a pre-existing characteristic of
tier-2, out of scope to fix here.

**Tickets 07-08**, added within minutes of the 01-06 deploy going live, from real
`query_log` evidence a live user actually generated against production: "What crops do
we have?" (a listing, distinct from ticket 04's area total) and "What's the expense
amount to date?" (a cumulative total, matching the dashboard's existing cumulative
stat-card treatment - "as of" a cutoff, not a `date_from`-bounded range) both got the
generic unresolved wall despite being real, answerable questions. Both new tools are
pure reuse of ticket 03's infrastructure - no changes to the dispatch mechanism itself.
Also from that same live session: **"Are you sure?" is not a bug** - it's the expected,
designed cost of chat being deliberately one-shot; there's no context for a follow-up
question to resolve against. Documented, not silently "fixed" with ad-hoc memory.

**Every tier-3 tool and the data-dictionary refusal path were verified against real
production Supabase data, independently cross-checked against a direct query each
time**, not just local test-DB coverage - e.g. real pig headcount (12, as of
2026-09-15), real crop area (23.0 ha), real crop types (Groundnuts, Maize, Soyabean,
Tomatoes), real cumulative expenses (30380.06 as of 2026-09-14), real weather
(2026-09-15, 6.7-21°C, 0mm rain, 47% humidity) - each confirmed to match a direct SQL
query against the same live database, then confirmed again live through the deployed
Render app via `gradio_client`, not assumed from "the deploy succeeded."

**A separate, real evaluation was run and its finding acted on**: the user asked
whether GPT-4o-mini could reliably handle farm questions in Shona, given voice input
(a small, real, already-proven pattern in Lobels - `gr.Audio` + Whisper transcription,
verified by reading Lobels' actual code) was also on the table. A real spike (translate
representative questions to Shona, back-translate, and ask GPT-4o-mini to answer them
cold) found a genuine, reproducible vocabulary-level defect: GPT-4o-mini twice
mistranslated "pigs" as "mbudzi" (goats) and "mombe" (cattle) in Shona, and then
answered *entirely about the wrong animal* when asked those same (its own) mistranslated
questions - confirmed via back-translation, not assumed. General Shona grammar read as
genuinely decent elsewhere (crops/weather/debtor questions round-tripped cleanly). The
user decided to drop the Shona feature rather than build on this defect. **Worth
knowing if Shona is ever revisited**: this is a real, narrow, livestock-vocabulary gap,
not a blanket "Shona doesn't work" finding, and would need a native speaker's review,
not another automated spike, before any real investment.

**A broader expanded-scope analysis was done (not built)** for seven possible next
directions, with the user's sequencing decision recorded here in case a future session
picks any of these up out of order:
1. **Exhaustive tool coverage** - open-ended, no fixed target count; sequenced as
   ongoing, evidence-driven batches (cross-checked against what the dashboard's charts
   already show, so chat fills genuine gaps rather than duplicating on-screen data),
   with a fixed-question tool-selection accuracy eval re-run as each batch lands, to
   catch degradation early rather than assume tool-calling scales past the ~10-12 tools
   proven in Savanna/Lobels.
2. **Multi-turn conversation memory** - deferred until tool coverage stabilizes; token
   cost compounds with #1 (both resend more content per call), so the user doesn't want
   them landing back-to-back without re-checking real cost/latency.
3. **Query result caching** - deferred alongside #2, since its real payoff (caching
   follow-up questions) is low while chat stays one-shot. Technically straightforward
   when revisited: `_sync_state["last_synced_at"]` (from section 5's live-sync work)
   is exactly the invalidation key needed - no cached answer can survive past the last
   real sync.
4. **Suggested follow-up questions** - sequenced alongside future tool batches, using a
   curated per-tool mapping (each tool declares its own plausible follow-ups) rather
   than an LLM call per answer, to add zero per-turn latency/cost.
5. **Domain summary lookup tab** (like Lobels' "Material Lookup") - confirmed
   independent of all of this chatbot work; ticketed separately at
   `.scratch/domain-summary-lookup/issues/01-domain-summary-lookup-tab.md`, buildable
   almost entirely from `ui/queries.py`'s existing functions (one small new crops-only
   query needed - no equivalent exists there yet). **Not yet built.**
6. **Voice input** - small, proven, independent; can slot in anytime. Verified for real
   against Lobels' actual code: `gr.Audio(sources=["microphone"])` +
   `mic.stop_recording(transcribe, ...)` + a ~10-line Whisper (`whisper-1`) call, feeding
   the existing message textbox - zero changes needed to `chatbot/engine.py`.
7. **Shona language support** - dropped by the user after the real spike above found a
   concrete vocabulary defect (see above). Not pursued further.

## Open items — unresolved, don't assume either way

- ~~A `/grill-me` session on expanding the chatbot's catalog into NL-to-SQL was
  mid-flight~~ — **resolved.** The user set a hard constraint (no free-form
  LLM-generated/executed SQL, ruled out entirely) that made the original round-2
  questions moot as framed; a fresh three-round grilling session settled tier-0 +
  tier-3 tool-calling instead, fully implemented across tickets 01-08. See section 6.
- **A real, unfixed tier-2 classification ambiguity, found while building ticket 06,
  documented but out of scope to fix**: the phrasing "Do we owe anyone money?" shares
  enough vocabulary with `crop_debtor`'s own catalog phrase ("who owes US money for
  crops") that tier-2's LLM classifier occasionally, non-deterministically misroutes it
  there instead of correctly falling through to a no-match. This is a pre-existing
  characteristic of tier-2's classification (not introduced by tier-3/section 6's work),
  worth hardening at some point - probably means making the catalog's phrase/description
  summary given to tier-2 more explicit about directionality (money owed *to* the farm
  vs. *by* the farm), not something to guess a fix for without testing against the real
  API again.
- **Seven possible next directions for this chatbot work were analyzed but not built**
  (exhaustive tool coverage, multi-turn, query caching, suggested follow-ups, a domain
  summary tab, voice input, Shona support) - full detail and the user's sequencing
  decision are in section 6's closing paragraphs. Voice input and the domain-summary tab
  are both confirmed small/independent and could be picked up anytime; Shona was
  dropped after a real spike found a concrete defect; the rest are deliberately
  sequenced after further evidence-driven tool-coverage batches land.
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

## Ultimate goal (stated by user) — chatbot done end-to-end; now a growing platform

Original goal: build a chatbot on top of this farm data, able to answer cross-domain
questions in plain language. **That's fully done, tested, and live**: a real Supabase
Postgres database populated from the workbook; a working `answer_question` seam that
resolves questions (deterministic → LLM fallback), respects module scoping, never lets
an LLM touch raw-row arithmetic, and logs everything for future catalog improvement.

The scope then grew, by explicit user direction, into a full **intelligence platform**
with a sidebar-nav layout — matching the pattern of sibling Netrisyl product Lobels
Biscuits Intelligence initially (tabs), then redesigned to match a supplied dashboard
mockup (sidebar + stat cards + chart grid). Live at
`https://netrisyl-farm-intelligence.onrender.com`: a 9-item left sidebar — **Dashboard**
(new landing page: stat cards + chart grid), **Chat** (the original goal, unchanged),
**Herd & Flock**, **Feeding**, **Health**, **Breeding**, **Finance**, **Reports**
(Findings & Alerts + Data Coverage), **Settings** (see section 4 for the full nav-item
mapping and what's genuinely new vs. carried over). All verified end-to-end against the
live URL via real Playwright screenshots, not just "the deploy succeeded."

The scope grew once more, by explicit user direction, to make the data source itself
**live**: a real Google Sheet now feeds Supabase on a lazy poll-on-request cycle (no more
manual `.xlsx` re-sync), and a global date-range filter reaches every dashboard page and
the chat, with chat's date-scoped answers running the same inject-and-narrate query
first, LLM-narrates-only-that-result discipline as always. See section 5 for the full
architecture, verified end-to-end against the live URL the same way.

The scope grew a final time, by explicit user direction, to make the chatbot answer
"any question the data can actually support," with a hard constraint ruling out
free-form LLM-generated SQL entirely. **That's now done, tested, and live too**: tier-0
(greetings/help) and tier-3 (OpenAI native tool-calling over real, safe Python query
functions - headcount, crop area, crop types, weather, cumulative expenses) sit
alongside the original tier-1/tier-2 catalog, unchanged. A curated data dictionary backs
honest "we don't track that" refusals. Two of the eight tickets that built this
(07-08) were themselves driven by real `query_log` evidence generated within minutes of
first deploying the rest - the observability this whole feature added is already
proving out its own premise. See section 6 for the full architecture and the seven
further directions analyzed (not built) for whoever picks this up next.

**Not built, still deferred, by explicit user sequencing decision** (see section 6's
closing paragraphs for the full reasoning): multi-turn conversation handling, query
result caching, further exhaustive tool coverage (deliberately paced in evidence-driven
batches, not attempted all at once), suggested follow-up question chips, and a domain
summary lookup tab (confirmed independent of the chatbot work, ticketed separately at
`.scratch/domain-summary-lookup/`). Voice input is proven small and could slot in
anytime. Shona language support was evaluated via a real spike, found a genuine
vocabulary defect, and was dropped by the user rather than pursued further. Farm-
switching UI or a module selector remains deferred - there's only one real farm today.
Any analysis/dashboarding on top of `query_log` specifically also remains unbuilt (the
table and write path exist and are now richer with tool-call data; nothing reads that
table yet beyond the ad-hoc real-usage checks described in section 6).

## Suggested skills for the next session

- **mattpocock-skills:tdd** — for any further tier-3 tool (evidence-driven batches,
  per section 6's sequencing decision) or new capability on `answer_question`; the seam
  and testing-split conventions (the primary `answer_question` black-box seam plus the
  one narrow, explicitly-agreed `resolve_tool_call` exception) are now well-established
  precedent across four rounds of catalog growth. Note: the dashboard (section 4)
  deliberately did *not* follow this — no spec, no tickets, no automated tests, by
  explicit user instruction — so don't assume that layer follows the same conventions
  without checking first.
- **mattpocock-skills:grilling** — if multi-turn conversation memory or query-result
  caching (both deliberately deferred, section 6) become the next task; both reopen
  real design questions (how history interacts with the existing global date-range
  filter; cache-key/invalidation shape) worth stress-testing before building, the same
  way tier-0/tier-3 were.
- **mattpocock-skills:to-tickets** — if the domain-summary-lookup ticket
  (`.scratch/domain-summary-lookup/issues/01-domain-summary-lookup-tab.md`, confirmed
  independent, not yet built) or voice input (small, proven, independent - see section
  6) get picked up; neither needs a fresh spec, just implementation.
- **code-review** or **simplify** — `sync/engine.py` (20 near-identical per-table sync
  functions), `chatbot/catalog.py` (a growing list of near-identical `CatalogQuery`
  entries), and now `chatbot/tools.py` (5 tier-3 tools and growing) are all candidates
  for a table-driven refactor now that the pattern is proven several times over.
  Deliberately not done mid-TDD-loop — refactoring is a separate step per the TDD skill.
- **mattpocock-skills:domain-modeling** — if formalizing the workbook's domain
  vocabulary (a `CONTEXT.md` or ADR) makes sense now that the schema has been through
  several real design fixes across the sync, chatbot, and tier-3 builds.
