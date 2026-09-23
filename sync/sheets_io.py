"""
Google Sheets read layer for the live sync. Fetches every tab's raw values
via the Sheets API, then wraps them in a tiny shim (_TabView/SheetsWorkbook)
that satisfies exactly the two openpyxl access patterns
sync/workbook_reader.py's read_tab_rows/read_list_values use
(`ws[N]` for the header row, `.iter_rows(min_row=..., max_col=..., values_only=True)`
for data rows) - so every _sync_* function in sync/engine.py runs completely
unchanged against a Google Sheet, exactly as it does against the .xlsx
workbook.

The new live Sheet uses a simplified convention vs. the old workbook: row 1
is the header, row 2+ is real data - no purpose-note row, no sample row, no
row-3-is-real-data exception for farm_profile/staff. Since this shim's
iter_rows() always yields *all* real data rows regardless of the numeric
min_row the legacy code passes (3 for farm_profile/staff, 4 for everything
else), that legacy distinction - meaningful only in terms of openpyxl's real
row numbers - simply doesn't matter here: both values mean the same thing
("skip the header, give me real data"), which this adapter already provides.
"""

import datetime

from googleapiclient.discovery import build
from google.oauth2 import service_account

SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Google Sheets' serial-date epoch (day 0 = Dec 30, 1899).
_SHEETS_EPOCH = datetime.date(1899, 12, 30)

# Which columns (by header name) hold dates, per tab - the Sheets API
# returns unformatted date cells as a serial day-count, not a string, so
# these need explicit conversion back to a real datetime.date. Matches the
# same tabs/columns sync/engine.py already treats as dates.
DATE_COLUMNS = {
    "00_FARM_PROFILE": {"financial_year_start"},
    "02_EXPENSES": {"date"},
    "03_REVENUE": {"date"},
    "04_LABOUR_LOG": {"date"},
    "05_WEATHER_LOG": {"date"},
    "06_FEED_INVENTORY": {"date"},
    "07_HEALTH_LOG": {"date", "withdrawal_until"},
    "P1_PIG_BATCHES": {"start_date", "target_market_date"},
    "P2_PIG_DAILY_LOG": {"date"},
    "P3_PIG_WEIGHTS": {"date"},
    "P4_SOW_REGISTER": {"date_of_birth"},
    "P5_BREEDING_FARROWING": {
        "service_date", "expected_farrow_date", "farrow_date", "wean_date"},
    "C1_POULTRY_BATCHES": {"placement_date", "target_off_date"},
    "C2_POULTRY_DAILY_LOG": {"date"},
    "C3_POULTRY_WEIGHTS": {"date"},
    "F1_PLOTS": set(),
    "F2_PLANTINGS": {"planting_date", "expected_harvest_date"},
    "F3_FIELD_OPERATIONS": {"date"},
    "F4_SCOUTING_LOG": {"date"},
    "F5_HARVEST_LOG": {"date"},
}


def _serial_to_date(value):
    if isinstance(value, (int, float)):
        return _SHEETS_EPOCH + datetime.timedelta(days=value)
    return value


class _CellView:
    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value


class _TabView:
    def __init__(self, rows, date_columns):
        header = rows[0] if rows else []
        self._header = [_CellView(v) for v in header]
        data = rows[1:] if len(rows) > 1 else []
        date_col_idx = {i for i, name in enumerate(header) if name in date_columns}
        self._data = [
            tuple(self._cell(v, i in date_col_idx) for i, v in enumerate(row))
            for row in data
        ]

    @staticmethod
    def _cell(v, is_date):
        # A blank cell must come through as None (matching openpyxl, which
        # this whole sync engine was written and tested against) - an
        # empty string breaks numeric/date columns downstream (Postgres
        # rejects "" for a NUMERIC column outright).
        if v == "":
            return None
        return _serial_to_date(v) if is_date else v

    def __getitem__(self, _row_num):
        """Legacy code asks for row 1 or row 2 depending on which reader
        called it (read_list_values uses ws[1], read_tab_rows uses ws[2]) -
        both mean "the header row", which is always real row 1 here."""
        return self._header

    def iter_rows(self, min_row=1, max_col=None, values_only=True):
        max_col = max_col or len(self._header)
        for row in self._data:
            padded = list(row) + [None] * (max_col - len(row))
            yield tuple(padded[:max_col])


class SheetsWorkbook:
    """Drop-in stand-in for an openpyxl Workbook, as far as
    sync/workbook_reader.py and sync/engine.py are concerned."""

    def __init__(self, tabs: dict):
        self._views = {
            name: _TabView(rows, DATE_COLUMNS.get(name, set()))
            for name, rows in tabs.items()
        }
        self.sheetnames = list(tabs.keys())

    def __getitem__(self, name):
        return self._views[name]

    def __contains__(self, name):
        return name in self._views


def _sheets_service(creds_path: str):
    creds = service_account.Credentials.from_service_account_file(
        creds_path, scopes=SHEETS_SCOPES
    )
    return build("sheets", "v4", credentials=creds)


def load_sheets_workbook(sheet_id: str, creds_path: str) -> SheetsWorkbook:
    """Fetch every tab's full values in one batchGet call. UNFORMATTED_VALUE
    keeps numbers/booleans as native types and dates as serial day-counts
    (converted to real dates per-tab via DATE_COLUMNS above) rather than
    locale-ambiguous formatted strings."""
    service = _sheets_service(creds_path)
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    tab_names = [s["properties"]["title"] for s in meta.get("sheets", [])]

    result = service.spreadsheets().values().batchGet(
        spreadsheetId=sheet_id,
        ranges=tab_names,
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()

    tabs = {}
    for name, value_range in zip(tab_names, result.get("valueRanges", [])):
        tabs[name] = value_range.get("values", [])
    return SheetsWorkbook(tabs)
