# 05: Sync shared-core operational tables and prove the cross-domain query

**What to build:** The shared-core tables that make cross-domain questions possible —
expenses, revenue, labour, weather, feed inventory, and health — synced into Supabase,
with the feed-cost-split-by-domain query from the prototype now running for real against
Postgres instead of SQLite. This is the ticket that actually delivers on the spec's core
promise: a chatbot backend can ask "how does feed cost split between pigs and chickens"
and get a real, correct answer from the database.

**Blocked by:** 01, 02, 03, 04 (needs `batch_ref`/`planting_code` targets to exist in all
three domain modules)

**Status:** ready-for-agent

- [ ] `02_EXPENSES`, `03_REVENUE`, `04_LABOUR_LOG`, `05_WEATHER_LOG`,
      `06_FEED_INVENTORY`, and `07_HEALTH_LOG` are synced via the shared engine from
      Ticket 01.
- [ ] `06_FEED_INVENTORY` is synced at `domain + feed_type + week` grain (not
      `domain + week`), matching the fix already applied to the workbook
      (`main`, commit `21bd86e`) — not the coarser grain the prototype originally found
      broken.
- [ ] `batch_ref` columns in `02_EXPENSES`/`03_REVENUE`/`04_LABOUR_LOG`/`07_HEALTH_LOG`
      resolve against `P1`/`C1` `batch_code` where non-null, and remain nullable
      otherwise (not every expense/revenue line ties to a batch).
- [ ] Formula-derived columns (`02_EXPENSES.total_cost`, `03_REVENUE.total_amount`,
      `04_LABOUR_LOG.labour_cost`) are synced as their resolved values, never as formula
      text.
- [ ] The feed-cost-split-by-domain query, promoted from
      `prototype_supabase_sync.py` (branch `prototype/supabase-domain-join-test`), runs
      against the real synced Postgres/Supabase tables and resolves with 0 kg of usage
      left unpriced, matching the prototype's finding.
- [ ] A row with an invalid dropdown value (`category`, `payment_status`, `feed_type`,
      etc.) is rejected and reported.
- [ ] Idempotency holds for all six tables.
