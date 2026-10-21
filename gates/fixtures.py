"""
Deliberately dirty workbooks (plan section 10). The synthetic workbook plants its own findings and passes on clean data, so each defect a
real sheet is likely to have is injected here into a fresh copy of the clean workbook. Each fixture names the gate that must fire and its
severity; tests/test_gates_dirty.py runs every one through the gated sync, and evals/dirty_report.py reports detection and what the
chatbot would answer on each.

    wb = dirty("duplicate_expense_row")           # an openpyxl Workbook, never saved
"""

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

import openpyxl

from gates import BLOCK, REPORT, WARN

WORKBOOK = Path(__file__).resolve().parent.parent / "Netrisyl_Farm_Intelligence_Workbook.xlsx"
DATA_ROW = 4


@dataclass(frozen=True)
class Dirty:
    name: str
    describe: str
    gate: str               # the gate that must fire ("" = none must fire: a control)
    severity: str
    apply: callable


def _col(ws, header):
    return [c.value for c in ws[2]].index(header) + 1


def _rows(ws, month=None, **eq):
    """Row numbers of data rows whose date starts with `month` (YYYY-MM) and whose columns equal `eq`."""
    out = []
    for r in range(DATA_ROW, ws.max_row + 1):
        if ws.cell(r, 1).value is None:
            continue
        if month and not str(ws.cell(r, _col(ws, "date")).value).startswith(month):
            continue
        if all(ws.cell(r, _col(ws, k)).value == v for k, v in eq.items()):
            out.append(r)
    return out


def _currency_invalid(wb):
    wb["00_FARM_PROFILE"].cell(3, _col(wb["00_FARM_PROFILE"], "currency")).value = "DOLLARZ"


def _currency_missing(wb):
    wb["00_FARM_PROFILE"].cell(3, _col(wb["00_FARM_PROFILE"], "currency")).value = None


def _mixed_currency(wb):
    ws = wb["02_EXPENSES"]
    note = _col(ws, "allocation_note")
    for r in _rows(ws, "2026-04")[:4]:
        ws.cell(r, note).value = "paid in ZWL 4,500"


def _grams(wb):
    ws = wb["02_EXPENSES"]
    unit = _col(ws, "unit")
    r = _rows(ws, "2026-03")[0]
    ws.cell(r, unit).value = "g"


def _duplicate_expense_row(wb):
    ws = wb["02_EXPENSES"]
    src = _rows(ws, "2026-05")[0]
    dst = ws.max_row + 1
    for c in range(1, ws.max_column + 1):
        ws.cell(dst, c).value = ws.cell(src, c).value


def _category_typo(wb):
    ws = wb["02_EXPENSES"]
    cat = _col(ws, "category")
    for r in _rows(ws, "2026-06")[:2]:
        ws.cell(r, cat).value = "Feeed"


def _missing_expense_month(wb):
    ws = wb["02_EXPENSES"]
    for r in sorted(_rows(ws, "2026-05"), reverse=True):
        ws.delete_rows(r)


def _ten_x_jump(wb):
    """July feed expenses scaled until they are at least twelve times June's."""
    ws = wb["02_EXPENSES"]
    total, cat = _col(ws, "total_cost"), _col(ws, "category")
    feed = lambda month: [r for r in _rows(ws, month) if ws.cell(r, cat).value == "Feed" and isinstance(ws.cell(r, total).value, (int, float))]
    june, july = sum(ws.cell(r, total).value for r in feed("2026-06")), sum(ws.cell(r, total).value for r in feed("2026-07"))
    factor = -(-12 * june // july) if july else 1
    for r in feed("2026-07"):
        ws.cell(r, total).value = ws.cell(r, total).value * factor


def _feed_mismatch(wb):
    ws = wb["06_FEED_INVENTORY"]
    used = _col(ws, "used_kg")
    for r in _rows(ws, "2026-02"):
        if isinstance(ws.cell(r, used).value, (int, float)):
            ws.cell(r, used).value = ws.cell(r, used).value * 3


def _clean(wb):
    pass


DIRTY = {d.name: d for d in (
    Dirty("currency_invalid", "farm currency is not an ISO code", "currency_invalid", BLOCK, _currency_invalid),
    Dirty("currency_missing", "farm currency is blank", "currency_missing", BLOCK, _currency_missing),
    Dirty("mixed_currency_month", "four April expenses are noted in ZWL while the farm is USD", "mixed_currency", BLOCK, _mixed_currency),
    Dirty("kg_vs_g", "an expense is entered in grams, a unit the list does not have", "unrecognised_unit", BLOCK, _grams),
    Dirty("duplicate_expense_row", "a May expense row is pasted twice", "duplicate_primary_key", BLOCK, _duplicate_expense_row),
    Dirty("category_typo", "two June expenses have the category 'Feeed'", "unknown_value", WARN, _category_typo),
    Dirty("missing_expense_month", "every May expense row is gone", "month_without_rows", WARN, _missing_expense_month),
    Dirty("ten_x_feed_jump", "July feed expenses are ten times June's", "category_jump", WARN, _ten_x_jump),
    Dirty("feed_log_mismatch", "February inventory use is triple the daily logs", "feed_reconciliation", REPORT, _feed_mismatch),
    Dirty("clean_control", "the unmodified workbook", "", "", _clean),
)}


def dirty(name):
    wb = openpyxl.load_workbook(WORKBOOK, data_only=True)
    DIRTY[name].apply(wb)
    return wb
