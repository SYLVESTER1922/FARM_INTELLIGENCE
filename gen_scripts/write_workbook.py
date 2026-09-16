import pickle
import openpyxl

SRC = "/Users/vharsh/Farm-Intelligence-App/Netrisyl_Farm_Intelligence_Workbook.xlsx"
SCRATCH_DIR = "/Users/vharsh/Farm-Intelligence-App/gen_scripts"
OUT = "/Users/vharsh/Farm-Intelligence-App/Netrisyl_Farm_Intelligence_Workbook_generated.xlsx"

with open(f"{SCRATCH_DIR}/rows.pkl", "rb") as f:
    rows = pickle.load(f)

COLUMNS = {
    "01_STAFF": ["staff_code", "full_name", "role", "primary_domain", "pay_type", "rate", "active"],
    "02_EXPENSES": ["date", "domain", "category", "item", "quantity", "unit", "unit_cost",
                     "total_cost", "supplier", "payment_method", "batch_ref", "allocation_note",
                     "recorded_by"],
    "03_REVENUE": ["date", "domain", "product", "quantity", "unit", "unit_price", "total_amount",
                    "head_count", "avg_weight_kg", "grade", "buyer", "channel", "payment_status",
                    "batch_ref"],
    "04_LABOUR_LOG": ["date", "staff_code", "domain", "task", "hours", "overtime_hours",
                       "labour_cost", "batch_ref"],
    "05_WEATHER_LOG": ["date", "rainfall_mm", "temp_min_c", "temp_max_c", "humidity_pct", "event"],
    "06_FEED_INVENTORY": ["date", "domain", "feed_type", "opening_kg", "received_kg", "used_kg",
                            "waste_kg", "closing_kg", "unit_cost_per_kg", "supplier", "batch_ref"],
    "07_HEALTH_LOG": ["date", "domain", "batch_code", "animal_tag", "event_type", "symptom",
                        "diagnosis", "product", "dose", "animals_treated", "cost",
                        "withdrawal_until", "outcome", "administered_by"],
    "P1_PIG_BATCHES": ["batch_code", "pen", "breed", "start_date", "start_count", "start_avg_kg",
                         "source", "target_market_date", "status"],
    "P2_PIG_DAILY_LOG": ["date", "batch_code", "pen", "feed_type", "feed_kg", "water_litres",
                           "deaths", "culls", "closing_count", "pen_temp_c", "pen_condition",
                           "notes", "recorded_by"],
    "P3_PIG_WEIGHTS": ["date", "batch_code", "sample_size", "avg_weight_kg", "min_weight_kg",
                         "max_weight_kg", "age_days"],
    "P4_SOW_REGISTER": ["sow_tag", "breed", "date_of_birth", "parity", "body_condition_1_5", "status"],
    "P5_BREEDING_FARROWING": ["sow_tag", "boar_tag", "service_date", "service_type",
                                "pregnancy_confirmed", "expected_farrow_date", "farrow_date",
                                "born_alive", "stillborn", "mummified", "avg_birth_weight_kg",
                                "wean_date", "weaned_count", "avg_wean_weight_kg", "litter_batch_code"],
    "C1_POULTRY_BATCHES": ["batch_code", "bird_type", "breed", "house", "placement_date",
                             "chicks_placed", "chick_unit_cost", "hatchery", "target_off_date",
                             "status"],
    "C2_POULTRY_DAILY_LOG": ["date", "batch_code", "age_days", "deaths", "culls", "closing_birds",
                               "feed_type", "feed_kg", "water_litres", "house_temp_c",
                               "litter_condition", "lighting_hours", "eggs_collected",
                               "eggs_cracked", "eggs_dirty", "notes", "recorded_by"],
    "C3_POULTRY_WEIGHTS": ["date", "batch_code", "age_days", "sample_size", "avg_weight_g",
                             "uniformity_pct"],
    "F1_PLOTS": ["plot_code", "plot_name", "hectares", "soil_type", "irrigation_type", "gps"],
    "F2_PLANTINGS": ["planting_code", "plot_code", "crop", "variety", "season", "planting_date",
                       "area_ha", "seed_kg", "seed_cost", "expected_harvest_date",
                       "expected_yield_tons_ha", "status"],
    "F3_FIELD_OPERATIONS": ["date", "planting_code", "op_type", "product", "rate", "quantity",
                              "unit", "input_cost", "labour_hours", "machine_hours",
                              "irrigation_mm", "notes", "recorded_by"],
    "F4_SCOUTING_LOG": ["date", "planting_code", "growth_stage", "issue_type", "issue_name",
                          "severity_1_5", "incidence_pct", "soil_moisture", "action_taken",
                          "scouted_by"],
    "F5_HARVEST_LOG": ["date", "planting_code", "bags", "quantity_kg", "moisture_pct", "grade",
                         "field_loss_kg", "storage_location", "labour_hours"],
}

# formula column (0-indexed position within COLUMNS list) -> formula template using {r}
FORMULA_COLS = {
    "02_EXPENSES": {"total_cost": "=E{r}*G{r}"},
    "03_REVENUE": {"total_amount": "=D{r}*F{r}"},
    "04_LABOUR_LOG": {"labour_cost": "=IFERROR(INDEX('01_STAFF'!$F:$F,MATCH(B{r},'01_STAFF'!$A:$A,0))*E{r},0)"},
    "P2_PIG_DAILY_LOG": {"closing_count": "=IFERROR(INDEX(P1_PIG_BATCHES!$E:$E,MATCH(B{r},P1_PIG_BATCHES!$A:$A,0))-G{r}-H{r},0)"},
    "P3_PIG_WEIGHTS": {"age_days": '=IFERROR(A{r}-INDEX(P1_PIG_BATCHES!$D:$D,MATCH(B{r},P1_PIG_BATCHES!$A:$A,0)),"")'},
    "P5_BREEDING_FARROWING": {"expected_farrow_date": "=C{r}+114"},
    "F5_HARVEST_LOG": {"quantity_kg": "=C{r}*50"},
}

wb = openpyxl.load_workbook(SRC, data_only=False)

error_prone_cols = 0
total_rows_written = 0
for sheet_name, col_list in COLUMNS.items():
    ws = wb[sheet_name]
    formulas = FORMULA_COLS.get(sheet_name, {})
    data_rows = rows.get(sheet_name, [])
    r = 4
    for row_dict in data_rows:
        for ci, col_name in enumerate(col_list, start=1):
            if col_name in formulas:
                ws.cell(row=r, column=ci, value=formulas[col_name].format(r=r))
            else:
                val = row_dict.get(col_name)
                ws.cell(row=r, column=ci, value=val)
        r += 1
    total_rows_written += len(data_rows)
    print(f"{sheet_name}: wrote {len(data_rows)} rows (rows 4..{r-1})")

print("TOTAL ROWS WRITTEN:", total_rows_written)

wb.save(OUT)
print("Saved to", OUT)
