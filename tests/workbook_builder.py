"""
Shared test helper: builds a minimal .xlsx fixture following the real
workbook's row convention (row 1 = purpose note, row 2 = header, row 3 =
sample row, row 4+ = data), so sync tests don't depend on the full
generated Chiedza Mixed Farm workbook.
"""

import openpyxl


def build_workbook(path, sheets: dict):
    """
    sheets: {sheet_name: {"header": [...], "sample": [...] (optional), "rows": [[...], ...]}}
    """
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, spec in sheets.items():
        ws = wb.create_sheet(name)
        if name == "99_LISTS":
            # 99_LISTS has no purpose/sample rows: header is row 1, values start row 2.
            ws.append(spec["header"])
            for row in spec.get("rows", []):
                ws.append(row)
            continue
        ws.append([f"PURPOSE: test fixture for {name}"])
        ws.append(spec["header"])
        ws.append(spec.get("sample", spec["header"]))
        for row in spec.get("rows", []):
            ws.append(row)
    wb.save(path)
