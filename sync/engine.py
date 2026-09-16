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
    if "P1_PIG_BATCHES" in wb.sheetnames:
        report.rows_written["pig_batches"] = _sync_pig_batches(
            wb, conn, farm_code, lists, report.errors)
    if "P2_PIG_DAILY_LOG" in wb.sheetnames:
        report.rows_written["pig_daily_log"] = _sync_pig_daily_log(
            wb, conn, report.errors)
    if "P3_PIG_WEIGHTS" in wb.sheetnames:
        report.rows_written["pig_weights"] = _sync_pig_weights(
            wb, conn, report.errors)
    if "P4_SOW_REGISTER" in wb.sheetnames:
        report.rows_written["sow_register"] = _sync_sow_register(
            wb, conn, farm_code, lists, report.errors)
    if "P5_BREEDING_FARROWING" in wb.sheetnames:
        report.rows_written["breeding_farrowing"] = _sync_breeding_farrowing(
            wb, conn, lists, report.errors)

    conn.close()
    return report


PIG_BATCH_DROPDOWN_FIELDS = {
    "breed": "BREED_PIG",
    "source": "SOURCE",
    "status": "STATUS_BATCH",
}

SOW_DROPDOWN_FIELDS = {
    "breed": "BREED_PIG",
    "status": "SOW_STATUS",
}

FARROWING_DROPDOWN_FIELDS = {
    "service_type": "SERVICE_TYPE",
    "pregnancy_confirmed": "YESNO",
}


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


def _sync_pig_batches(wb, conn, farm_code: str, lists: dict, errors: list) -> int:
    records = read_tab_rows(wb["P1_PIG_BATCHES"])

    conn.execute("""
        CREATE TABLE IF NOT EXISTS pig_batches (
            batch_code TEXT PRIMARY KEY,
            farm_code TEXT NOT NULL REFERENCES farm_profile(farm_code),
            pen TEXT,
            breed TEXT,
            start_date DATE,
            start_count INTEGER,
            start_avg_kg NUMERIC,
            source TEXT,
            target_market_date DATE,
            status TEXT
        )
    """)
    written = 0
    for record in records:
        if not _validate_dropdowns("pig_batches", record, "batch_code",
                                    PIG_BATCH_DROPDOWN_FIELDS, lists, errors):
            continue
        conn.execute(
            """
            INSERT INTO pig_batches (
                batch_code, farm_code, pen, breed, start_date, start_count,
                start_avg_kg, source, target_market_date, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (batch_code) DO UPDATE SET
                farm_code = EXCLUDED.farm_code,
                pen = EXCLUDED.pen,
                breed = EXCLUDED.breed,
                start_date = EXCLUDED.start_date,
                start_count = EXCLUDED.start_count,
                start_avg_kg = EXCLUDED.start_avg_kg,
                source = EXCLUDED.source,
                target_market_date = EXCLUDED.target_market_date,
                status = EXCLUDED.status
            """,
            (
                record["batch_code"], farm_code, record["pen"], record["breed"],
                record["start_date"], record["start_count"], record["start_avg_kg"],
                record["source"], record["target_market_date"], record["status"],
            ),
        )
        written += 1
    return written


def _sync_pig_daily_log(wb, conn, errors: list) -> int:
    records = read_tab_rows(wb["P2_PIG_DAILY_LOG"])

    conn.execute("""
        CREATE TABLE IF NOT EXISTS pig_daily_log (
            date DATE NOT NULL,
            batch_code TEXT NOT NULL REFERENCES pig_batches(batch_code),
            pen TEXT,
            feed_type TEXT,
            feed_kg NUMERIC,
            water_litres NUMERIC,
            deaths INTEGER,
            culls INTEGER,
            closing_count INTEGER,
            pen_temp_c NUMERIC,
            pen_condition TEXT,
            notes TEXT,
            recorded_by TEXT,
            PRIMARY KEY (date, batch_code)
        )
    """)
    written = 0
    for record in records:
        try:
            conn.execute(
                """
                INSERT INTO pig_daily_log (
                    date, batch_code, pen, feed_type, feed_kg, water_litres,
                    deaths, culls, closing_count, pen_temp_c, pen_condition,
                    notes, recorded_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date, batch_code) DO UPDATE SET
                    pen = EXCLUDED.pen,
                    feed_type = EXCLUDED.feed_type,
                    feed_kg = EXCLUDED.feed_kg,
                    water_litres = EXCLUDED.water_litres,
                    deaths = EXCLUDED.deaths,
                    culls = EXCLUDED.culls,
                    closing_count = EXCLUDED.closing_count,
                    pen_temp_c = EXCLUDED.pen_temp_c,
                    pen_condition = EXCLUDED.pen_condition,
                    notes = EXCLUDED.notes,
                    recorded_by = EXCLUDED.recorded_by
                """,
                (
                    record["date"], record["batch_code"], record["pen"],
                    record["feed_type"], record["feed_kg"], record["water_litres"],
                    record["deaths"], record["culls"], record["closing_count"],
                    record["pen_temp_c"], record["pen_condition"], record["notes"],
                    record["recorded_by"],
                ),
            )
        except psycopg.errors.ForeignKeyViolation:
            conn.rollback()
            errors.append({
                "table": "pig_daily_log",
                "row": f"{record['date']}/{record['batch_code']}",
                "field": "batch_code", "value": record["batch_code"],
                "reason": "no matching batch_code in pig_batches",
            })
            continue
        written += 1
    return written


def _sync_pig_weights(wb, conn, errors: list) -> int:
    records = read_tab_rows(wb["P3_PIG_WEIGHTS"])

    conn.execute("""
        CREATE TABLE IF NOT EXISTS pig_weights (
            date DATE NOT NULL,
            batch_code TEXT NOT NULL REFERENCES pig_batches(batch_code),
            sample_size INTEGER,
            avg_weight_kg NUMERIC,
            min_weight_kg NUMERIC,
            max_weight_kg NUMERIC,
            age_days INTEGER,
            PRIMARY KEY (date, batch_code)
        )
    """)
    written = 0
    for record in records:
        try:
            conn.execute(
                """
                INSERT INTO pig_weights (
                    date, batch_code, sample_size, avg_weight_kg, min_weight_kg,
                    max_weight_kg, age_days
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date, batch_code) DO UPDATE SET
                    sample_size = EXCLUDED.sample_size,
                    avg_weight_kg = EXCLUDED.avg_weight_kg,
                    min_weight_kg = EXCLUDED.min_weight_kg,
                    max_weight_kg = EXCLUDED.max_weight_kg,
                    age_days = EXCLUDED.age_days
                """,
                (
                    record["date"], record["batch_code"], record["sample_size"],
                    record["avg_weight_kg"], record["min_weight_kg"],
                    record["max_weight_kg"], record["age_days"],
                ),
            )
        except psycopg.errors.ForeignKeyViolation:
            conn.rollback()
            errors.append({
                "table": "pig_weights",
                "row": f"{record['date']}/{record['batch_code']}",
                "field": "batch_code", "value": record["batch_code"],
                "reason": "no matching batch_code in pig_batches",
            })
            continue
        written += 1
    return written


def _sync_sow_register(wb, conn, farm_code: str, lists: dict, errors: list) -> int:
    records = read_tab_rows(wb["P4_SOW_REGISTER"])

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sow_register (
            sow_tag TEXT PRIMARY KEY,
            farm_code TEXT NOT NULL REFERENCES farm_profile(farm_code),
            breed TEXT,
            date_of_birth DATE,
            parity INTEGER,
            body_condition_1_5 INTEGER,
            status TEXT
        )
    """)
    written = 0
    for record in records:
        if not _validate_dropdowns("sow_register", record, "sow_tag",
                                    SOW_DROPDOWN_FIELDS, lists, errors):
            continue
        conn.execute(
            """
            INSERT INTO sow_register (
                sow_tag, farm_code, breed, date_of_birth, parity,
                body_condition_1_5, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (sow_tag) DO UPDATE SET
                farm_code = EXCLUDED.farm_code,
                breed = EXCLUDED.breed,
                date_of_birth = EXCLUDED.date_of_birth,
                parity = EXCLUDED.parity,
                body_condition_1_5 = EXCLUDED.body_condition_1_5,
                status = EXCLUDED.status
            """,
            (
                record["sow_tag"], farm_code, record["breed"],
                record["date_of_birth"], record["parity"],
                record["body_condition_1_5"], record["status"],
            ),
        )
        written += 1
    return written


def _sync_breeding_farrowing(wb, conn, lists: dict, errors: list) -> int:
    records = read_tab_rows(wb["P5_BREEDING_FARROWING"])

    conn.execute("""
        CREATE TABLE IF NOT EXISTS breeding_farrowing (
            sow_tag TEXT NOT NULL REFERENCES sow_register(sow_tag),
            boar_tag TEXT,
            service_date DATE NOT NULL,
            service_type TEXT,
            pregnancy_confirmed BOOLEAN,
            expected_farrow_date DATE,
            farrow_date DATE,
            born_alive INTEGER,
            stillborn INTEGER,
            mummified INTEGER,
            avg_birth_weight_kg NUMERIC,
            wean_date DATE,
            weaned_count INTEGER,
            avg_wean_weight_kg NUMERIC,
            litter_batch_code TEXT REFERENCES pig_batches(batch_code),
            PRIMARY KEY (sow_tag, service_date)
        )
    """)
    written = 0
    for record in records:
        if not _validate_dropdowns("breeding_farrowing", record, "sow_tag",
                                    FARROWING_DROPDOWN_FIELDS, lists, errors):
            continue
        try:
            conn.execute(
                """
                INSERT INTO breeding_farrowing (
                    sow_tag, boar_tag, service_date, service_type,
                    pregnancy_confirmed, expected_farrow_date, farrow_date,
                    born_alive, stillborn, mummified, avg_birth_weight_kg,
                    wean_date, weaned_count, avg_wean_weight_kg, litter_batch_code
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (sow_tag, service_date) DO UPDATE SET
                    boar_tag = EXCLUDED.boar_tag,
                    service_type = EXCLUDED.service_type,
                    pregnancy_confirmed = EXCLUDED.pregnancy_confirmed,
                    expected_farrow_date = EXCLUDED.expected_farrow_date,
                    farrow_date = EXCLUDED.farrow_date,
                    born_alive = EXCLUDED.born_alive,
                    stillborn = EXCLUDED.stillborn,
                    mummified = EXCLUDED.mummified,
                    avg_birth_weight_kg = EXCLUDED.avg_birth_weight_kg,
                    wean_date = EXCLUDED.wean_date,
                    weaned_count = EXCLUDED.weaned_count,
                    avg_wean_weight_kg = EXCLUDED.avg_wean_weight_kg,
                    litter_batch_code = EXCLUDED.litter_batch_code
                """,
                (
                    record["sow_tag"], record["boar_tag"], record["service_date"],
                    record["service_type"], record["pregnancy_confirmed"] == "Yes",
                    record["expected_farrow_date"], record["farrow_date"],
                    record["born_alive"], record["stillborn"], record["mummified"],
                    record["avg_birth_weight_kg"], record["wean_date"],
                    record["weaned_count"], record["avg_wean_weight_kg"],
                    record["litter_batch_code"],
                ),
            )
        except psycopg.errors.ForeignKeyViolation:
            conn.rollback()
            errors.append({
                "table": "breeding_farrowing",
                "row": f"{record['sow_tag']}/{record['service_date']}",
                "field": "sow_tag_or_litter_batch_code",
                "value": (record["sow_tag"], record["litter_batch_code"]),
                "reason": "no matching sow_tag in sow_register or "
                          "litter_batch_code in pig_batches",
            })
            continue
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
