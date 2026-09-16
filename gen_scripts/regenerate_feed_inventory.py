"""
Regenerate ONLY the 06_FEED_INVENTORY tab, at domain+feed_type+week grain
(one row per domain, per feed_type, per week), matching the feed_type
granularity already recorded in P2_PIG_DAILY_LOG / C2_POULTRY_DAILY_LOG.

Why: the original generation logged one row per domain per week (a single
"Pig grower" / "Broiler grower" line all year), while the daily logs
record every growth-stage feed_type (Pig starter/grower/finisher, Chick
mash, Broiler starter/grower/finisher). A cross-domain feed-cost query
joining on (domain, feed_type) failed for most usage as a result - see
prototype/supabase-domain-join-test branch for the finding. This fixes
the data model (finer grain) rather than the query (relaxed join key).

Scope: ONLY 06_FEED_INVENTORY changes. Every other tab (including
02_EXPENSES, which in the original generation derived its Feed line items
from the old coarser feed_inventory receipts) is left exactly as-is.

Reads the actual live daily-log data already written to the workbook
(source of truth), not the original generation script's in-memory state.
"""

import datetime as dt
import random
import openpyxl

WORKBOOK = "../Netrisyl_Farm_Intelligence_Workbook.xlsx"
SEED = 42
random.seed(SEED)

FEED_SUPPLIER = "Profeeds Marondera"
SPIKE_WEEK = dt.date(2026, 2, 2)  # same quirk week as the original generation

# base unit cost per kg, by feed_type - higher-protein early-stage feeds
# cost more; later-stage finisher feeds are cheaper per kg
BASE_UNIT_COST = {
    "Pig starter": 0.82,
    "Pig grower": 0.68,
    "Pig finisher": 0.58,
    "Broiler starter": 0.80,
    "Broiler grower": 0.72,
    "Broiler finisher": 0.63,
    "Chick mash": 0.95,
}

WASTE_PCT = {"piggery": 0.012, "poultry": 0.015}
MIN_STOCK_FLOOR = {"piggery": 120.0, "poultry": 100.0}


def noisy(val, pct=0.1, lo=None):
    v = val * (1 + random.uniform(-pct, pct))
    return max(lo, v) if lo is not None else v


def rnd1(x):
    return round(x, 1)


def week_monday(day):
    return day - dt.timedelta(days=day.weekday())


def load_daily_feed_by_domain_feed_type_week(wb):
    """(domain, feed_type, week_monday) -> summed feed_kg, read from the live sheets."""
    usage = {}

    ws = wb["P2_PIG_DAILY_LOG"]
    for row in ws.iter_rows(min_row=4, max_col=13, values_only=True):
        if row[0] is None:
            continue
        date = dt.date.fromisoformat(str(row[0])[:10])
        feed_type, feed_kg = row[3], row[4]
        if feed_kg is None:
            continue
        wk = week_monday(date)
        key = ("piggery", feed_type, wk)
        usage[key] = usage.get(key, 0.0) + float(feed_kg)

    ws = wb["C2_POULTRY_DAILY_LOG"]
    for row in ws.iter_rows(min_row=4, max_col=17, values_only=True):
        if row[0] is None:
            continue
        date = dt.date.fromisoformat(str(row[0])[:10])
        feed_type, feed_kg = row[6], row[7]
        if feed_kg is None:
            continue
        wk = week_monday(date)
        key = ("poultry", feed_type, wk)
        usage[key] = usage.get(key, 0.0) + float(feed_kg)

    return usage


def build_feed_inventory_rows(usage):
    # group weekly usage by (domain, feed_type) line, in date order
    lines = {}
    for (domain, feed_type, wk), kg in usage.items():
        lines.setdefault((domain, feed_type), {})[wk] = round(kg, 1)

    # find the piggery/poultry (domain, feed_type) line with the most usage
    # in the spike week, to carry the single-event price-spike quirk forward
    spike_line = {"piggery": None, "poultry": None}
    for domain in ("piggery", "poultry"):
        candidates = [(kg, ft) for (d, ft), weeks in lines.items() if d == domain
                      for wk, kg in weeks.items() if wk == SPIKE_WEEK]
        if candidates:
            spike_line[domain] = max(candidates)[1]

    out_rows = []
    for (domain, feed_type), weeks in sorted(lines.items()):
        stock = 0.0
        base_cost = BASE_UNIT_COST.get(feed_type, 0.70)
        first = True
        for wk in sorted(weeks):
            used = weeks[wk]
            received = 0.0
            if used > 0 or (not first and stock < MIN_STOCK_FLOOR[domain]):
                received = round(noisy(max(used * 1.15, 150), 0.1), 0)
            elif first:
                # first delivery for this feed_type line, stock a bit ahead
                received = round(noisy(max(used * 1.3, 150), 0.1), 0)
            first = False

            unit_cost = round(noisy(base_cost, 0.04), 2)
            if wk == SPIKE_WEEK and feed_type == spike_line.get(domain):
                unit_cost = round(base_cost * 1.22, 2)

            waste = rnd1(used * WASTE_PCT[domain])
            opening = rnd1(stock)
            closing = rnd1(opening + received - used - waste)
            stock = closing

            if used > 0 or received > 0:
                out_rows.append(dict(
                    date=wk.isoformat(), domain=domain, feed_type=feed_type,
                    opening_kg=opening, received_kg=received, used_kg=used,
                    waste_kg=waste, closing_kg=closing, unit_cost_per_kg=unit_cost,
                    supplier=FEED_SUPPLIER, batch_ref=None))

    out_rows.sort(key=lambda r: (r["date"], r["domain"], r["feed_type"]))
    return out_rows


def write_feed_inventory(wb, new_rows):
    ws = wb["06_FEED_INVENTORY"]
    cols = [c.value for c in ws[2]]  # header row, source of truth for column order
    ncols = len(cols)

    # wipe existing data rows (row 4 onward), never touch header/sample rows
    for row in ws.iter_rows(min_row=4, max_row=ws.max_row, max_col=ncols):
        for cell in row:
            cell.value = None

    for i, r in enumerate(new_rows):
        excel_row = 4 + i
        for j, col_name in enumerate(cols):
            ws.cell(row=excel_row, column=j + 1, value=r[col_name])

    # update the sheet's own CADENCE note (row 1) to describe the new grain
    purpose_cell = ws["A1"]
    old = purpose_cell.value or ""
    if "one row per domain+feed_type per week" not in old:
        purpose_cell.value = old.replace(
            "CADENCE: Weekly stock count (+ every delivery)",
            "CADENCE: One row per domain+feed_type per week (+ every delivery), "
            "matching the feed_type granularity used in P2/C2 daily logs"
        )


if __name__ == "__main__":
    wb = openpyxl.load_workbook(WORKBOOK, data_only=False)

    usage = load_daily_feed_by_domain_feed_type_week(wb)
    print(f"Distinct (domain, feed_type) lines found in daily logs: "
          f"{len(set((d, ft) for d, ft, _ in usage))}")

    new_rows = build_feed_inventory_rows(usage)
    print(f"New 06_FEED_INVENTORY row count: {len(new_rows)}")
    for (d, ft) in sorted(set((r['domain'], r['feed_type']) for r in new_rows)):
        n = sum(1 for r in new_rows if r['domain'] == d and r['feed_type'] == ft)
        print(f"  {d:<10} {ft:<20} {n} weekly rows")

    write_feed_inventory(wb, new_rows)
    wb.save(WORKBOOK)
    print("Saved.")
