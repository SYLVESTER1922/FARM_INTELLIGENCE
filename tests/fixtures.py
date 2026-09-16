"""Shared fixture-building helpers for sync engine tests."""


def base_fixture(staff_rows=(), lists=None, extra_sheets=None):
    fixture = {
        "00_FARM_PROFILE": {
            "header": ["farm_code", "farm_name", "region_district", "currency",
                       "total_hectares", "module_piggery_active", "module_poultry_active",
                       "module_crops_active", "financial_year_start"],
            "sample": ["NIS-999", "Sample Farm", "Sample District", "USD", 10,
                       "Yes", "Yes", "Yes", "2026-01-01"],
            "rows": [["NIS-001", "Chiedza Mixed Farm", "Goromonzi, Mashonaland East",
                      "USD", 45, "Yes", "Yes", "Yes", "2026-01-01"]],
        },
        "01_STAFF": {
            "header": ["staff_code", "full_name", "role", "primary_domain",
                       "pay_type", "rate", "active"],
            "sample": ["S99", "Sample Person", "Supervisor", "shared", "Daily", 10, "Yes"],
            "rows": list(staff_rows),
        },
    }
    if lists is not None:
        header = list(lists.keys())
        max_len = max((len(v) for v in lists.values()), default=0)
        rows = [
            [lists[name][i] if i < len(lists[name]) else None for name in header]
            for i in range(max_len)
        ]
        fixture["99_LISTS"] = {"header": header, "rows": rows}
    if extra_sheets:
        fixture.update(extra_sheets)
    return fixture
