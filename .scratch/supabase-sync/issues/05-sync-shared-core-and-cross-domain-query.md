# 05: Sync shared-core operational tables and prove the cross-domain query

**What to build:** The shared-core tables that make cross-domain questions possible —
expenses, revenue, labour, weather, feed inventory, and health — synced into Supabase,
with the feed-cost-split-by-domain query from the prototype now running for real against
Postgres instead of SQLite. This is the ticket that actually delivers on the spec's core
promise: a chatbot backend can ask "how does feed cost split between pigs and chickens"
and get a real, correct answer from the database.

**Blocked by:** 01, 02, 03, 04 (needs `batch_ref`/`planting_code` targets to exist in all
three domain modules)

**Status:** done

- [x] `02_EXPENSES`, `03_REVENUE`, `04_LABOUR_LOG`, `05_WEATHER_LOG`,
      `06_FEED_INVENTORY`, and `07_HEALTH_LOG` are synced via the shared engine from
      Ticket 01.
      (`_sync_expenses`, `_sync_revenue`, `_sync_labour_log`, `_sync_weather_log`,
      `_sync_feed_inventory`, `_sync_health_log` in `sync/engine.py`)
- [x] `06_FEED_INVENTORY` is synced at `domain + feed_type + week` grain (not
      `domain + week`), matching the fix already applied to the workbook
      (`main`, commit `21bd86e`) — not the coarser grain the prototype originally found
      broken. (`PRIMARY KEY (date, domain, feed_type)`)
- [x] `batch_ref` columns in `02_EXPENSES`/`03_REVENUE`/`04_LABOUR_LOG`/`07_HEALTH_LOG`
      resolve against `P1`/`C1` `batch_code` where non-null, and remain nullable
      otherwise (not every expense/revenue line ties to a batch).
      (new `_validate_batch_ref` helper: polymorphic, resolves against
      `pig_batches` or `poultry_batches` depending on the row's `domain`, since a
      single hard FK can't span two possible target tables; proven with both a
      valid piggery `batch_ref` and a rejected unknown one, plus separately for
      `expenses` and `health_log`'s own reference column — correction: this was
      later found to actually be named `batch_ref` too, not `batch_code` as
      written here at the time; see ticket 06's findings)
- [x] Formula-derived columns (`02_EXPENSES.total_cost`, `03_REVENUE.total_amount`,
      `04_LABOUR_LOG.labour_cost`) are synced as their resolved values, never as formula
      text — inherent to reading with `data_only=True`.
- [x] The feed-cost-split-by-domain query, promoted from
      `prototype_supabase_sync.py` (branch `prototype/supabase-domain-join-test`), runs
      against the real synced Postgres/Supabase tables and resolves with 0 kg of usage
      left unpriced, matching the prototype's finding.
      (`test_feed_cost_split_by_domain_query_resolves_cleanly`, run against real
      local Postgres, not SQLite)
- [x] A row with an invalid dropdown value (`category`, `payment_status`, `feed_type`,
      etc.) is rejected and reported.
      (`test_sync_rejects_revenue_row_with_invalid_payment_status`; the mechanism
      was already proven generic across 4 tables and 6+ fields in tickets 01-04)
- [x] Idempotency holds for all six tables.
      (`test_sync_is_idempotent_across_shared_core_tables`)

Also generalized `_validate_dropdowns` (and reused the pattern for
`_validate_batch_ref`) from a single-column natural key to an arbitrary `row_id`
string, since several of these tables (expenses, revenue, health_log) have no
single-column natural key — needed to report a meaningful row identifier on
violation. Confirmed the refactor was safe by running the full suite (41 passing
at that point) before adding new behavior on top.
