from dataclasses import dataclass, field

import openpyxl
import psycopg

from sync.workbook_reader import read_list_values, read_tab_rows


@dataclass
class SyncReport:
    rows_written: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)


def sync_workbook_to_supabase(filepath: str, farm_code: str, dsn: str) -> SyncReport:
    wb = openpyxl.load_workbook(filepath, data_only=True)
    conn = psycopg.connect(dsn, autocommit=True)
    report = SyncReport()

    lists = read_list_values(wb["99_LISTS"]) if "99_LISTS" in wb.sheetnames else {}

    report.rows_written["farm_profile"] = _sync_farm_profile(wb, conn)
    report.rows_written["staff"] = _sync_staff(wb, conn, farm_code, lists, report.errors)
    if lists:
        report.rows_written["list_values"] = _sync_list_values(conn, lists)

    conn.close()
    return report


# staff column -> 99_LISTS column it must be one of
STAFF_DROPDOWN_FIELDS = {
    "primary_domain": "DOMAIN",
    "role": "ROLE",
}


def _validate_dropdowns(table: str, record: dict, key_field: str,
                         dropdown_fields: dict, lists: dict, errors: list) -> bool:
    """Returns True if the record passes all dropdown checks; else appends
    one error per violation to `errors` and returns False."""
    valid = True
    for field_name, list_name in dropdown_fields.items():
        if list_name not in lists:
            continue  # no 99_LISTS data available to validate against
        value = record[field_name]
        if value not in lists[list_name]:
            errors.append({
                "table": table, "row": record[key_field], "field": field_name,
                "value": value, "reason": f"not in 99_LISTS[{list_name}]",
            })
            valid = False
    return valid


def _sync_farm_profile(wb, conn) -> int:
    record = read_tab_rows(wb["00_FARM_PROFILE"])[0]

    conn.execute("""
        CREATE TABLE IF NOT EXISTS farm_profile (
            farm_code TEXT PRIMARY KEY,
            farm_name TEXT,
            region_district TEXT,
            currency TEXT,
            total_hectares NUMERIC,
            module_piggery_active BOOLEAN,
            module_poultry_active BOOLEAN,
            module_crops_active BOOLEAN,
            financial_year_start DATE
        )
    """)
    conn.execute(
        """
        INSERT INTO farm_profile (
            farm_code, farm_name, region_district, currency, total_hectares,
            module_piggery_active, module_poultry_active, module_crops_active,
            financial_year_start
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (farm_code) DO UPDATE SET
            farm_name = EXCLUDED.farm_name,
            region_district = EXCLUDED.region_district,
            currency = EXCLUDED.currency,
            total_hectares = EXCLUDED.total_hectares,
            module_piggery_active = EXCLUDED.module_piggery_active,
            module_poultry_active = EXCLUDED.module_poultry_active,
            module_crops_active = EXCLUDED.module_crops_active,
            financial_year_start = EXCLUDED.financial_year_start
        """,
        (
            record["farm_code"], record["farm_name"], record["region_district"],
            record["currency"], record["total_hectares"],
            record["module_piggery_active"] == "Yes",
            record["module_poultry_active"] == "Yes",
            record["module_crops_active"] == "Yes",
            record["financial_year_start"],
        ),
    )
    return 1


def _sync_staff(wb, conn, farm_code: str, lists: dict, errors: list) -> int:
    records = read_tab_rows(wb["01_STAFF"])

    conn.execute("""
        CREATE TABLE IF NOT EXISTS staff (
            staff_code TEXT PRIMARY KEY,
            farm_code TEXT NOT NULL REFERENCES farm_profile(farm_code),
            full_name TEXT,
            role TEXT,
            primary_domain TEXT,
            pay_type TEXT,
            rate NUMERIC,
            active BOOLEAN
        )
    """)
    written = 0
    for record in records:
        if not _validate_dropdowns("staff", record, "staff_code",
                                    STAFF_DROPDOWN_FIELDS, lists, errors):
            continue
        conn.execute(
            """
            INSERT INTO staff (
                staff_code, farm_code, full_name, role, primary_domain, pay_type,
                rate, active
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (staff_code) DO UPDATE SET
                farm_code = EXCLUDED.farm_code,
                full_name = EXCLUDED.full_name,
                role = EXCLUDED.role,
                primary_domain = EXCLUDED.primary_domain,
                pay_type = EXCLUDED.pay_type,
                rate = EXCLUDED.rate,
                active = EXCLUDED.active
            """,
            (
                record["staff_code"], farm_code, record["full_name"], record["role"],
                record["primary_domain"], record["pay_type"], record["rate"],
                record["active"] == "Yes",
            ),
        )
        written += 1
    return written


def _sync_list_values(conn, lists: dict) -> int:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS list_values (
            list_name TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (list_name, value)
        )
    """)
    count = 0
    for list_name, values in lists.items():
        for value in values:
            conn.execute(
                """
                INSERT INTO list_values (list_name, value) VALUES (%s, %s)
                ON CONFLICT (list_name, value) DO NOTHING
                """,
                (list_name, value),
            )
            count += 1
    return count
