"""
Reusable reader for the Netrisyl Farm Intelligence workbook's row
convention: row 1 = purpose/cadence note, row 2 = header, row 3 = sample
row (never treated as data), row 4+ = data. Used by the sync engine, and
intended to replace the ad hoc parsing duplicated across
gen_scripts/generate_data.py and gen_scripts/regenerate_feed_inventory.py.
"""


def read_tab_rows(ws, min_row: int = 4) -> list[dict]:
    """Return row `min_row`+ of a tab as a list of dicts keyed by its
    row-2 header. Defaults to 4, skipping row 3's sample - but
    00_FARM_PROFILE and 01_STAFF are read from row 3 (see their sync
    functions): the real workbook's data genuinely starts there for
    those two tables (00_FARM_PROFILE has no row 4 at all, being a
    singleton; 01_STAFF's row 3 holds a real, FK-referenced staff
    member, not a discardable example) - confirmed by ticket 06's
    full-workbook regression, not a guess."""
    header = [c.value for c in ws[2]]
    rows = []
    for row in ws.iter_rows(min_row=min_row, max_col=len(header), values_only=True):
        if any(value is not None for value in row):
            rows.append(dict(zip(header, row)))
    return rows


def read_list_values(ws) -> dict:
    """Read 99_LISTS into {list_name: [values...]}, dropping trailing blanks."""
    header = [c.value for c in ws[1]]
    lists = {name: [] for name in header}
    for row in ws.iter_rows(min_row=2, values_only=True):
        for name, value in zip(header, row):
            if value is not None:
                lists[name].append(value)
    return lists
