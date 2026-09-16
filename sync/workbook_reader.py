"""
Reusable reader for the Netrisyl Farm Intelligence workbook's row
convention: row 1 = purpose/cadence note, row 2 = header, row 3 = sample
row (never treated as data), row 4+ = data. Used by the sync engine, and
intended to replace the ad hoc parsing duplicated across
gen_scripts/generate_data.py and gen_scripts/regenerate_feed_inventory.py.
"""


def read_tab_rows(ws) -> list[dict]:
    """Return row 4+ of a tab as a list of dicts keyed by its row-2 header."""
    header = [c.value for c in ws[2]]
    rows = []
    for row in ws.iter_rows(min_row=4, max_col=len(header), values_only=True):
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
