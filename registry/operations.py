"""Operations metrics: feed stock, market readiness, health events, weather."""

import datetime as dt

from registry.core import (
    INACTIVE_BATCH_STATUSES, LIVESTOCK, LOGS, Coverage, Metric, Result, bounds, check_period, label,
    latest_log_date, no_record, one, pick_domains, register, rows_of, table_range,
)


from registry.core import rnd as _f  # exact half-up rounding


# ============================================================================ feed stock
def feed_stock(conn, scope):
    first, last = table_range(conn, "feed_inventory")
    as_of = scope.as_of or last
    msg, cov = check_period("feed stock", scope.with_(start=as_of, end=as_of), first, last)
    if msg:
        return no_record("feed_stock", scope, "kg", msg, cov)
    doms = list(pick_domains(scope, LIVESTOCK))
    raw = rows_of(conn, """
        SELECT DISTINCT ON (domain, feed_type) domain, feed_type, closing_kg, date FROM feed_inventory
        WHERE date <= %(as_of)s AND domain = ANY(%(doms)s) ORDER BY domain, feed_type, date DESC""",
                  {"as_of": as_of, "doms": doms})
    rows = [{"domain": r["domain"], "label": label(r["domain"]), "feed_type": r["feed_type"],
             "closing_kg": _f(r["closing_kg"], 1), "date": r["date"]} for r in raw]
    by_domain = {d: _f(sum(r["closing_kg"] for r in rows if r["domain"] == d), 1) for d in doms}
    return Result("feed_stock", "ok", scope, "kg",
                  {"as_of": as_of, "total_kg": _f(sum(by_domain.values()), 1), "by_domain": by_domain}, rows, cov)


register(Metric(
    id="feed_stock", title="feed stock", group="operations",
    definition="Feed on hand: the latest closing_kg per feed type on or before a date (default: the latest inventory date).",
    sources=("feed_inventory",), unit="kg", decimals=1, period="snapshot", domains=LIVESTOCK, zero_tolerance=False,
    answers="How much feed is left or on hand, per domain and feed type.",
    does_not_answer="How fast it will run out, or what it cost (feed consumed cost).",
    compute=feed_stock, eval_oracles=("feed_stock",),
    parity_exempt="No dashboard page shows feed stock on hand.",
))


# ============================================================================ market readiness
def market_readiness(conn, scope):
    domains = pick_domains(scope, LIVESTOCK)
    as_of = scope.as_of or latest_log_date(conn, domains)
    if as_of is None:
        return Result("market_readiness", "not_available", scope, "batches", message="No batch records.")
    horizon = as_of + dt.timedelta(days=30)
    rows = []
    for d in domains:
        meta = LOGS[d]
        for r in rows_of(conn, f"SELECT batch_code, {meta['target']} AS target, status FROM {meta['batches']} "
                               f"WHERE {meta['target']} IS NOT NULL"):
            if r["status"] in INACTIVE_BATCH_STATUSES:
                continue                                  # only active batches can be ready or overdue
            days = (r["target"] - as_of).days
            if r["target"] < as_of:
                state = "overdue"
            elif r["target"] <= horizon:
                state = "due_soon"
            else:
                continue
            rows.append({"batch_code": r["batch_code"], "domain": d, "label": label(d), "target_date": r["target"],
                         "days_to_target": days, "state": state, "status": r["status"]})
    rows.sort(key=lambda r: r["days_to_target"])
    return Result("market_readiness", "ok", scope, "batches",
                  {"as_of": as_of, "overdue": sum(r["state"] == "overdue" for r in rows),
                   "due_soon": sum(r["state"] == "due_soon" for r in rows)}, rows, Coverage(),
                  ["Only active batches (not sold or closed) are listed; 'due soon' means within 30 days."])


register(Metric(
    id="market_readiness", title="batches", group="operations",
    definition="Active batches (not Sold, not Closed) whose target date has passed (overdue) or falls within 30 days (due soon).",
    sources=("pig_batches", "poultry_batches", "pig_daily_log", "poultry_daily_log"), unit="batches", decimals=0,
    period="snapshot", domains=LIVESTOCK, zero_tolerance=False,
    answers="Which batches are ready to sell, due or overdue for market or off-take.",
    does_not_answer="Market prices or buyer demand.",
    compute=market_readiness, eval_oracles=("market_ready", "no_overdue"),
    parity_exempt="No dashboard page lists market readiness.",
))


# ============================================================================ health events
def health_events(conn, scope):
    first, last = table_range(conn, "health_log")
    msg, cov = check_period("health events", scope, first, last)
    if msg:
        return no_record("health_events", scope, "events", msg, cov)
    lo, hi = bounds(scope)
    doms = list(scope.domains) if scope.domains else None
    raw = rows_of(conn, """
        SELECT domain, event_type, COUNT(*) AS n, SUM(cost) AS cost FROM health_log
        WHERE date BETWEEN %(lo)s AND %(hi)s AND (%(doms)s::text[] IS NULL OR domain = ANY(%(doms)s))
        GROUP BY domain, event_type ORDER BY domain, event_type""", {"lo": lo, "hi": hi, "doms": doms})
    rows = [{"domain": r["domain"], "label": label(r["domain"]), "event_type": r["event_type"],
             "event_count": r["n"], "total_cost": _f(r["cost"])} for r in raw]
    return Result("health_events", "ok", scope, "events",
                  {"total_events": sum(r["event_count"] for r in rows),
                   "total_cost": _f(sum(r["total_cost"] for r in rows)),
                   "by_event_type": {t: sum(r["event_count"] for r in rows if r["event_type"] == t)
                                     for t in sorted({r["event_type"] for r in rows})}}, rows, cov,
                  ["These are logged treatments, vaccinations and inspections; whether an animal is sick "
                   "right now is not recorded."])


register(Metric(
    id="health_events", title="health events", group="operations",
    definition="Logged health events (treatments, vaccinations, inspections) and their cost in a period, by domain and type.",
    sources=("health_log",), unit="events", decimals=0, period="range", domains=LIVESTOCK, zero_tolerance=False,
    answers="How many treatments or vaccinations, and the vet cost, over a period.",
    does_not_answer="Whether an animal is sick right now (no current-condition status is logged).",
    compute=health_events, eval_oracles=("health",),
    dashboard=("fetch_health_summary", "fetch_domain_summary"),
))


# ============================================================================ weather
def weather(conn, scope):
    first, last = table_range(conn, "weather_log")
    if scope.start or scope.end:
        msg, cov = check_period("weather", scope, first, last)
        if msg:
            return no_record("weather", scope, "mm", msg, cov)
        lo, hi = bounds(scope)
        r = rows_of(conn, """SELECT COALESCE(SUM(rainfall_mm), 0) AS rain, AVG(temp_min_c) AS tmin,
            AVG(temp_max_c) AS tmax, AVG(humidity_pct) AS hum, COUNT(*) AS days FROM weather_log
            WHERE date BETWEEN %(lo)s AND %(hi)s""", {"lo": lo, "hi": hi})[0]
        return Result("weather", "ok", scope, "mm",
                      {"rainfall_total_mm": _f(r["rain"], 1), "avg_temp_min_c": _f(r["tmin"], 1) if r["tmin"] is not None else None,
                       "avg_temp_max_c": _f(r["tmax"], 1) if r["tmax"] is not None else None,
                       "avg_humidity_pct": _f(r["hum"], 1) if r["hum"] is not None else None, "days_logged": r["days"]},
                      [], cov, ["Only past conditions are logged; there is no forecast."])
    as_of = scope.as_of or last
    msg, cov = check_period("weather", scope.with_(start=as_of, end=as_of), first, last)
    if msg:
        return no_record("weather", scope, "mm", msg, cov)
    r = rows_of(conn, """SELECT date, rainfall_mm, temp_min_c, temp_max_c, humidity_pct, event FROM weather_log
        WHERE date <= %(as_of)s ORDER BY date DESC LIMIT 1""", {"as_of": as_of})[0]
    return Result("weather", "ok", scope, "mm",
                  {"date": r["date"], "rainfall_mm": _f(r["rainfall_mm"], 1), "temp_min_c": _f(r["temp_min_c"], 1),
                   "temp_max_c": _f(r["temp_max_c"], 1), "humidity_pct": _f(r["humidity_pct"], 1), "event": r["event"]},
                  [], cov, ["Only past conditions are logged; there is no forecast."])


register(Metric(
    id="weather", title="weather", group="operations",
    definition="The latest logged day's conditions, or rainfall and average temperatures over a period. Historical only.",
    sources=("weather_log",), unit="mm", decimals=1, period="range", domains=(), zero_tolerance=False,
    answers="What the weather is or was on the latest logged day (today's weather), or how much rain fell in a period.",
    does_not_answer="A forecast.",
    compute=weather, eval_oracles=("weather_latest", "rainfall_total"), snapshot_default=True,
    parity_exempt="No dashboard page shows weather.",
))
