import random
import datetime as dt
import copy
import openpyxl

SEED = 42
random.seed(SEED)

SRC = "/Users/vharsh/Farm-Intelligence-App/Netrisyl_Farm_Intelligence_Workbook.xlsx"
SCRATCH_DIR = "/Users/vharsh/Farm-Intelligence-App/gen_scripts"
OUT = "/Users/vharsh/Farm-Intelligence-App/Netrisyl_Farm_Intelligence_Workbook_generated.xlsx"

WINDOW_START = dt.date(2025, 10, 1)
TODAY = dt.date(2026, 9, 15)

def d(s):
    return dt.date.fromisoformat(s)

def daterange(a, b):
    days = (b - a).days
    for i in range(days + 1):
        yield a + dt.timedelta(days=i)

def noisy(val, pct=0.1, lo=None):
    v = val * (1 + random.uniform(-pct, pct))
    if lo is not None:
        v = max(lo, v)
    return v

def rnd1(x):
    return round(x, 1)

def rnd2(x):
    return round(x, 2)

# ---------------------------------------------------------------------------
# ENTITY DEFINITIONS
# ---------------------------------------------------------------------------

STAFF = [
    dict(staff_code="S02", full_name="Blessing Chikafu", role="Poultry attendant",
         primary_domain="poultry", pay_type="Daily", rate=11, active="Yes"),
    dict(staff_code="S03", full_name="Farai Gumbo", role="Field hand",
         primary_domain="crops", pay_type="Piece-rate", rate=8, active="Yes"),
    dict(staff_code="S04", full_name="Rudo Mutasa", role="Supervisor",
         primary_domain="shared", pay_type="Monthly", rate=450, active="Yes"),
]
STAFF_RATE = {"S01": 12, "S02": 11, "S03": 8, "S04": 450}

PIG_BATCHES = [
    dict(batch_code="PIG-B01", pen="Pen 1", breed="Large White",
         start_date=d("2025-11-02"), start_count=10, start_avg_kg=7.0,
         source="Own farrowing", target_market_date=d("2026-02-22"),
         end_date=d("2026-02-18"), status="Sold", disease=False),
    dict(batch_code="PIG-B02", pen="Pen 1", breed="Duroc cross",
         start_date=d("2026-03-02"), start_count=26, start_avg_kg=9.0,
         source="Bought-in", target_market_date=d("2026-08-15"),
         end_date=d("2026-08-17"), status="Sold", disease=True),
    dict(batch_code="PIG-B03", pen="Pen 2", breed="Landrace",
         start_date=d("2025-11-10"), start_count=24, start_avg_kg=8.2,
         source="Bought-in", target_market_date=d("2026-03-20"),
         end_date=d("2026-03-20"), status="Sold", disease=False),
    dict(batch_code="PIG-B04", pen="Pen 2", breed="Duroc cross",
         start_date=d("2026-05-12"), start_count=12, start_avg_kg=7.2,
         source="Own farrowing", target_market_date=d("2026-09-20"),
         end_date=None, status="Active", disease=False),
]

SOWS = [
    dict(sow_tag="SOW-01", breed="Large White", dob=d("2023-05-10"), parity=2,
         body_condition=3, status="Open"),
    dict(sow_tag="SOW-02", breed="Landrace", dob=d("2022-11-20"), parity=4,
         body_condition=3, status="Pregnant"),
    dict(sow_tag="SOW-03", breed="Duroc cross", dob=d("2023-08-15"), parity=1,
         body_condition=4, status="Lactating"),
]

FARROWINGS = [
    dict(sow_tag="SOW-01", boar_tag="BOAR-01", service_date=d("2025-06-12"),
         service_type="Natural", pregnancy_confirmed="Yes",
         farrow_date=d("2025-10-05"), born_alive=11, stillborn=1, mummified=0,
         avg_birth_weight_kg=1.3, wean_date=d("2025-11-02"), weaned_count=10,
         avg_wean_weight_kg=6.8, litter_batch_code="PIG-B01"),
    dict(sow_tag="SOW-03", boar_tag="BOAR-02", service_date=d("2025-12-20"),
         service_type="AI", pregnancy_confirmed="Yes",
         farrow_date=d("2026-04-14"), born_alive=13, stillborn=0, mummified=1,
         avg_birth_weight_kg=1.4, wean_date=d("2026-05-12"), weaned_count=12,
         avg_wean_weight_kg=7.2, litter_batch_code="PIG-B04"),
    dict(sow_tag="SOW-02", boar_tag="BOAR-01", service_date=d("2026-07-20"),
         service_type="Natural", pregnancy_confirmed="Yes",
         farrow_date=None, born_alive=None, stillborn=None, mummified=None,
         avg_birth_weight_kg=None, wean_date=None, weaned_count=None,
         avg_wean_weight_kg=None, litter_batch_code=None),
]

POULTRY_BATCHES = [
    dict(batch_code="BRO-P01", bird_type="Broiler", breed="Ross 308", house="House 1",
         placement_date=d("2025-10-10"), chicks_placed=500, chick_unit_cost=0.55,
         hatchery="Irvine's Zimbabwe", target_off_date=d("2025-11-21"),
         end_date=d("2025-11-21"), status="Sold", bad=False),
    dict(batch_code="BRO-P02", bird_type="Broiler", breed="Ross 308", house="House 1",
         placement_date=d("2025-12-20"), chicks_placed=520, chick_unit_cost=0.58,
         hatchery="Irvine's Zimbabwe", target_off_date=d("2026-01-31"),
         end_date=d("2026-01-31"), status="Sold", bad=True),
    dict(batch_code="BRO-P03", bird_type="Broiler", breed="Ross 308", house="House 1",
         placement_date=d("2026-03-05"), chicks_placed=500, chick_unit_cost=0.55,
         hatchery="Irvine's Zimbabwe", target_off_date=d("2026-04-16"),
         end_date=d("2026-04-16"), status="Sold", bad=False),
    dict(batch_code="BRO-P04", bird_type="Broiler", breed="Ross 308", house="House 1",
         placement_date=d("2026-08-04"), chicks_placed=510, chick_unit_cost=0.60,
         hatchery="National Foods Hatchery", target_off_date=d("2026-09-15"),
         end_date=None, status="Growing", bad=False),
]

HEATWAVE_DAYS = [d("2026-01-08"), d("2026-01-09"), d("2026-01-10"), d("2026-01-11"), d("2026-01-12")]
HAILSTORM_DAY = d("2026-01-25")
POWERCUT_DAY = d("2026-06-03")
FROST_DAY = d("2026-06-18")

DISEASE_OUTBREAK_START = d("2026-04-25")
DISEASE_OUTBREAK_END = d("2026-05-05")

MISSING_LOG_WEEK = (d("2026-07-01"), d("2026-07-07"))  # PIG-B04, attendant on leave

PLOTS = [
    dict(plot_code="PL1", plot_name="Home field", hectares=10, soil_type="Clay loam",
         irrigation_type="Sprinkler"),
    dict(plot_code="PL2", plot_name="Dam field", hectares=8, soil_type="Sandy loam",
         irrigation_type="Rainfed"),
    dict(plot_code="PL3", plot_name="Valley field", hectares=5, soil_type="Red clay",
         irrigation_type="Drip"),
]

PLANTINGS = [
    dict(planting_code="MZ-PL1-25A", plot_code="PL1", crop="Maize", variety="SC637",
         season="2025 Summer", planting_date=d("2025-11-20"), area_ha=6, seed_kg=150,
         seed_cost=210, expected_harvest_date=d("2026-04-10"), expected_yield=5.5,
         status="Harvested", harvest_date=d("2026-04-12"), debtor=False),
    dict(planting_code="SB-PL2-25A", plot_code="PL2", crop="Soyabean", variety="SC Sequel",
         season="2025 Summer", planting_date=d("2025-11-28"), area_ha=8, seed_kg=480,
         seed_cost=960, expected_harvest_date=d("2026-03-25"), expected_yield=2.2,
         status="Harvested", harvest_date=d("2026-03-28"), debtor=True),
    dict(planting_code="GN-PL3-25A", plot_code="PL3", crop="Groundnuts", variety="Nyanda",
         season="2025 Summer", planting_date=d("2025-12-02"), area_ha=5, seed_kg=300,
         seed_cost=450, expected_harvest_date=d("2026-04-20"), expected_yield=1.5,
         status="Harvested", harvest_date=d("2026-04-22"), debtor=False),
    dict(planting_code="TM-PL1-26A", plot_code="PL1", crop="Tomatoes", variety="Roma VF",
         season="2026 Winter", planting_date=d("2026-05-10"), area_ha=2, seed_kg=0.3,
         seed_cost=180, expected_harvest_date=d("2026-08-15"), expected_yield=25,
         status="Harvested", harvest_date=d("2026-08-18"), debtor=False),
    dict(planting_code="TM-PL2-26A", plot_code="PL2", crop="Tomatoes", variety="Roma VF",
         season="2026 Winter", planting_date=d("2026-06-01"), area_ha=2, seed_kg=0.3,
         seed_cost=180, expected_harvest_date=d("2026-09-05"), expected_yield=25,
         status="Growing", harvest_date=None, debtor=False),
]

# ---------------------------------------------------------------------------
# TAB ROW COLLECTIONS  (each: list of dict keyed by column name, formulas as strings)
# ---------------------------------------------------------------------------
rows = {name: [] for name in [
    "01_STAFF", "02_EXPENSES", "03_REVENUE", "04_LABOUR_LOG", "05_WEATHER_LOG",
    "06_FEED_INVENTORY", "07_HEALTH_LOG", "P1_PIG_BATCHES", "P2_PIG_DAILY_LOG",
    "P3_PIG_WEIGHTS", "P4_SOW_REGISTER", "P5_BREEDING_FARROWING",
    "C1_POULTRY_BATCHES", "C2_POULTRY_DAILY_LOG", "C3_POULTRY_WEIGHTS",
    "F1_PLOTS", "F2_PLANTINGS", "F3_FIELD_OPERATIONS", "F4_SCOUTING_LOG",
    "F5_HARVEST_LOG",
]}

# ---- 01_STAFF ----
for s in STAFF:
    rows["01_STAFF"].append(s)

# ---- P1_PIG_BATCHES ----
for b in PIG_BATCHES:
    rows["P1_PIG_BATCHES"].append(dict(
        batch_code=b["batch_code"], pen=b["pen"], breed=b["breed"],
        start_date=b["start_date"].isoformat(), start_count=b["start_count"],
        start_avg_kg=b["start_avg_kg"], source=b["source"],
        target_market_date=b["target_market_date"].isoformat(), status=b["status"]))

# ---- P4_SOW_REGISTER ----
for s in SOWS:
    rows["P4_SOW_REGISTER"].append(dict(
        sow_tag=s["sow_tag"], breed=s["breed"], date_of_birth=s["dob"].isoformat(),
        parity=s["parity"], body_condition_1_5=s["body_condition"], status=s["status"]))

# ---- C1_POULTRY_BATCHES ----
for b in POULTRY_BATCHES:
    rows["C1_POULTRY_BATCHES"].append(dict(
        batch_code=b["batch_code"], bird_type=b["bird_type"], breed=b["breed"],
        house=b["house"], placement_date=b["placement_date"].isoformat(),
        chicks_placed=b["chicks_placed"], chick_unit_cost=b["chick_unit_cost"],
        hatchery=b["hatchery"], target_off_date=b["target_off_date"].isoformat(),
        status=b["status"]))

# ---- F1_PLOTS ----
for p in PLOTS:
    rows["F1_PLOTS"].append(dict(
        plot_code=p["plot_code"], plot_name=p["plot_name"], hectares=p["hectares"],
        soil_type=p["soil_type"], irrigation_type=p["irrigation_type"], gps=None))

# ---- F2_PLANTINGS ----
for p in PLANTINGS:
    rows["F2_PLANTINGS"].append(dict(
        planting_code=p["planting_code"], plot_code=p["plot_code"], crop=p["crop"],
        variety=p["variety"], season=p["season"], planting_date=p["planting_date"].isoformat(),
        area_ha=p["area_ha"], seed_kg=p["seed_kg"], seed_cost=p["seed_cost"],
        expected_harvest_date=p["expected_harvest_date"].isoformat(),
        expected_yield_tons_ha=p["expected_yield"], status=p["status"]))

# ---------------------------------------------------------------------------
# 05_WEATHER_LOG  (one row per day, seasonality)
# ---------------------------------------------------------------------------
for day in daterange(WINDOW_START, TODAY):
    month = day.month
    rainy = month in (11, 12, 1, 2, 3)
    event = "Normal"
    rainfall = 0
    if day in HEATWAVE_DAYS:
        event = "Heatwave"
        temp_max = round(noisy(38, 0.05), 1)
        temp_min = round(noisy(23, 0.08), 1)
        rainfall = 0
        humidity = round(noisy(30, 0.1))
    elif day == HAILSTORM_DAY:
        event = "Hailstorm"
        rainfall = round(noisy(45, 0.15), 1)
        temp_max = round(noisy(24, 0.05), 1)
        temp_min = round(noisy(15, 0.08), 1)
        humidity = round(noisy(80, 0.05))
    elif day == POWERCUT_DAY:
        event = "Power cut"
        rainfall = round(noisy(2, 0.5), 1) if rainy else 0
        temp_max = round(noisy(21, 0.08), 1)
        temp_min = round(noisy(9, 0.1), 1)
        humidity = round(noisy(45, 0.1))
    elif day == FROST_DAY:
        event = "Frost"
        rainfall = 0
        temp_max = round(noisy(18, 0.06), 1)
        temp_min = round(noisy(1, 0.5), 1)
        humidity = round(noisy(35, 0.1))
    else:
        if rainy:
            temp_max = round(noisy(27, 0.08), 1)
            temp_min = round(noisy(17, 0.1), 1)
            humidity = round(noisy(65, 0.12))
            rainfall = round(max(0, random.gauss(6, 9)), 1) if random.random() < 0.45 else 0
        else:
            temp_max = round(noisy(23, 0.1), 1)
            temp_min = round(noisy(8, 0.2), 1)
            humidity = round(noisy(42, 0.15))
            rainfall = 0
    rows["05_WEATHER_LOG"].append(dict(
        date=day.isoformat(), rainfall_mm=rainfall, temp_min_c=temp_min,
        temp_max_c=temp_max, humidity_pct=max(10, min(95, humidity)), event=event))

# ---------------------------------------------------------------------------
# P2_PIG_DAILY_LOG + running weight/feed tracking (for P3 + feed inventory ties)
# ---------------------------------------------------------------------------
PIG_FEED_STAGE = [
    (0, 30, "Pig starter"), (30, 70, "Pig grower"), (70, 999, "Pig finisher"),
]

def pig_feed_type(age_days):
    for lo, hi, name in PIG_FEED_STAGE:
        if lo <= age_days < hi:
            return name
    return "Pig finisher"

pig_daily_feed_by_domain_week = {}  # (monday_date) -> kg  (piggery)
feed_usage_by_domain_type_week = {}  # (domain, feed_type, monday_date) -> kg
pig_health_events = []
pig_weekly_water = {}

for b in PIG_BATCHES:
    end = b["end_date"] if b["end_date"] else TODAY
    count = b["start_count"]
    recorder = "S01"
    for day in daterange(b["start_date"], end):
        age = (day - b["start_date"]).days
        if b["batch_code"] == "PIG-B04" and MISSING_LOG_WEEK[0] <= day <= MISSING_LOG_WEEK[1]:
            continue  # missing week quirk
        deaths = 0
        culls = 0
        pen_condition = "Dry"
        notes = None
        in_outbreak = b["disease"] and DISEASE_OUTBREAK_START <= day <= DISEASE_OUTBREAK_END
        if in_outbreak:
            pen_condition = "Damp"
            if random.random() < 0.22:
                deaths = 1
                count = max(0, count - deaths)
            if day == DISEASE_OUTBREAK_START:
                notes = "Several pigs off-feed, loose stools - vet called"
        else:
            if random.random() < 0.004 and count > 1:
                deaths = 1
                count -= 1
        feed_type = pig_feed_type(age)
        per_head = 0.35 + 0.021 * age
        per_head = min(per_head, 2.7)
        if in_outbreak:
            per_head *= 0.6
        feed_kg = rnd1(max(0.2, noisy(per_head * count, 0.12)))
        water_litres = rnd1(max(1, noisy(feed_kg * 2.6, 0.15)))
        pen_temp = rnd1(noisy(24, 0.15))
        rows["P2_PIG_DAILY_LOG"].append(dict(
            date=day.isoformat(), batch_code=b["batch_code"], pen=b["pen"],
            feed_type=feed_type, feed_kg=feed_kg, water_litres=water_litres,
            deaths=deaths, culls=culls,
            closing_count=None,  # formula written separately
            pen_temp_c=pen_temp, pen_condition=pen_condition, notes=notes,
            recorded_by=recorder))
        wk = day - dt.timedelta(days=day.weekday())
        pig_daily_feed_by_domain_week[wk] = pig_daily_feed_by_domain_week.get(wk, 0) + feed_kg
        key = ("piggery", feed_type, wk)
        feed_usage_by_domain_type_week[key] = feed_usage_by_domain_type_week.get(key, 0) + feed_kg
    b["final_count"] = count

# Disease outbreak -> 07_HEALTH_LOG rows for PIG-B02
disease_batch = next(b for b in PIG_BATCHES if b["disease"])
outbreak_dates = list(daterange(DISEASE_OUTBREAK_START, DISEASE_OUTBREAK_END))
symptoms_cycle = ["Diarrhoea", "Coughing", "Off-feed"]
for i, day in enumerate([outbreak_dates[0], outbreak_dates[2], outbreak_dates[4], outbreak_dates[6], outbreak_dates[-1]]):
    if i == 0:
        rows["07_HEALTH_LOG"].append(dict(
            date=day.isoformat(), domain="piggery", batch_code=disease_batch["batch_code"],
            animal_tag=None, event_type="Inspection", symptom="Diarrhoea",
            diagnosis="Suspected bacterial enteritis / respiratory complex", product=None,
            dose=None, animals_treated=disease_batch["start_count"], cost=15,
            withdrawal_until=None, outcome="Ongoing", administered_by="S01"))
    else:
        died = 1 if i in (1, 2) else 0
        outcome = "Died" if died else ("Recovered" if i == 4 else "Ongoing")
        rows["07_HEALTH_LOG"].append(dict(
            date=day.isoformat(), domain="piggery", batch_code=disease_batch["batch_code"],
            animal_tag=None, event_type="Treatment", symptom=random.choice(symptoms_cycle),
            diagnosis="Bacterial enteritis / respiratory complex", product="Oxytetracycline LA",
            dose="1ml/10kg IM", animals_treated=random.randint(6, 14), cost=rnd2(noisy(38, 0.2)),
            withdrawal_until=(day + dt.timedelta(days=21)).isoformat(), outcome=outcome,
            administered_by="S01"))

# routine vaccinations for every pig batch (~day 7)
for b in PIG_BATCHES:
    vac_day = b["start_date"] + dt.timedelta(days=7)
    if vac_day <= TODAY:
        rows["07_HEALTH_LOG"].append(dict(
            date=vac_day.isoformat(), domain="piggery", batch_code=b["batch_code"],
            animal_tag=None, event_type="Vaccination", symptom="None", diagnosis=None,
            product="Erysipelas + Parvo combo", dose="2ml IM", animals_treated=b["start_count"],
            cost=rnd2(b["start_count"] * 0.9), withdrawal_until=None, outcome="Recovered",
            administered_by="S01"))

# ---------------------------------------------------------------------------
# P3_PIG_WEIGHTS (fortnightly per batch)
# ---------------------------------------------------------------------------
for b in PIG_BATCHES:
    end = b["end_date"] if b["end_date"] else TODAY
    day = b["start_date"] + dt.timedelta(days=14)
    while day <= end:
        age = (day - b["start_date"]).days
        base = b["start_avg_kg"] + age * 0.62
        if b["disease"] and DISEASE_OUTBREAK_START <= day <= DISEASE_OUTBREAK_END + dt.timedelta(days=14):
            base *= 0.88
        avg_w = rnd1(max(b["start_avg_kg"], noisy(base, 0.06)))
        spread = rnd1(avg_w * 0.18)
        rows["P3_PIG_WEIGHTS"].append(dict(
            date=day.isoformat(), batch_code=b["batch_code"],
            sample_size=min(10, b["start_count"]), avg_weight_kg=avg_w,
            min_weight_kg=rnd1(avg_w - spread), max_weight_kg=rnd1(avg_w + spread),
            age_days=None))
        day += dt.timedelta(days=14)

# ---------------------------------------------------------------------------
# P5_BREEDING_FARROWING
# ---------------------------------------------------------------------------
for f in FARROWINGS:
    rows["P5_BREEDING_FARROWING"].append(dict(
        sow_tag=f["sow_tag"], boar_tag=f["boar_tag"],
        service_date=f["service_date"].isoformat(), service_type=f["service_type"],
        pregnancy_confirmed=f["pregnancy_confirmed"], expected_farrow_date=None,
        farrow_date=f["farrow_date"].isoformat() if f["farrow_date"] else None,
        born_alive=f["born_alive"], stillborn=f["stillborn"], mummified=f["mummified"],
        avg_birth_weight_kg=f["avg_birth_weight_kg"],
        wean_date=f["wean_date"].isoformat() if f["wean_date"] else None,
        weaned_count=f["weaned_count"], avg_wean_weight_kg=f["avg_wean_weight_kg"],
        litter_batch_code=f["litter_batch_code"]))

# ---------------------------------------------------------------------------
# C2_POULTRY_DAILY_LOG
# ---------------------------------------------------------------------------
BROILER_FEED_STAGE = [(0, 10, "Chick mash"), (10, 24, "Broiler starter"),
                       (24, 35, "Broiler grower"), (35, 999, "Broiler finisher")]

def broiler_feed_type(age):
    for lo, hi, name in BROILER_FEED_STAGE:
        if lo <= age < hi:
            return name
    return "Broiler finisher"

poultry_daily_feed_by_week = {}
for b in POULTRY_BATCHES:
    end = b["end_date"] if b["end_date"] else TODAY
    birds = b["chicks_placed"]
    recorder = "S02"
    for day in daterange(b["placement_date"], end):
        age = (day - b["placement_date"]).days
        deaths = 0
        heat_hit = b["bad"] and day in HEATWAVE_DAYS
        if heat_hit:
            deaths = max(1, round(noisy(birds * 0.018, 0.3)))
        else:
            base_rate = 0.0022 if age > 2 else 0.006  # higher early mortality
            if random.random() < base_rate:
                deaths = random.randint(1, 2)
        culls = 1 if (age > 5 and random.random() < 0.01) else 0
        birds = max(0, birds - deaths - culls)
        feed_type = broiler_feed_type(age)
        per_bird = min(0.02 + 0.0026 * age, 0.16)
        feed_kg = rnd1(max(0.3, noisy(per_bird * birds, 0.1)))
        water_litres = rnd1(max(0.5, noisy(feed_kg * 1.8, 0.12)))
        house_temp = rnd1(noisy(31 - age * 0.12, 0.1)) if age < 21 else rnd1(noisy(26, 0.1))
        if heat_hit:
            house_temp = rnd1(noisy(37, 0.05))
        litter = "Dry"
        if heat_hit:
            litter = "Damp"
        notes = "Heat stress - panting, high water intake, elevated mortality" if heat_hit else None
        rows["C2_POULTRY_DAILY_LOG"].append(dict(
            date=day.isoformat(), batch_code=b["batch_code"], age_days=age,
            deaths=deaths, culls=culls, closing_birds=birds, feed_type=feed_type,
            feed_kg=feed_kg, water_litres=water_litres, house_temp_c=house_temp,
            litter_condition=litter, lighting_hours=None if age > 21 else 23,
            eggs_collected=0, eggs_cracked=0, eggs_dirty=0, notes=notes,
            recorded_by=recorder))
        wk = day - dt.timedelta(days=day.weekday())
        poultry_daily_feed_by_week[wk] = poultry_daily_feed_by_week.get(wk, 0) + feed_kg
        key = ("poultry", feed_type, wk)
        feed_usage_by_domain_type_week[key] = feed_usage_by_domain_type_week.get(key, 0) + feed_kg
    b["final_count"] = birds

# heatwave-linked health log entry for BRO-P02
bad_batch = next(b for b in POULTRY_BATCHES if b["bad"])
rows["07_HEALTH_LOG"].append(dict(
    date=d("2026-01-10").isoformat(), domain="poultry", batch_code=bad_batch["batch_code"],
    animal_tag=None, event_type="Inspection", symptom="Off-feed", diagnosis="Heat stress",
    product=None, dose=None, animals_treated=bad_batch["chicks_placed"], cost=0,
    withdrawal_until=None, outcome="Ongoing", administered_by="S02"))

# routine NCD vaccination per broiler batch, day 7
for b in POULTRY_BATCHES:
    vac_day = b["placement_date"] + dt.timedelta(days=7)
    if vac_day <= TODAY:
        rows["07_HEALTH_LOG"].append(dict(
            date=vac_day.isoformat(), domain="poultry", batch_code=b["batch_code"],
            animal_tag=None, event_type="Vaccination", symptom="None", diagnosis=None,
            product="Newcastle LaSota", dose="1 drop/bird", animals_treated=b["chicks_placed"],
            cost=rnd2(b["chicks_placed"] * 0.035), withdrawal_until=None, outcome="Ongoing",
            administered_by="S02"))

# ---------------------------------------------------------------------------
# C3_POULTRY_WEIGHTS (weekly)
# ---------------------------------------------------------------------------
for b in POULTRY_BATCHES:
    end = b["end_date"] if b["end_date"] else TODAY
    day = b["placement_date"] + dt.timedelta(days=7)
    while day <= end:
        age = (day - b["placement_date"]).days
        base_g = 40 + age * 46  # ross308-ish ramp to ~2kg by 42d
        if b["bad"] and day >= d("2026-01-08"):
            base_g *= 0.85
        avg_g = round(max(40, noisy(base_g, 0.06)))
        uniformity = round(max(65, noisy(88 if not b["bad"] else 78, 0.06)))
        rows["C3_POULTRY_WEIGHTS"].append(dict(
            date=day.isoformat(), batch_code=b["batch_code"], age_days=age,
            sample_size=25, avg_weight_g=avg_g, uniformity_pct=uniformity))
        day += dt.timedelta(days=7)

# ---------------------------------------------------------------------------
# 06_FEED_INVENTORY  (one row per domain+feed_type per week, matching the
# feed_type granularity used in P2/C2 daily logs - NOT one row per domain.
# A domain-only grain can't be joined to the daily logs on (domain,
# feed_type) without leaving most usage unpriced - see
# prototype/supabase-domain-join-test for the finding that drove this.)
# ---------------------------------------------------------------------------
FEED_SUPPLIER = "Profeeds Marondera"
SPIKE_WEEK = d("2026-02-02")  # monday - price spike quirk, applied to
                              # whichever (domain, feed_type) line has the
                              # most usage that week, per domain

BASE_UNIT_COST = {
    "Pig starter": 0.82, "Pig grower": 0.68, "Pig finisher": 0.58,
    "Broiler starter": 0.80, "Broiler grower": 0.72, "Broiler finisher": 0.63,
    "Chick mash": 0.95,
}
WASTE_PCT = {"piggery": 0.012, "poultry": 0.015}
MIN_STOCK_FLOOR = {"piggery": 120.0, "poultry": 100.0}

feed_lines = {}
for (domain, feed_type, wk), kg in feed_usage_by_domain_type_week.items():
    feed_lines.setdefault((domain, feed_type), {})[wk] = round(kg, 1)

spike_line = {"piggery": None, "poultry": None}
for domain in ("piggery", "poultry"):
    candidates = [(kg, ft) for (d_, ft), weeks in feed_lines.items() if d_ == domain
                  for wk, kg in weeks.items() if wk == SPIKE_WEEK]
    if candidates:
        spike_line[domain] = max(candidates)[1]

for (domain, feed_type), weeks in sorted(feed_lines.items()):
    stock = 0.0
    base_cost = BASE_UNIT_COST.get(feed_type, 0.70)
    first = True
    for wk in sorted(weeks):
        used = weeks[wk]
        received = 0.0
        if used > 0 or (not first and stock < MIN_STOCK_FLOOR[domain]):
            received = round(noisy(max(used * 1.15, 150), 0.1), 0)
        elif first:
            received = round(noisy(max(used * 1.3, 150), 0.1), 0)
        first = False

        unit_cost = round(noisy(base_cost, 0.04), 2)
        if wk == SPIKE_WEEK and feed_type == spike_line.get(domain):
            unit_cost = round(base_cost * 1.22, 2)

        waste = round(used * WASTE_PCT[domain], 1)
        opening = round(stock, 1)
        closing = round(opening + received - used - waste, 1)
        stock = closing

        if used > 0 or received > 0:
            rows["06_FEED_INVENTORY"].append(dict(
                date=wk.isoformat(), domain=domain, feed_type=feed_type,
                opening_kg=opening, received_kg=received, used_kg=used, waste_kg=waste,
                closing_kg=closing, unit_cost_per_kg=unit_cost, supplier=FEED_SUPPLIER,
                batch_ref=None))

# ---------------------------------------------------------------------------
# F3_FIELD_OPERATIONS, F4_SCOUTING_LOG, F5_HARVEST_LOG
# ---------------------------------------------------------------------------
OP_SEQUENCE = [
    ("Land prep", None, None, None, "kg", 8, 3, 0),
    ("Planting", None, None, None, "kg", 6, 1, 0),
    ("Basal fert", "Compound D", "300 kg/ha", None, "kg", 4, 1, 0),
    ("Top dressing", "AN", "150 kg/ha", None, "kg", 3, 1, 0),
    ("Herbicide", "Glyphosate", "3 l/ha", None, "litre", 3, 0.5, 0),
    ("Weeding", None, None, None, "kg", 10, 0, 0),
]
ISSUE_POOL = [
    ("Pest", "Fall armyworm"), ("Pest", "Aphids"), ("Disease", "Grey leaf spot"),
    ("Weed", "Witchweed"), ("Nutrient", "Nitrogen deficiency"), ("None", "None"),
]
GROWTH_STAGES = ["Emergence", "V6", "Tasselling", "Silking", "Grain fill", "Maturity"]

for p in PLANTINGS:
    plot_ha = p["area_ha"]
    # field operations
    op_day = p["planting_date"] - dt.timedelta(days=5)
    for i, (op_type, product, rate, _, unit, labour_h, machine_h, irrig) in enumerate(OP_SEQUENCE):
        if op_type == "Planting":
            op_day = p["planting_date"]
        qty = plot_ha * (300 if op_type == "Basal fert" else 150 if op_type == "Top dressing"
                          else 3 if op_type == "Herbicide" else 0)
        cost = 0
        if op_type == "Land prep":
            cost = round(noisy(plot_ha * 35, 0.1))
        elif op_type == "Planting":
            cost = 0
        elif op_type == "Basal fert":
            cost = round(noisy(plot_ha * 90, 0.08))
        elif op_type == "Top dressing":
            cost = round(noisy(plot_ha * 65, 0.08))
        elif op_type == "Herbicide":
            cost = round(noisy(plot_ha * 22, 0.1))
        elif op_type == "Weeding":
            cost = 0
        rows["F3_FIELD_OPERATIONS"].append(dict(
            date=op_day.isoformat(), planting_code=p["planting_code"], op_type=op_type,
            product=product, rate=rate, quantity=round(qty, 1) if qty else None, unit=unit,
            input_cost=cost, labour_hours=labour_h, machine_hours=machine_h,
            irrigation_mm=irrig, notes=None, recorded_by="S03"))
        op_day = op_day + dt.timedelta(days=random.randint(18, 30))
        if op_day > (p["harvest_date"] or TODAY):
            break

    # scouting - biweekly through growth
    end_scout = p["harvest_date"] if p["harvest_date"] else TODAY
    sday = p["planting_date"] + dt.timedelta(days=14)
    stage_idx = 0
    while sday <= end_scout:
        stage = GROWTH_STAGES[min(stage_idx, len(GROWTH_STAGES) - 1)]
        stage_idx += 1
        issue_type, issue_name = random.choice(ISSUE_POOL)
        severity = random.randint(1, 3) if issue_type != "None" else None
        incidence = random.randint(3, 20) if issue_type != "None" else 0
        action = "Spot-sprayed affected rows" if issue_type in ("Pest", "Disease") else (
            "Hand-weeded" if issue_type == "Weed" else ("Top-dressed early" if issue_type == "Nutrient" else None))
        moisture = "Moist" if sday.month in (11, 12, 1, 2, 3) else random.choice(["Dry", "Moist"])
        rows["F4_SCOUTING_LOG"].append(dict(
            date=sday.isoformat(), planting_code=p["planting_code"], growth_stage=stage,
            issue_type=issue_type, issue_name=issue_name, severity_1_5=severity,
            incidence_pct=incidence, soil_moisture=moisture, action_taken=action,
            scouted_by="S03"))
        sday += dt.timedelta(days=14)

    # harvest
    if p["harvest_date"]:
        if p["crop"] == "Maize":
            bags = round(plot_ha * p["expected_yield"] * 1000 / 50 * noisy(1, 0.08))
            moisture = rnd1(noisy(13, 0.1))
            grade = random.choice(["A", "A", "B"])
        elif p["crop"] == "Soyabean":
            bags = round(plot_ha * p["expected_yield"] * 1000 / 50 * noisy(1, 0.08))
            moisture = rnd1(noisy(11, 0.1))
            grade = random.choice(["A", "B"])
        elif p["crop"] == "Groundnuts":
            bags = round(plot_ha * p["expected_yield"] * 1000 / 50 * noisy(0.92, 0.1))
            moisture = rnd1(noisy(9, 0.1))
            grade = random.choice(["A", "B"])
        else:  # tomatoes
            bags = round(plot_ha * p["expected_yield"] * 1000 / 50 * noisy(0.9, 0.1))
            moisture = None
            grade = random.choice(["A", "B", "A"])
        storage = "Silo 1" if p["crop"] in ("Maize", "Soyabean", "Groundnuts") else "Sold direct"
        field_loss = round(bags * 50 * 0.02)
        rows["F5_HARVEST_LOG"].append(dict(
            date=p["harvest_date"].isoformat(), planting_code=p["planting_code"], bags=bags,
            quantity_kg=None, moisture_pct=moisture, grade=grade, field_loss_kg=field_loss,
            storage_location=storage, labour_hours=round(noisy(plot_ha * 6, 0.15))))
        p["harvest_bags"] = bags

# ---------------------------------------------------------------------------
# 04_LABOUR_LOG  (daily rows per staff, working days)
# ---------------------------------------------------------------------------
STAFF_DOMAIN = {"S01": "piggery", "S02": "poultry", "S03": "crops", "S04": "shared"}
TASKS_BY_DOMAIN = {
    "piggery": ["Feeding", "Cleaning", "Weighing", "Vaccination"],
    "poultry": ["Feeding", "Cleaning", "Weighing", "Vaccination"],
    "crops": ["Land prep", "Weeding", "Spraying", "Harvest", "Maintenance"],
    "shared": ["Maintenance", "Marketing", "Vaccination", "Weighing"],
}
for day in daterange(WINDOW_START, TODAY):
    if day.weekday() == 6:  # Sunday off, mostly
        if random.random() > 0.15:
            continue
    for staff_code, domain in STAFF_DOMAIN.items():
        if random.random() < 0.08:  # occasional day off / absence
            continue
        task = random.choice(TASKS_BY_DOMAIN[domain])
        hours = 8 if staff_code != "S04" else round(noisy(6, 0.2))
        overtime = 1 if random.random() < 0.1 else 0
        batch_ref = None
        rows["04_LABOUR_LOG"].append(dict(
            date=day.isoformat(), staff_code=staff_code, domain=domain, task=task,
            hours=hours, overtime_hours=overtime, labour_cost=None, batch_ref=batch_ref))

# ---------------------------------------------------------------------------
# 02_EXPENSES
# ---------------------------------------------------------------------------
LATE_PAYMENT_QUIRK_APPLIED = {"done": False}

for wk_row in rows["06_FEED_INVENTORY"]:
    if wk_row["received_kg"] and wk_row["received_kg"] > 0:
        domain = wk_row["domain"]
        qty_bags = round(wk_row["received_kg"] / 50)
        if qty_bags <= 0:
            continue
        unit_cost = round(wk_row["unit_cost_per_kg"] * 50, 2)
        item = f"{wk_row['feed_type']} 50kg"
        rows["02_EXPENSES"].append(dict(
            date=wk_row["date"], domain=domain, category="Feed", item=item,
            quantity=qty_bags, unit="bag", unit_cost=unit_cost, total_cost=None,
            supplier=FEED_SUPPLIER, payment_method=random.choice(["Cash", "EcoCash", "Bank"]),
            batch_ref=None, allocation_note=None, recorded_by=random.choice(["S01", "S02", "S04"])))

for b in PIG_BATCHES:
    if b["source"] == "Bought-in":
        rows["02_EXPENSES"].append(dict(
            date=b["start_date"].isoformat(), domain="piggery", category="Weaners",
            item=f"Weaners x{b['start_count']}", quantity=b["start_count"], unit="head",
            unit_cost=rnd2(noisy(28, 0.1)), total_cost=None, supplier="Local breeder",
            payment_method="Cash", batch_ref=b["batch_code"], allocation_note=None,
            recorded_by="S01"))

for b in POULTRY_BATCHES:
    rows["02_EXPENSES"].append(dict(
        date=b["placement_date"].isoformat(), domain="poultry", category="Day-old chicks",
        item=f"{b['breed']} day-old chicks", quantity=b["chicks_placed"], unit="head",
        unit_cost=b["chick_unit_cost"], total_cost=None, supplier=b["hatchery"],
        payment_method="EcoCash", batch_ref=b["batch_code"], allocation_note=None,
        recorded_by="S02"))

for hlog in rows["07_HEALTH_LOG"]:
    if hlog["cost"]:
        rows["02_EXPENSES"].append(dict(
            date=hlog["date"], domain=hlog["domain"], category="Vet & Meds",
            item=hlog["product"] or hlog["diagnosis"] or "Vet treatment",
            quantity=1, unit="dose", unit_cost=hlog["cost"], total_cost=None,
            supplier="Farm & City Vet", payment_method="Cash", batch_ref=hlog["batch_code"],
            allocation_note=None, recorded_by=hlog["administered_by"]))

for p in PLANTINGS:
    rows["02_EXPENSES"].append(dict(
        date=(p["planting_date"] - dt.timedelta(days=6)).isoformat(), domain="crops",
        category="Seed", item=f"{p['crop']} seed ({p['variety']})", quantity=p["seed_kg"],
        unit="kg", unit_cost=round(p["seed_cost"] / max(p["seed_kg"], 0.01), 2),
        total_cost=None, supplier="SeedCo", payment_method="Bank", batch_ref=p["planting_code"],
        allocation_note=None, recorded_by="S03"))
    for op in rows["F3_FIELD_OPERATIONS"]:
        if op["planting_code"] == p["planting_code"] and op["input_cost"]:
            cat = "Fertiliser" if op["op_type"] in ("Basal fert", "Top dressing") else "Chemicals"
            rows["02_EXPENSES"].append(dict(
                date=op["date"], domain="crops", category=cat, item=f"{op['op_type']} - {op['product'] or op['op_type']}",
                quantity=op["quantity"] or 1, unit=op["unit"], unit_cost=round(op["input_cost"] / (op["quantity"] or 1), 2),
                total_cost=None, supplier="Farm & City", payment_method="Bank",
                batch_ref=p["planting_code"], allocation_note=None, recorded_by="S03"))

# a handful of generic overheads
overhead_dates = [WINDOW_START + dt.timedelta(days=30 * i) for i in range(12)]
for od in overhead_dates:
    if od > TODAY:
        continue
    rows["02_EXPENSES"].append(dict(
        date=od.isoformat(), domain="shared", category="Fuel", item="Diesel - generator/vehicle",
        quantity=round(noisy(40, 0.15)), unit="litre", unit_cost=rnd2(noisy(1.55, 0.05)),
        total_cost=None, supplier="Puma Energy Goromonzi", payment_method="Cash",
        batch_ref=None, allocation_note=None, recorded_by="S04"))
    rows["02_EXPENSES"].append(dict(
        date=od.isoformat(), domain="shared", category="Electricity", item="ZESA prepaid token",
        quantity=1, unit="trip", unit_cost=rnd2(noisy(65, 0.1)), total_cost=None,
        supplier="ZESA", payment_method="EcoCash", batch_ref=None, allocation_note=None,
        recorded_by="S04"))

# ---------------------------------------------------------------------------
# 03_REVENUE
# ---------------------------------------------------------------------------
for b in PIG_BATCHES:
    if b["status"] != "Sold":
        continue
    final_w = b["start_avg_kg"] + (b["end_date"] - b["start_date"]).days * 0.62
    if b["disease"]:
        final_w *= 0.9
    head = b["final_count"]
    avg_w = rnd1(noisy(final_w, 0.05))
    price_per_kg = rnd2(noisy(1.85, 0.06))
    rows["03_REVENUE"].append(dict(
        date=b["end_date"].isoformat(), domain="piggery", product="Live pig",
        quantity=round(head * avg_w, 1), unit="kg", unit_price=price_per_kg,
        total_amount=None, head_count=head, avg_weight_kg=avg_w, grade=None,
        buyer="Colcom Abattoir", channel="Abattoir", payment_status="Paid",
        batch_ref=b["batch_code"]))

for b in POULTRY_BATCHES:
    if b["status"] != "Sold":
        continue
    head = b["final_count"]
    avg_w = rnd1(noisy(2.1 if not b["bad"] else 1.85, 0.05))
    price_per_kg = rnd2(noisy(3.1, 0.05))
    status = "Paid"
    buyer = "Local market vendor"
    channel = "Market"
    if b["batch_code"] == "BRO-P03":
        # briefly-late-but-eventually-paid quirk: contract channel, account customer
        buyer = "Greenline Butchery (30-day account)"
        channel = "Contract"
        status = "Paid"
    rows["03_REVENUE"].append(dict(
        date=b["end_date"].isoformat(), domain="poultry", product="Live broiler",
        quantity=head, unit="head", unit_price=round(price_per_kg * avg_w, 2),
        total_amount=None, head_count=head, avg_weight_kg=avg_w, grade=None,
        buyer=buyer, channel=channel, payment_status=status, batch_ref=b["batch_code"]))

PRODUCT_BY_CROP = {"Maize": "Maize grain", "Soyabean": "Soya", "Groundnuts": "Maize grain",
                    "Tomatoes": "Tomatoes"}
for p in PLANTINGS:
    if p["status"] != "Harvested":
        continue
    bags = p.get("harvest_bags", 0)
    qty_kg = bags * 50
    if p["crop"] == "Maize":
        product, unit, price = "Maize grain", "bag", rnd2(noisy(13, 0.05))
        qty, unit_price_total = bags, price
    elif p["crop"] == "Soyabean":
        product, unit, price = "Soya", "bag", rnd2(noisy(24, 0.06))
        qty, unit_price_total = bags, price
    elif p["crop"] == "Groundnuts":
        product, unit, price = "Maize grain", "bag", rnd2(noisy(30, 0.06))
        qty, unit_price_total = bags, price
    else:
        product, unit, price = "Tomatoes", "crate", rnd2(noisy(9, 0.08))
        qty, unit_price_total = round(qty_kg / 20), price
    status = "Paid"
    buyer = "Mbare Musika trader"
    channel = "Market"
    if p["debtor"]:
        status = "Owing"
        buyer = "Chikafu Grain Traders"
        channel = "Contract"
    rows["03_REVENUE"].append(dict(
        date=p["harvest_date"].isoformat(), domain="crops", product=product,
        quantity=qty, unit=unit, unit_price=unit_price_total, total_amount=None,
        head_count=None, avg_weight_kg=None, grade=random.choice(["A", "B"]),
        buyer=buyer, channel=channel, payment_status=status, batch_ref=p["planting_code"]))

print("Row counts:")
for k, v in rows.items():
    print(f"  {k}: {len(v)}")

import json
with open(f"{SCRATCH_DIR}/rows_dump.json", "w") as f:
    json.dump({"pig_batches": [dict(b, start_date=b["start_date"].isoformat(),
                                     target_market_date=b["target_market_date"].isoformat(),
                                     end_date=b["end_date"].isoformat() if b["end_date"] else None)
                                for b in PIG_BATCHES],
               "poultry_batches": [dict(b, placement_date=b["placement_date"].isoformat(),
                                         target_off_date=b["target_off_date"].isoformat(),
                                         end_date=b["end_date"].isoformat() if b["end_date"] else None)
                                    for b in POULTRY_BATCHES],
               "row_counts": {k: len(v) for k, v in rows.items()}}, f, indent=2)

# save rows to a pickle for the writer script
import pickle
with open(f"{SCRATCH_DIR}/rows.pkl", "wb") as f:
    pickle.dump(rows, f)

print("Generation complete. Seed =", SEED)
