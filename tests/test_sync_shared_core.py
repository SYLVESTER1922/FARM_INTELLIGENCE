from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _feed_inventory_sheet(rows):
    return {
        "header": ["date", "domain", "feed_type", "opening_kg", "received_kg",
                   "used_kg", "waste_kg", "closing_kg", "unit_cost_per_kg",
                   "supplier", "batch_ref"],
        "sample": ["2026-09-07", "piggery", "Pig grower", 1200, 500, 430, 5,
                   1265, 0.68, "Profeeds Marondera", None],
        "rows": rows,
    }


def test_sync_writes_feed_inventory_row(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "06_FEED_INVENTORY": _feed_inventory_sheet([
            ["2025-10-06", "poultry", "Chick mash", 0, 142, 34.7, 0.5, 106.8,
             0.98, "Profeeds Marondera", None],
        ]),
    }))

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT used_kg, unit_cost_per_kg FROM feed_inventory "
        "WHERE domain = %s AND feed_type = %s AND date = %s",
        ("poultry", "Chick mash", "2025-10-06"),
    ).fetchone()
    assert float(row[0]) == 34.7 and float(row[1]) == 0.98


def test_sync_writes_weather_log_row(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "05_WEATHER_LOG": {
            "header": ["date", "rainfall_mm", "temp_min_c", "temp_max_c",
                       "humidity_pct", "event"],
            "sample": ["2026-09-01", 0, 14, 27, 48, "Normal"],
            "rows": [["2026-01-08", 0, 22, 39, 30, "Heatwave"]],
        },
    }))

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT temp_max_c, event FROM weather_log WHERE date = %s",
        ("2026-01-08",),
    ).fetchone()
    assert float(row[0]) == 39 and row[1] == "Heatwave"


def _staff_sheet(rows):
    return {
        "header": ["staff_code", "full_name", "role", "primary_domain",
                   "pay_type", "rate", "active"],
        "sample": ["S99", "Sample Person", "Supervisor", "shared", "Daily", 10, "Yes"],
        "rows": rows,
    }


def _labour_log_sheet(rows):
    return {
        "header": ["date", "staff_code", "domain", "task", "hours",
                   "overtime_hours", "labour_cost", "batch_ref"],
        "sample": ["2026-09-01", "S99", "piggery", "Feeding", 8, 0, 96, None],
        "rows": rows,
    }


def test_sync_writes_labour_log_row_without_batch_ref(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    fixture = base_fixture(staff_rows=[
        ["S01", "Tendai Moyo", "Pig attendant", "piggery", "Daily", 12, "Yes"],
    ], extra_sheets={
        "04_LABOUR_LOG": _labour_log_sheet([
            ["2026-01-05", "S01", "piggery", "Feeding", 8, 0, 96, None],
        ]),
    })
    build_workbook(wb_path, fixture)

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT task, hours, batch_ref FROM labour_log "
        "WHERE staff_code = %s AND date = %s",
        ("S01", "2026-01-05"),
    ).fetchone()
    assert row == ("Feeding", 8, None)


def test_sync_rejects_labour_log_row_with_unknown_staff(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "04_LABOUR_LOG": _labour_log_sheet([
            ["2026-01-05", "S-DOES-NOT-EXIST", "piggery", "Feeding", 8, 0, 96, None],
        ]),
    }))

    report = sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    assert report.errors == [
        {"table": "labour_log", "row": "2026-01-05/S-DOES-NOT-EXIST",
         "field": "staff_code", "value": "S-DOES-NOT-EXIST",
         "reason": "no matching staff_code in staff"}
    ]


def test_sync_writes_labour_log_row_with_valid_piggery_batch_ref(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(staff_rows=[
        ["S01", "Tendai Moyo", "Pig attendant", "piggery", "Daily", 12, "Yes"],
    ], extra_sheets={
        "P1_PIG_BATCHES": {
            "header": ["batch_code", "pen", "breed", "start_date", "start_count",
                       "start_avg_kg", "source", "target_market_date", "status"],
            "sample": ["PIG-B99", "Pen 9", "Large White", "2026-01-01", 20, 8.0,
                       "Own farrowing", "2026-05-01", "Active"],
            "rows": [["PIG-B01", "Pen 1", "Large White", "2026-01-05", 24, 8.5,
                      "Own farrowing", "2026-05-20", "Active"]],
        },
        "04_LABOUR_LOG": _labour_log_sheet([
            ["2026-01-05", "S01", "piggery", "Feeding", 8, 0, 96, "PIG-B01"],
        ]),
    }))

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT batch_ref FROM labour_log WHERE staff_code = %s AND date = %s",
        ("S01", "2026-01-05"),
    ).fetchone()
    assert row == ("PIG-B01",)


def test_sync_rejects_labour_log_row_with_unknown_batch_ref(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(staff_rows=[
        ["S01", "Tendai Moyo", "Pig attendant", "piggery", "Daily", 12, "Yes"],
    ], extra_sheets={
        "P1_PIG_BATCHES": {
            "header": ["batch_code", "pen", "breed", "start_date", "start_count",
                       "start_avg_kg", "source", "target_market_date", "status"],
            "sample": ["PIG-B99", "Pen 9", "Large White", "2026-01-01", 20, 8.0,
                       "Own farrowing", "2026-05-01", "Active"],
            "rows": [],
        },
        "04_LABOUR_LOG": _labour_log_sheet([
            ["2026-01-05", "S01", "piggery", "Feeding", 8, 0, 96, "PIG-DOES-NOT-EXIST"],
        ]),
    }))

    report = sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    assert report.errors == [
        {"table": "labour_log", "row": "2026-01-05/S01", "field": "batch_ref",
         "value": "PIG-DOES-NOT-EXIST",
         "reason": "no matching batch_code in pig_batches"}
    ]
    row = db_conn.execute(
        "SELECT * FROM labour_log WHERE staff_code = %s AND date = %s",
        ("S01", "2026-01-05"),
    ).fetchone()
    assert row is None


def _expenses_sheet(rows):
    return {
        "header": ["date", "domain", "category", "item", "quantity", "unit",
                   "unit_cost", "total_cost", "supplier", "payment_method",
                   "batch_ref", "allocation_note", "recorded_by"],
        "sample": ["2026-09-01", "poultry", "Feed", "Broiler starter 50kg", 10,
                   "bag", 34, 340, "Profeeds Marondera", "EcoCash", "BRO-24",
                   None, "S01"],
        "rows": rows,
    }


def test_sync_writes_expense_row(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "02_EXPENSES": _expenses_sheet([
            ["2026-01-06", "piggery", "Feed", "Pig starter 50kg", 10, "bag",
             41, 410, "Profeeds Marondera", "Cash", None, None, "S01"],
        ]),
    }))

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT category, item, total_cost FROM expenses "
        "WHERE date = %s AND domain = %s AND item = %s",
        ("2026-01-06", "piggery", "Pig starter 50kg"),
    ).fetchone()
    assert row[0] == "Feed" and float(row[2]) == 410


def test_sync_rejects_expense_row_with_unknown_batch_ref(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "C1_POULTRY_BATCHES": {
            "header": ["batch_code", "bird_type", "breed", "house",
                       "placement_date", "chicks_placed", "chick_unit_cost",
                       "hatchery", "target_off_date", "status"],
            "sample": ["BRO-99", "Broiler", "Ross 308", "House 9",
                       "2026-08-10", 500, 0.55, "Irvine's Zimbabwe",
                       "2026-09-21", "Growing"],
            "rows": [],
        },
        "02_EXPENSES": _expenses_sheet([
            ["2026-01-06", "poultry", "Feed", "Broiler starter 50kg", 10, "bag",
             34, 340, "Profeeds Marondera", "EcoCash", "BRO-DOES-NOT-EXIST",
             None, "S01"],
        ]),
    }))

    report = sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    assert report.errors == [
        {"table": "expenses", "row": "2026-01-06/poultry/Broiler starter 50kg",
         "field": "batch_ref", "value": "BRO-DOES-NOT-EXIST",
         "reason": "no matching batch_code in poultry_batches"}
    ]


def _revenue_sheet(rows):
    return {
        "header": ["date", "domain", "product", "quantity", "unit", "unit_price",
                   "total_amount", "head_count", "avg_weight_kg", "grade",
                   "buyer", "channel", "payment_status", "batch_ref"],
        "sample": ["2026-09-03", "poultry", "Dressed chicken", 48, "head", 6.2,
                   297.6, 48, 2.1, None, "Local market vendor", "Market",
                   "Paid", "BRO-24"],
        "rows": rows,
    }


def test_sync_writes_revenue_row(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "03_REVENUE": _revenue_sheet([
            ["2026-03-28", "crops", "Soyabean", 1000, "bag", 12, 12000, None,
             None, "A", "Chikafu Grain Traders", "Market", "Owing", None],
        ]),
    }))

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT product, total_amount, payment_status FROM revenue "
        "WHERE date = %s AND domain = %s AND buyer = %s",
        ("2026-03-28", "crops", "Chikafu Grain Traders"),
    ).fetchone()
    assert row[0] == "Soyabean" and float(row[1]) == 12000 and row[2] == "Owing"


def test_sync_rejects_revenue_row_with_invalid_payment_status(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(
        lists={"PAYMENT_STATUS": ["Paid", "Partial", "Owing"]},
        extra_sheets={
            "03_REVENUE": _revenue_sheet([
                ["2026-03-28", "crops", "Soyabean", 1000, "bag", 12, 12000, None,
                 None, "A", "Chikafu Grain Traders", "Market",
                 "Not-A-Real-Status", None],
            ]),
        },
    ))

    report = sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    assert report.errors == [
        {"table": "revenue", "row": "2026-03-28/crops/Chikafu Grain Traders",
         "field": "payment_status", "value": "Not-A-Real-Status",
         "reason": "not in 99_LISTS[PAYMENT_STATUS]"}
    ]


def _health_log_sheet(rows):
    return {
        "header": ["date", "domain", "batch_code", "animal_tag", "event_type",
                   "symptom", "diagnosis", "product", "dose", "animals_treated",
                   "cost", "withdrawal_until", "outcome", "administered_by"],
        "sample": ["2026-08-20", "poultry", "BRO-99", None, "Vaccination",
                   "None", None, "Newcastle LaSota", "1 drop/bird", 500, 18,
                   None, "Ongoing", "S02"],
        "rows": rows,
    }


def test_sync_writes_health_log_row(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "P1_PIG_BATCHES": {
            "header": ["batch_code", "pen", "breed", "start_date", "start_count",
                       "start_avg_kg", "source", "target_market_date", "status"],
            "sample": ["PIG-B99", "Pen 9", "Large White", "2026-01-01", 20, 8.0,
                       "Own farrowing", "2026-05-01", "Active"],
            "rows": [["PIG-B02", "Pen 2", "Landrace", "2026-01-05", 20, 8.5,
                      "Own farrowing", "2026-05-20", "Active"]],
        },
        "07_HEALTH_LOG": _health_log_sheet([
            ["2026-04-25", "piggery", "PIG-B02", None, "Inspection",
             "Diarrhoea", "Suspected bacterial enteritis", None, None, 20, 15,
             None, "Ongoing", "S01"],
        ]),
    }))

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    row = db_conn.execute(
        "SELECT event_type, symptom, cost FROM health_log "
        "WHERE date = %s AND batch_code = %s",
        ("2026-04-25", "PIG-B02"),
    ).fetchone()
    assert row[0] == "Inspection" and row[1] == "Diarrhoea" and float(row[2]) == 15


def test_sync_rejects_health_log_row_with_unknown_batch(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, base_fixture(extra_sheets={
        "P1_PIG_BATCHES": {
            "header": ["batch_code", "pen", "breed", "start_date", "start_count",
                       "start_avg_kg", "source", "target_market_date", "status"],
            "sample": ["PIG-B99", "Pen 9", "Large White", "2026-01-01", 20, 8.0,
                       "Own farrowing", "2026-05-01", "Active"],
            "rows": [],
        },
        "07_HEALTH_LOG": _health_log_sheet([
            ["2026-04-25", "piggery", "PIG-DOES-NOT-EXIST", None, "Inspection",
             "Diarrhoea", "Suspected bacterial enteritis", None, None, 20, 15,
             None, "Ongoing", "S01"],
        ]),
    }))

    report = sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    assert report.errors == [
        {"table": "health_log", "row": "2026-04-25/PIG-DOES-NOT-EXIST/Inspection",
         "field": "batch_code", "value": "PIG-DOES-NOT-EXIST",
         "reason": "no matching batch_code in pig_batches"}
    ]


def _full_shared_core_fixture():
    pig_daily_log_sheet = {
        "header": ["date", "batch_code", "pen", "feed_type", "feed_kg",
                   "water_litres", "deaths", "culls", "closing_count",
                   "pen_temp_c", "pen_condition", "notes", "recorded_by"],
        "sample": ["2026-09-07", "PIG-B99", "Pen 9", "Pig grower", 42, 110, 0,
                   0, 20, 24, "Dry", None, "S01"],
        "rows": [
            ["2026-01-06", "PIG-B01", "Pen 1", "Pig grower", 40, 100, 0, 0, 24,
             24, "Dry", None, "S01"],
            ["2026-01-07", "PIG-B01", "Pen 1", "Pig grower", 42, 105, 0, 0, 24,
             24, "Dry", None, "S01"],
        ],
    }
    poultry_daily_log_sheet = {
        "header": ["date", "batch_code", "age_days", "deaths", "culls",
                   "closing_birds", "feed_type", "feed_kg", "water_litres",
                   "house_temp_c", "litter_condition", "lighting_hours",
                   "eggs_collected", "eggs_cracked", "eggs_dirty", "notes",
                   "recorded_by"],
        "sample": ["2026-09-01", "BRO-99", 22, 2, 0, 498, "Broiler grower", 58,
                   95, 29, "Dry", None, 0, 0, 0, None, "S02"],
        "rows": [
            ["2026-01-06", "BRO-01", 20, 1, 0, 499, "Broiler grower", 50, 90,
             29, "Dry", None, 0, 0, 0, None, "S02"],
        ],
    }
    return base_fixture(extra_sheets={
        "P1_PIG_BATCHES": {
            "header": ["batch_code", "pen", "breed", "start_date", "start_count",
                       "start_avg_kg", "source", "target_market_date", "status"],
            "sample": ["PIG-B99", "Pen 9", "Large White", "2026-01-01", 20, 8.0,
                       "Own farrowing", "2026-05-01", "Active"],
            "rows": [["PIG-B01", "Pen 1", "Large White", "2025-12-01", 24, 8.5,
                      "Own farrowing", "2026-05-20", "Active"]],
        },
        "P2_PIG_DAILY_LOG": pig_daily_log_sheet,
        "C1_POULTRY_BATCHES": {
            "header": ["batch_code", "bird_type", "breed", "house",
                       "placement_date", "chicks_placed", "chick_unit_cost",
                       "hatchery", "target_off_date", "status"],
            "sample": ["BRO-99", "Broiler", "Ross 308", "House 9",
                       "2026-08-10", 500, 0.55, "Irvine's Zimbabwe",
                       "2026-09-21", "Growing"],
            "rows": [["BRO-01", "Broiler", "Ross 308", "House 1",
                      "2025-12-17", 500, 0.55, "Irvine's Zimbabwe",
                      "2026-01-28", "Growing"]],
        },
        "C2_POULTRY_DAILY_LOG": poultry_daily_log_sheet,
        "06_FEED_INVENTORY": _feed_inventory_sheet([
            ["2026-01-05", "piggery", "Pig grower", 400, 250, 82, 1, 567,
             0.68, "Profeeds Marondera", None],
            ["2026-01-05", "poultry", "Broiler grower", 300, 200, 50, 0.5,
             449.5, 0.72, "Profeeds Marondera", None],
        ]),
        "02_EXPENSES": _expenses_sheet([
            ["2026-01-05", "piggery", "Feed", "Pig grower 50kg", 5, "bag", 34,
             170, "Profeeds Marondera", "Cash", None, None, "S01"],
        ]),
        "03_REVENUE": _revenue_sheet([]),
        "04_LABOUR_LOG": _labour_log_sheet([]),
        "05_WEATHER_LOG": {
            "header": ["date", "rainfall_mm", "temp_min_c", "temp_max_c",
                       "humidity_pct", "event"],
            "sample": ["2026-09-01", 0, 14, 27, 48, "Normal"],
            "rows": [],
        },
        "07_HEALTH_LOG": _health_log_sheet([]),
    })


def test_sync_is_idempotent_across_shared_core_tables(tmp_path, db_conn, test_dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _full_shared_core_fixture())

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    counts = {
        table: db_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("expenses", "revenue", "labour_log", "weather_log",
                       "feed_inventory", "health_log")
    }
    assert counts == {
        "expenses": 1, "revenue": 0, "labour_log": 0, "weather_log": 0,
        "feed_inventory": 2, "health_log": 0,
    }


def test_feed_cost_split_by_domain_query_resolves_cleanly(tmp_path, db_conn, test_dsn):
    """Promotes prototype_supabase_sync.py's strict (domain, feed_type) join
    (branch prototype/supabase-domain-join-test) from SQLite to the real
    synced Postgres tables. This is the ticket's core payoff: does the
    shared-core-plus-domain-module design actually answer 'how does feed
    cost split between pigs and chickens' without unpriced usage."""
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _full_shared_core_fixture())

    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    rows = db_conn.execute("""
        WITH domain_usage AS (
            SELECT date, 'piggery' AS domain, feed_type, feed_kg
            FROM pig_daily_log
            UNION ALL
            SELECT date, 'poultry' AS domain, feed_type, feed_kg
            FROM poultry_daily_log
        ),
        priced AS (
            SELECT
                u.domain, u.feed_type, u.feed_kg,
                (SELECT fi.unit_cost_per_kg FROM feed_inventory fi
                 WHERE fi.domain = u.domain AND fi.feed_type = u.feed_type
                   AND fi.date <= u.date
                 ORDER BY fi.date DESC LIMIT 1) AS unit_cost_per_kg
            FROM domain_usage u
        )
        SELECT
            domain,
            ROUND(SUM(feed_kg), 1) AS total_feed_kg,
            SUM(CASE WHEN unit_cost_per_kg IS NULL THEN feed_kg ELSE 0 END) AS unpriced_kg,
            ROUND(SUM(feed_kg * unit_cost_per_kg), 2) AS feed_cost
        FROM priced
        GROUP BY domain
        ORDER BY domain
    """).fetchall()

    by_domain = {r[0]: r for r in rows}
    assert by_domain["piggery"][2] == 0  # unpriced_kg
    assert by_domain["poultry"][2] == 0
    assert float(by_domain["piggery"][3]) == round(82 * 0.68, 2)
    assert float(by_domain["poultry"][3]) == round(50 * 0.72, 2)
