"""Headcount metrics: active headcount, batch count, mortality."""

import datetime as dt
from decimal import Decimal

from registry.core import (
    INACTIVE_BATCH_STATUSES, LIVESTOCK, rnd, LOGS, Coverage, Metric, Result, bounds, check_period, label,
    latest_log_date, month_label, no_record, one, pick_domains, register, rows_of, table_range, union_range,
)

# ============================================================================ active headcount
_ACTIVE_SQL = """
    WITH batch_range AS (
        SELECT batch_code, MIN(date) AS first_date, MAX(date) AS last_date FROM {log} GROUP BY batch_code
    ),
    active AS (
        SELECT batch_code FROM batch_range WHERE first_date <= %(cutoff)s AND last_date >= %(cutoff)s
    ),
    latest AS (
        SELECT DISTINCT ON (batch_code) batch_code, {count} AS headcount FROM {log}
        WHERE date <= %(cutoff)s ORDER BY batch_code, date DESC
    )
    SELECT COALESCE(SUM(l.headcount), 0) FROM active a JOIN latest l ON l.batch_code = a.batch_code
"""


def headcount_asof(conn, domain, cutoff):
    """Animals on the farm for one domain as of `cutoff`: batches with daily-log rows both on or before
    and on or after the cutoff, at their latest count on or before it. There is no historical status
    log, so today's status column can't say whether a batch was active on a past date."""
    meta = LOGS[domain]
    return int(one(conn, _ACTIVE_SQL.format(log=meta["log"], count=meta["count"]), {"cutoff": cutoff}))


def active_headcount(conn, scope):
    domains = pick_domains(scope, LIVESTOCK)
    first, last = union_range(conn, [LOGS[d]["log"] for d in domains])
    as_of = scope.as_of or last
    snap = scope.with_(start=as_of, end=as_of)
    msg, cov = check_period("headcount", snap, first, last)
    if msg:
        return no_record("active_headcount", scope, "animals", msg, cov)
    rows = [{"domain": d, "label": label(d), "headcount": headcount_asof(conn, d, as_of)} for d in domains]
    rows.sort(key=lambda r: -r["headcount"])
    return Result("active_headcount", "ok", scope, "animals",
                  {"as_of": as_of, "total": sum(r["headcount"] for r in rows)}, rows, cov)


register(Metric(
    id="active_headcount", title="headcount", group="headcount",
    definition=("Animals on the farm as of a date (default: the latest logged date): the latest closing count "
                "of every batch with daily-log rows on both sides of that date. Per-domain counts are always shown."),
    sources=("pig_daily_log", "poultry_daily_log"), unit="animals", decimals=0, period="snapshot",
    domains=LIVESTOCK, zero_tolerance=True,
    answers="How many pigs, chickens or animals are on the farm now, per section or combined (or on a past date).",
    does_not_answer="Headcount by class (sows, growers, layers): the logs have no class field.",
    compute=active_headcount, eval_oracles=("headcount", "headcount_total"),
    dashboard=("fetch_dashboard_stats", "fetch_domain_summary"),
))


# ============================================================================ batch count
def batch_count(conn, scope):
    domains = pick_domains(scope, LIVESTOCK)
    rows = []
    for d in domains:
        t = LOGS[d]["batches"]
        counts = rows_of(conn, f"SELECT status, COUNT(*) AS n FROM {t} GROUP BY status")
        by_status = {r["status"]: r["n"] for r in counts}
        total = sum(by_status.values())
        active = sum(n for s, n in by_status.items() if s not in INACTIVE_BATCH_STATUSES)
        rows.append({"domain": d, "label": label(d), "total": total, "active": active,
                     "sold": by_status.get("Sold", 0), "closed": by_status.get("Closed", 0)})
    figures = {"total": sum(r["total"] for r in rows), "active": sum(r["active"] for r in rows),
               "sold": sum(r["sold"] for r in rows)}
    return Result("batch_count", "ok", scope, "batches", figures, rows, Coverage(),
                  ["Active means the batch has not been sold or closed."])


register(Metric(
    id="batch_count", title="batches", group="headcount",
    definition="Batches recorded, always as 'N batches in total, M active'; active = not Sold and not Closed.",
    sources=("pig_batches", "poultry_batches"), unit="batches", decimals=0, period="none",
    domains=LIVESTOCK, zero_tolerance=True,
    answers="How many batches the farm has or has had, how many are active and how many were sold or closed, per domain.",
    does_not_answer="Which batches are ready to sell (market readiness).",
    compute=batch_count, eval_oracles=("batch_count",),
    dashboard=("fetch_data_coverage",),
))


# ============================================================================ mortality
def _opening(conn, meta, start):
    """Animals present when the period starts: batches placed before `start` that still have daily-log
    rows on or after it, at their last count before it."""
    return int(one(conn, f"""
        SELECT COALESCE(SUM(c.cnt), 0) FROM (
            SELECT DISTINCT ON (l.batch_code) l.batch_code, l.{meta['count']} AS cnt
            FROM {meta['log']} l
            WHERE l.date < %(start)s
              AND l.batch_code IN (SELECT batch_code FROM {meta['log']} GROUP BY batch_code HAVING MAX(date) >= %(start)s)
            ORDER BY l.batch_code, l.date DESC) c""", {"start": start}))


def mortality(conn, scope):
    domains = pick_domains(scope, LIVESTOCK)
    first, last = union_range(conn, [LOGS[d]["log"] for d in domains])
    msg, cov = check_period("deaths", scope, first, last)
    if msg:
        return no_record("mortality", scope, "%", msg, cov)
    lo, hi = bounds(scope)

    if scope.batch_code and scope.grain != "month":     # a NAMED batch leads: its own figure, never a ranking of all batches (whatever dimension was added)
        for d in LIVESTOCK:
            meta = LOGS[d]
            row = conn.execute(f"SELECT {meta['placed']} FROM {meta['batches']} WHERE batch_code = %s",
                               (scope.batch_code,)).fetchone()
            if row:
                deaths = int(one(conn, f"SELECT COALESCE(SUM(deaths), 0) FROM {meta['log']} "
                                       f"WHERE batch_code = %(b)s AND date BETWEEN %(lo)s AND %(hi)s",
                                 {"b": scope.batch_code, "lo": lo, "hi": hi}))
                placed = int(row[0])
                rate = rnd(Decimal(deaths) / Decimal(placed) * 100, 2) if placed else None
                return Result("mortality", "ok", scope, "%",
                              {"deaths": deaths, "at_risk": placed, "rate_pct": rate},
                              [{"domain": d, "label": label(d), "batch_code": scope.batch_code, "deaths": deaths,
                                "at_risk": placed, "rate_pct": rate}], cov,
                              [f"Mortality = deaths ÷ animals placed ({placed:,})."])
        return Result("mortality", "not_available", scope, "%", coverage=cov,
                      message=f"There is no batch {scope.batch_code} on record.")

    if scope.grain == "month":
        rows = []
        for d in domains:
            for r in rows_of(conn, f"""SELECT date_trunc('month', date)::date AS month, SUM(deaths) AS deaths
                FROM {LOGS[d]['log']} WHERE date BETWEEN %(lo)s AND %(hi)s
                AND (%(b)s::text IS NULL OR batch_code = %(b)s) GROUP BY 1 ORDER BY 1""",
                             {"lo": lo, "hi": hi, "b": scope.batch_code}):
                rows.append({"domain": d, "label": label(d), "month": month_label(r["month"]),
                             "month_start": r["month"], "deaths": int(r["deaths"] or 0)})
        return Result("mortality", "ok", scope, "%", {"deaths": sum(r["deaths"] for r in rows)}, rows, cov,
                      ["Monthly view shows deaths only."])

    if scope.dimension == "batch":
        rows = []
        for d in domains:
            meta = LOGS[d]
            for r in rows_of(conn, f"""
                    SELECT b.batch_code, b.{meta['placed']} AS placed, COALESCE(SUM(l.deaths), 0) AS deaths
                    FROM {meta['batches']} b
                    LEFT JOIN {meta['log']} l ON l.batch_code = b.batch_code AND l.date BETWEEN %(lo)s AND %(hi)s
                    GROUP BY b.batch_code, b.{meta['placed']}""", {"lo": lo, "hi": hi}):
                placed = int(r["placed"] or 0)
                rows.append({"batch_code": r["batch_code"], "domain": d, "label": label(d), "deaths": int(r["deaths"]),
                             "at_risk": placed,
                             "rate_pct": rnd(Decimal(int(r["deaths"])) / Decimal(placed) * 100, 2) if placed else None})
        rows.sort(key=lambda r: (-(r["rate_pct"] or 0), r["batch_code"]))
        worst = rows[0] if rows else None
        return Result("mortality", "ok", scope, "%",
                      {"worst_batch": worst["batch_code"] if worst else None,
                       "worst_rate_pct": worst["rate_pct"] if worst else None}, rows, cov,
                      ["Batch mortality = deaths ÷ animals placed."])

    rows = []
    for d in domains:
        meta = LOGS[d]
        deaths = int(one(conn, f"SELECT COALESCE(SUM(deaths), 0) FROM {meta['log']} "
                               f"WHERE date BETWEEN %(lo)s AND %(hi)s", {"lo": lo, "hi": hi}))
        opening = _opening(conn, meta, scope.start) if scope.start else 0
        added = int(one(conn, f"SELECT COALESCE(SUM({meta['placed']}), 0) FROM {meta['batches']} "
                              f"WHERE {meta['start']} BETWEEN %(lo)s AND %(hi)s", {"lo": lo, "hi": hi}))
        at_risk = opening + added
        rows.append({"domain": d, "label": label(d), "deaths": deaths, "opening": opening, "additions": added,
                     "at_risk": at_risk, "rate_pct": rnd(Decimal(deaths) / Decimal(at_risk) * 100, 2) if at_risk else None})
    deaths = sum(r["deaths"] for r in rows)
    opening = sum(r["opening"] for r in rows)
    added = sum(r["additions"] for r in rows)
    at_risk = opening + added
    rate = rnd(Decimal(deaths) / Decimal(at_risk) * 100, 2) if at_risk else None
    rows.sort(key=lambda r: -r["deaths"])
    return Result("mortality", "ok", scope, "%",
                  {"deaths": deaths, "opening": opening, "additions": added, "at_risk": at_risk, "rate_pct": rate},
                  rows, cov,
                  [f"Mortality = deaths ÷ animals at risk ({opening:,} at the start of the period + "
                   f"{added:,} added = {at_risk:,})."])


register(Metric(
    id="mortality", title="deaths", group="headcount",
    definition=("Deaths in a period ÷ animals at risk. For a period: the headcount at its start plus animals "
                "added during it. For a batch: deaths ÷ animals placed. The denominator is stated in every answer."),
    sources=("pig_daily_log", "poultry_daily_log", "pig_batches", "poultry_batches"), unit="%", decimals=2,
    period="range", domains=LIVESTOCK, zero_tolerance=True,
    answers="How many animals died and the mortality rate, farm-wide, per domain, per batch or per month.",
    does_not_answer="Cause of death.",
    compute=mortality, dimensions=("batch",), grains=("month",), batch_filter=True, eval_oracles=("deaths", "batch_deaths", "worst_poultry_mortality_batch", "mortality_rate"),
    dashboard=("fetch_dashboard_stats", "fetch_mortality_by_month", "fetch_findings"),
))


# ============================================================================ sow count
def sow_count(conn, scope):
    """Sows on the farm and their status split, from sow_register. The register holds each sow's CURRENT status only
    (Open, Served, Pregnant, Lactating, Culled): there is no history, so this is always 'now'."""
    raw = rows_of(conn, "SELECT status, COUNT(*) AS n FROM sow_register GROUP BY status ORDER BY n DESC, status")
    if not raw:
        return Result("sow_count", "not_available", scope, "sows", message="No sows are recorded in the sow register.")
    rows = [{"status": r["status"], "count": int(r["n"])} for r in raw]
    culled = sum(r["count"] for r in rows if r["status"] == "Culled")
    on_farm = [r for r in rows if r["status"] != "Culled"]
    return Result("sow_count", "ok", scope, "sows",
                  {"total": sum(r["count"] for r in on_farm), "culled": culled,
                   "by_status": {r["status"]: r["count"] for r in on_farm}},
                  on_farm, Coverage(),
                  ["Sows on the farm exclude culled sows. Status is each sow's current status; no history is kept."])


register(Metric(
    id="sow_count", title="sows", group="headcount",
    definition=("Sows on the farm (sow_register, not culled) with the split by current status: Open, Served, "
                "Pregnant, Lactating. Sows are not part of the batch headcount."),
    sources=("sow_register",), unit="sows", decimals=0, period="none", domains=("piggery",), zero_tolerance=True,
    answers="How many sows there are, and how many are open, served, pregnant or lactating right now.",
    does_not_answer="Sow history or how many there were on a past date (only the current status is stored).",
    compute=sow_count, eval_oracles=("sow_count",),
    parity_exempt="No dashboard page lists sows.",
))
