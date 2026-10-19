"""Performance metrics: FCR, weight, harvest yield, breeding, crop plantings."""

from decimal import Decimal

from registry.core import (
    INACTIVE_BATCH_STATUSES, LIVESTOCK, LOGS, Coverage, Metric, Result, bounds, check_period, label,
    latest_log_date, no_record, one, pick_domains, register, rows_of, table_range, union_range,
)


from registry.core import rnd as _f  # exact half-up rounding


# ============================================================================ FCR
_PIG_SAMPLES = """
    SELECT batch_code, date, avg_weight_kg AS kg FROM pig_weights WHERE date BETWEEN %(lo)s AND %(hi)s
    UNION ALL
    SELECT batch_code, start_date, start_avg_kg FROM pig_batches
    WHERE start_avg_kg IS NOT NULL AND start_date BETWEEN %(lo)s AND %(hi)s
"""
_POULTRY_SAMPLES = """
    SELECT batch_code, date, avg_weight_g / 1000.0 AS kg FROM poultry_weights WHERE date BETWEEN %(lo)s AND %(hi)s
"""


def fcr(conn, scope):
    domains = pick_domains(scope, LIVESTOCK)
    lo, hi = bounds(scope)
    rows = []
    for d in domains:
        meta = LOGS[d]
        samples = {}
        for r in rows_of(conn, _PIG_SAMPLES if d == "piggery" else _POULTRY_SAMPLES, {"lo": lo, "hi": hi}):
            if scope.batch_code and r["batch_code"] != scope.batch_code:
                continue
            samples.setdefault(r["batch_code"], []).append((r["date"], float(r["kg"])))
        codes = [r["batch_code"] for r in rows_of(conn, f"SELECT batch_code FROM {meta['batches']} ORDER BY 1")]
        for code in codes:
            if scope.batch_code and code != scope.batch_code:
                continue
            pts = sorted(samples.get(code, []))
            row = {"batch_code": code, "domain": d, "label": label(d), "fcr": None, "feed_kg": None,
                   "gain_kg": None, "from": None, "to": None, "samples": len(pts), "reason": None}
            if len(pts) < 2:
                row["reason"] = "needs at least two weight samples"
                rows.append(row)
                continue
            (d0, w0), (d1, w1) = pts[0], pts[-1]
            count = one(conn, f"SELECT {meta['count']} FROM {meta['log']} WHERE batch_code = %s AND date <= %s "
                              f"ORDER BY date DESC LIMIT 1", (code, d1))
            feed = one(conn, f"SELECT COALESCE(SUM(feed_kg), 0) FROM {meta['log']} "
                             f"WHERE batch_code = %s AND date > %s AND date <= %s", (code, d0, d1))
            gain = (w1 - w0) * (count or 0)
            row.update({"from": d0, "to": d1, "feed_kg": _f(feed, 1), "gain_kg": _f(gain, 1)})
            if gain <= 0:
                row["reason"] = "no weight gain recorded"
            else:
                row["fcr"] = _f(Decimal(feed) / Decimal(str(gain)), 2)
            rows.append(row)
    computed = [r for r in rows if r["fcr"] is not None]
    if not computed:
        return Result("fcr", "not_available", scope, "ratio", rows=rows,
                      message=("Feed conversion needs at least two weight samples per batch, with weight gained; "
                               "none of the batches in scope have them."))
    ranked = sorted(computed, key=lambda r: r["fcr"])
    first, last = union_range(conn, [LOGS[d]["log"] for d in domains])
    _, cov = check_period("feed conversion", scope, first, last)
    skipped = [r for r in rows if r["fcr"] is None]
    notes = ["FCR = feed kg ÷ weight gained kg per batch, between its first and latest weight sample; "
             "weight gained = change in average weight × animals at the latest sample."]
    if skipped:
        notes.append("No FCR for " + ", ".join(r["batch_code"] for r in skipped) + ": not enough weight data.")
    return Result("fcr", "ok", scope, "ratio",
                  {"best_batch": ranked[0]["batch_code"], "best_fcr": ranked[0]["fcr"],
                   "worst_batch": ranked[-1]["batch_code"], "worst_fcr": ranked[-1]["fcr"]},
                  ranked + skipped, cov, notes)


register(Metric(
    id="fcr", title="feed conversion", group="performance",
    definition=("Feed kg ÷ weight gained kg per batch, between its first and latest weight sample (a pig batch's "
                "starting weight counts as its first sample). Where weights are missing the answer is a named refusal."),
    sources=("pig_daily_log", "poultry_daily_log", "pig_weights", "poultry_weights", "pig_batches"),
    unit="ratio", decimals=2, period="range", domains=LIVESTOCK, zero_tolerance=False,
    answers="Which batches convert feed best and worst, and a batch's FCR.",
    does_not_answer="FCR for a batch with fewer than two weight samples.",
    compute=fcr, eval_oracles=("fcr_batch", "fcr_best_worst"), dashboard=("fetch_fcr_by_batch",),
))


# ============================================================================ weight
def weight(conn, scope):
    domains = pick_domains(scope, LIVESTOCK)
    as_of = scope.as_of or latest_log_date(conn, domains)
    rows = []
    for d in domains:
        meta = LOGS[d]
        wsql = ("SELECT DISTINCT ON (w.batch_code) w.batch_code, w.avg_weight_kg AS v, w.date, 'kg' AS unit, b.status "
                "FROM pig_weights w JOIN pig_batches b USING (batch_code) WHERE w.date <= %(as_of)s "
                "ORDER BY w.batch_code, w.date DESC") if d == "piggery" else (
                "SELECT DISTINCT ON (w.batch_code) w.batch_code, w.avg_weight_g AS v, w.date, 'g' AS unit, b.status "
                "FROM poultry_weights w JOIN poultry_batches b USING (batch_code) WHERE w.date <= %(as_of)s "
                "ORDER BY w.batch_code, w.date DESC")
        for r in rows_of(conn, wsql, {"as_of": as_of}):
            if scope.batch_code and r["batch_code"] != scope.batch_code:
                continue
            rows.append({"batch_code": r["batch_code"], "domain": d, "label": label(d), "avg_weight": _f(r["v"], 1),
                         "unit": r["unit"], "date": r["date"], "active": r["status"] not in INACTIVE_BATCH_STATUSES})
    if not rows:
        return Result("weight", "not_available", scope, "kg/g", message="No weight samples are recorded for that.")
    rows.sort(key=lambda r: (not r["active"], r["batch_code"]))
    return Result("weight", "ok", scope, "kg/g", {"as_of": as_of}, rows, Coverage(),
                  ["Pig weights are in kg, poultry weights in grams."])


register(Metric(
    id="weight", title="weights", group="performance",
    definition="Latest sampled average weight per batch on or before a date; kg for pigs, grams for poultry, never mixed.",
    sources=("pig_weights", "poultry_weights"), unit="kg/g", decimals=1, period="snapshot", domains=LIVESTOCK,
    zero_tolerance=False,
    answers="How heavy a batch or a domain's batches are now.",
    does_not_answer="Individual animal weights.",
    compute=weight, eval_oracles=("batch_weight",),
    dashboard=("fetch_batch_summary",),
))


# ============================================================================ harvest yield
def harvest_yield(conn, scope):
    first, last = table_range(conn, "harvest_log")
    msg, cov = check_period("harvests", scope, first, last)
    if msg:
        return no_record("harvest_yield", scope, "kg/ha", msg, cov)
    lo, hi = bounds(scope)
    raw = rows_of(conn, """
        SELECT pl.planting_code, p.plot_code, pl.crop, pl.area_ha, SUM(h.quantity_kg) AS kg,
               SUM(h.field_loss_kg) AS loss
        FROM harvest_log h JOIN plantings pl ON pl.planting_code = h.planting_code
        JOIN plots p ON p.plot_code = pl.plot_code
        WHERE h.date BETWEEN %(lo)s AND %(hi)s
        GROUP BY pl.planting_code, p.plot_code, pl.crop, pl.area_ha""", {"lo": lo, "hi": hi})
    rows = []
    for r in raw:
        area = float(r["area_ha"] or 0)
        kg = float(r["kg"] or 0)
        rows.append({"planting_code": r["planting_code"], "plot_code": r["plot_code"], "crop": r["crop"],
                     "area_ha": area, "harvested_kg": _f(kg, 1), "field_loss_kg": _f(r["loss"], 1),
                     "yield_kg_per_ha": _f(Decimal(str(kg)) / Decimal(str(area)), 1) if area else None})
    rows.sort(key=lambda r: -(r["yield_kg_per_ha"] or 0))
    ranked = [r for r in rows if r["yield_kg_per_ha"] is not None]
    return Result("harvest_yield", "ok", scope, "kg/ha",
                  {"total_harvested_kg": _f(sum(r["harvested_kg"] for r in rows), 1),
                   "total_field_loss_kg": _f(sum(r["field_loss_kg"] for r in rows), 1),
                   "best_plot": ranked[0]["plot_code"] if ranked else None,
                   "best_yield_kg_per_ha": ranked[0]["yield_kg_per_ha"] if ranked else None,
                   "worst_plot": ranked[-1]["plot_code"] if ranked else None,
                   "worst_yield_kg_per_ha": ranked[-1]["yield_kg_per_ha"] if ranked else None},
                  rows, cov)


register(Metric(
    id="harvest_yield", title="harvests", group="performance",
    definition="Harvested kg per hectare by planting (harvest_log.quantity_kg ÷ plantings.area_ha), plus totals and field loss.",
    sources=("harvest_log", "plantings", "plots"), unit="kg/ha", decimals=1, period="range", domains=("crops",),
    zero_tolerance=False,
    answers="How much was harvested (kg) in total or by crop, which plot or crop yields best per hectare, field loss.",
    does_not_answer="Yield forecasts.",
    compute=harvest_yield, eval_oracles=("best_yield_plot", "harvest_total_kg", "yield_for_crop"),
    dashboard=("fetch_crops_summary", "fetch_domain_summary"),
))


# ============================================================================ breeding
def breeding(conn, scope):
    first, last = table_range(conn, "breeding_farrowing", "service_date")
    msg, cov = check_period("breeding records", scope, first, last)
    if msg:
        return no_record("breeding", scope, "piglets", msg, cov)
    lo, hi = bounds(scope)
    rows = rows_of(conn, """
        SELECT sow_tag, service_date, farrow_date, born_alive, stillborn, weaned_count
        FROM breeding_farrowing WHERE service_date BETWEEN %(lo)s AND %(hi)s ORDER BY service_date""",
                   {"lo": lo, "hi": hi})
    done = [r for r in rows if r["farrow_date"] is not None]
    born = sum(r["born_alive"] or 0 for r in done)
    weaned = sum(r["weaned_count"] or 0 for r in done)
    best = max(done, key=lambda r: r["born_alive"] or 0) if done else None
    return Result("breeding", "ok", scope, "piglets",
                  {"litters": len(done), "born_alive": born, "weaned": weaned,
                   "avg_litter_size": _f(Decimal(born) / Decimal(len(done)), 1) if done else None,
                   "best_sow": best["sow_tag"] if best else None,
                   "best_sow_born_alive": best["born_alive"] if best else None},
                  rows, cov, ["Counts litters already farrowed; sows served but not yet farrowed are listed, not counted."])


register(Metric(
    id="breeding", title="breeding records", group="performance",
    definition="Litters farrowed, born alive, weaned, average litter size and best sow, by service date.",
    sources=("breeding_farrowing",), unit="piglets", decimals=0, period="range", domains=("piggery",),
    zero_tolerance=False,
    answers="How many litters, piglets born and weaned, average litter size, which sow did best.",
    does_not_answer="Per-sow history beyond the best litter (later).",
    compute=breeding, eval_oracles=("breeding",), dashboard=("fetch_breeding_summary",),
))


# ============================================================================ crop plantings
def crop_plantings(conn, scope):
    first, last = table_range(conn, "plantings", "planting_date")
    msg, cov = check_period("plantings", scope, first, last)
    if msg:
        return no_record("crop_plantings", scope, "ha", msg, cov)
    lo, hi = bounds(scope)
    r = rows_of(conn, """
        SELECT COALESCE(SUM(area_ha), 0) AS area, COUNT(DISTINCT plot_code) AS plots, COUNT(*) AS n,
               COUNT(*) FILTER (WHERE status != 'Harvested') AS active
        FROM plantings WHERE planting_date BETWEEN %(lo)s AND %(hi)s""", {"lo": lo, "hi": hi})[0]
    crops = [x["crop"] for x in rows_of(conn, """SELECT DISTINCT crop FROM plantings
        WHERE planting_date BETWEEN %(lo)s AND %(hi)s AND crop IS NOT NULL ORDER BY crop""", {"lo": lo, "hi": hi})]
    return Result("crop_plantings", "ok", scope, "ha",
                  {"total_area_ha": _f(r["area"]), "plot_count": r["plots"], "planting_count": r["n"],
                   "active_planting_count": r["active"], "crops": crops}, [], cov)


register(Metric(
    id="crop_plantings", title="plantings", group="performance",
    definition="Hectares planted, plots, plantings and crop types, by planting date.",
    sources=("plantings",), unit="ha", decimals=2, period="range", domains=("crops",), zero_tolerance=False,
    answers="How much land is planted, which crops, how many plantings are still active.",
    does_not_answer="Harvest results (harvest yield).",
    compute=crop_plantings, eval_oracles=("crop_area", "crop_types"),
    dashboard=("fetch_crops_summary",),
))
