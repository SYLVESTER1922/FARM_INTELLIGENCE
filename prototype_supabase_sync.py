"""
PROTOTYPE - throwaway, wipe me.

Question this answers: does the "shared-core-plus-domain-module" table design
survive being synced into a real relational store (Postgres/Supabase) and
queried cross-domain?

Stand-in: SQLite instead of Postgres/Supabase (no Docker/Homebrew/Postgres
available on this machine, and the domain-column join doesn't depend on
anything Postgres-specific). Tables mirror the workbook's own columns
exactly - no reshaping applied ahead of time, because whether reshaping
turns out to be necessary IS the question.

Loads 4 tabs from the now-populated workbook:
  - 02_EXPENSES        (shared core, has a `domain` column)
  - 06_FEED_INVENTORY  (shared core, has a `domain` column)
  - P2_PIG_DAILY_LOG   (piggery domain module)
  - C2_POULTRY_DAILY_LOG (poultry domain module)

Then runs ONE query: how does feed cost split between pigs and chickens
for a given month, joining the two domain-module daily logs against the
shared feed-inventory table on `domain` (+ feed_type + week).

Run: python3 prototype_supabase_sync.py
"""

import sqlite3
import datetime
import openpyxl

WORKBOOK = "Netrisyl_Farm_Intelligence_Workbook.xlsx"
DB = ":memory:"  # PROTOTYPE, nothing persisted to disk

TARGET_MONTH = (2026, 8)  # Aug 2026 - the most recently *complete* month
                          # in the Oct 2025-Sep 2026 window (today=2026-09-15,
                          # so Sep 2026 is only half-populated)


def sheet_rows(ws, ncols):
    """Yield data rows (row 4 onward) as tuples, skipping fully-blank rows."""
    for row in ws.iter_rows(min_row=4, max_col=ncols, values_only=True):
        if any(c is not None for c in row):
            yield row


def header(ws, ncols):
    return [c.value for c in ws[2][:ncols]]


def load_workbook_tables(conn):
    wb = openpyxl.load_workbook(WORKBOOK, data_only=True)

    # --- 06_FEED_INVENTORY (shared core, plain literals, no formulas) ---
    ws = wb["06_FEED_INVENTORY"]
    cols = header(ws, 11)
    conn.execute(f"CREATE TABLE feed_inventory ({', '.join(c + ' TEXT' for c in cols)})")
    rows = list(sheet_rows(ws, 11))
    conn.executemany(f"INSERT INTO feed_inventory VALUES ({','.join('?' * len(cols))})", rows)
    print(f"feed_inventory: {len(rows)} rows, columns={cols}")

    # --- 02_EXPENSES (shared core; total_cost is a live formula =E*G that
    # was never recalculated by a real engine, so we compute it ourselves
    # from quantity * unit_cost rather than trust the cached formula cell) ---
    ws = wb["02_EXPENSES"]
    cols = header(ws, 13)
    conn.execute(f"CREATE TABLE expenses ({', '.join(c + ' TEXT' for c in cols)})")
    raw_rows = list(sheet_rows(ws, 13))
    qty_i, cost_i, total_i = cols.index("quantity"), cols.index("unit_cost"), cols.index("total_cost")
    rows = []
    for r in raw_rows:
        r = list(r)
        if r[qty_i] is not None and r[cost_i] is not None:
            r[total_i] = round(float(r[qty_i]) * float(r[cost_i]), 2)
        rows.append(tuple(r))
    conn.executemany(f"INSERT INTO expenses VALUES ({','.join('?' * len(cols))})", rows)
    print(f"expenses: {len(rows)} rows, columns={cols}")

    # --- P2_PIG_DAILY_LOG (piggery domain module; closing_count is a live
    # formula, irrelevant to this query, left as-is / ignored) ---
    ws = wb["P2_PIG_DAILY_LOG"]
    cols = header(ws, 13)
    conn.execute(f"CREATE TABLE pig_daily_log ({', '.join(c + ' TEXT' for c in cols)})")
    rows = list(sheet_rows(ws, 13))
    conn.executemany(f"INSERT INTO pig_daily_log VALUES ({','.join('?' * len(cols))})", rows)
    print(f"pig_daily_log: {len(rows)} rows, columns={cols}")

    # --- C2_POULTRY_DAILY_LOG (poultry domain module) ---
    ws = wb["C2_POULTRY_DAILY_LOG"]
    cols = header(ws, 17)
    conn.execute(f"CREATE TABLE poultry_daily_log ({', '.join(c + ' TEXT' for c in cols)})")
    rows = list(sheet_rows(ws, 17))
    conn.executemany(f"INSERT INTO poultry_daily_log VALUES ({','.join('?' * len(cols))})", rows)
    print(f"poultry_daily_log: {len(rows)} rows, columns={cols}")


def run_the_one_query(conn, year, month):
    """
    Feed cost per domain for the given month, by joining each domain's
    daily-log feed_kg against the shared feed_inventory table's
    unit_cost_per_kg for the matching domain + feed_type + week.

    This is the actual test: pig_daily_log and poultry_daily_log have
    DIFFERENT column layouts (no shared schema beyond date/feed_type/feed_kg
    happening to have the same names) - so validating the design means
    checking whether a UNION ALL over just the columns needed is clean,
    or whether it needs real reshaping.
    """
    month_str = f"{year:04d}-{month:02d}"

    query = f"""
    WITH domain_usage AS (
        -- normalize both domain-module daily logs to one shared shape
        SELECT date, 'piggery' AS domain, feed_type, feed_kg FROM pig_daily_log
        WHERE substr(date, 1, 7) = '{month_str}'
        UNION ALL
        SELECT date, 'poultry' AS domain, feed_type, feed_kg FROM poultry_daily_log
        WHERE substr(date, 1, 7) = '{month_str}'
    ),
    priced_strict AS (
        -- attempt 1: join on domain + feed_type (the literal design as
        -- specified). Price = most recent feed_inventory delivery for
        -- that EXACT domain+feed_type on/before the usage date.
        -- (SQLite note: the outer-row date reference has to appear in the
        -- subquery's WHERE clause, not only in ORDER BY, or SQLite fails
        -- to bind it as a correlated reference at all - a real quirk hit
        -- while building this, not a stylistic choice)
        SELECT
            u.domain, u.feed_type, u.feed_kg,
            (SELECT fi.unit_cost_per_kg FROM feed_inventory fi
             WHERE fi.domain = u.domain AND fi.feed_type = u.feed_type AND fi.date <= u.date
             ORDER BY fi.date DESC LIMIT 1) AS unit_cost_per_kg
        FROM domain_usage u
    ),
    priced_relaxed AS (
        -- attempt 2: join on domain only, ignoring feed_type, since
        -- feed_inventory turns out to only track one feed_type per domain
        -- all year while the daily logs record every growth-stage feed
        SELECT
            u.domain, u.feed_type, u.feed_kg,
            (SELECT fi.unit_cost_per_kg FROM feed_inventory fi
             WHERE fi.domain = u.domain AND fi.date <= u.date
             ORDER BY fi.date DESC LIMIT 1) AS unit_cost_per_kg
        FROM domain_usage u
    )
    SELECT 'strict (domain+feed_type)' AS strategy, domain,
           ROUND(SUM(feed_kg), 1) AS total_feed_kg_used,
           SUM(CASE WHEN unit_cost_per_kg IS NULL THEN feed_kg ELSE 0 END) AS unpriced_kg,
           ROUND(SUM(feed_kg * unit_cost_per_kg), 2) AS feed_cost_usd
    FROM priced_strict GROUP BY domain
    UNION ALL
    SELECT 'relaxed (domain only)', domain,
           ROUND(SUM(feed_kg), 1),
           SUM(CASE WHEN unit_cost_per_kg IS NULL THEN feed_kg ELSE 0 END),
           ROUND(SUM(feed_kg * unit_cost_per_kg), 2)
    FROM priced_relaxed GROUP BY domain
    ORDER BY 1, 2;
    """

    cur = conn.execute(query)
    results = cur.fetchall()

    # cross-check against 02_EXPENSES Feed-category spend for the same month,
    # to see whether the two sources of truth roughly agree
    cross_check_query = f"""
    SELECT domain, ROUND(SUM(total_cost), 2) AS feed_purchase_cost_usd
    FROM expenses
    WHERE category = 'Feed' AND substr(date, 1, 7) = '{month_str}'
    GROUP BY domain
    ORDER BY domain;
    """
    cross_check = conn.execute(cross_check_query).fetchall()

    return query, results, cross_check_query, cross_check


if __name__ == "__main__":
    conn = sqlite3.connect(DB)
    load_workbook_tables(conn)

    year, month = TARGET_MONTH
    query, results, cc_query, cc_results = run_the_one_query(conn, year, month)

    print(f"\n=== Feed cost by domain, usage-based ({year:04d}-{month:02d}) ===")
    print(f"{'strategy':<28} {'domain':<10} {'feed_kg':>10} {'unpriced_kg':>12} {'feed_cost_usd':>14}")
    for strategy, domain, kg, unpriced, cost in results:
        print(f"{strategy:<28} {domain:<10} {kg:>10} {unpriced:>12} {str(cost):>14}")

    print(f"\n=== Cross-check: 02_EXPENSES Feed-category spend, same month ===")
    print(f"{'domain':<10} {'purchase_cost_usd':>18}")
    for domain, cost in cc_results:
        print(f"{domain:<10} {cost:>18}")

    print("\n=== Verdict ===")
    strict_unpriced = sum(r[3] for r in results if r[0].startswith("strict"))
    relaxed_unpriced = sum(r[3] for r in results if r[0].startswith("relaxed"))
    print(f"Strict join (domain+feed_type): {strict_unpriced} kg unpriced (no matching feed_type in feed_inventory).")
    print(f"Relaxed join (domain only):     {relaxed_unpriced} kg unpriced.")
    if strict_unpriced > 0 and relaxed_unpriced == 0:
        print("\nAWKWARD, as specified: joining on (domain, feed_type) fails because")
        print("06_FEED_INVENTORY only ever logs ONE feed_type per domain per year,")
        print("while the daily logs record every growth-stage feed_type. The")
        print("shared-core-plus-domain-module design DOES hold once the join key")
        print("is relaxed to domain-only - that's the fix needed before scaling.")
    elif strict_unpriced == 0:
        print("\nClean: the strict domain+feed_type join worked as originally specified.")
    else:
        print("\nStill awkward even domain-only - needs further investigation before scaling.")
