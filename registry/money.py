"""Money metrics: feed consumed cost, feed purchases, expenses, revenue, profit,
feed cost per animal, receivables, labour cost."""

from decimal import Decimal

from registry.core import (
    ALL_DOMAINS, LIVESTOCK, LOGS, Coverage, Metric, Result, bounds, check_period, label,
    month_label, no_record, one, pick_domains, register, rows_of, table_range, union_range,
)


from registry.core import rnd as _f  # exact half-up rounding


# ============================================================================ feed consumed cost
_FEED_SQL = """
    SELECT l.domain, {month} AS month,
           SUM(l.feed_kg) AS kg,
           SUM(l.feed_kg * p.unit_cost_per_kg) AS cost,
           COUNT(*) FILTER (WHERE p.unit_cost_per_kg IS NULL) AS unpriced
    FROM (SELECT date, 'piggery' AS domain, feed_type, feed_kg FROM pig_daily_log
          UNION ALL
          SELECT date, 'poultry', feed_type, feed_kg FROM poultry_daily_log) l
    LEFT JOIN LATERAL (
        SELECT f.unit_cost_per_kg FROM feed_inventory f
        WHERE f.domain = l.domain AND f.feed_type = l.feed_type AND f.date <= l.date
        ORDER BY f.date DESC LIMIT 1) p ON TRUE
    WHERE l.date BETWEEN %(lo)s AND %(hi)s AND l.domain = ANY(%(domains)s)
    GROUP BY 1, 2
    ORDER BY 2, 1
"""


def feed_consumed_cost(conn, scope):
    domains = pick_domains(scope, LIVESTOCK)
    first, last = union_range(conn, [LOGS[d]["log"] for d in domains])
    msg, cov = check_period("feed consumption", scope, first, last)
    if msg:
        return no_record("feed_consumed_cost", scope, "currency", msg, cov)

    lo, hi = bounds(scope)
    month = "date_trunc('month', l.date)::date" if scope.grain == "month" else "NULL::date"
    raw = rows_of(conn, _FEED_SQL.format(month=month), {"lo": lo, "hi": hi, "domains": list(domains)})
    rows = [{"domain": r["domain"], "label": label(r["domain"]), "month": r["month"] and month_label(r["month"]), "month_start": r["month"],
             "feed_kg": _f(r["kg"], 1), "feed_cost": _f(r["cost"]), "unpriced_rows": r["unpriced"]} for r in raw]
    if scope.grain != "month":
        rows.sort(key=lambda r: -r["feed_cost"])
    total_cost = _f(sum((r["cost"] or Decimal(0)) for r in raw))
    total_kg = _f(sum((r["kg"] or Decimal(0)) for r in raw), 1)
    unpriced = sum(r["unpriced"] for r in raw)

    figures = {"total_cost": total_cost, "total_kg": total_kg}
    notes = []
    if unpriced:
        notes.append(f"{unpriced} feed log rows had no price on file and are not costed.")
    if scope.aggregation == "avg_per_week":
        days = cov.days_covered
        figures["days_covered"] = days
        figures["avg_weekly_cost"] = _f(total_cost / days * 7) if days else None
        notes.append(f"Average per week = total consumed cost {total_cost:,.2f} ÷ {days} days covered × 7.")
    return Result("feed_consumed_cost", "ok", scope, "currency", figures, rows, cov, notes)


register(Metric(
    id="feed_consumed_cost", title="feed consumption", group="money",
    definition=("Feed the animals actually ate, priced: daily-log feed_kg × the most recent "
                "feed_inventory unit_cost_per_kg on or before that day, same domain and feed type. "
                "Average weekly = total ÷ days covered × 7, with the days stated."),
    sources=("pig_daily_log", "poultry_daily_log", "feed_inventory"), unit="currency", decimals=2,
    period="range", domains=LIVESTOCK, zero_tolerance=True,
    answers=("What was spent feeding the animals in a period: totals, per domain, per month, weekly average. A plain "
             "'feed cost' (no word like bought or purchased) means this metric."),
    does_not_answer="What was BOUGHT (that is feed purchases) or stock on hand (feed stock).",
    compute=feed_consumed_cost, aggregations=("total", "avg_per_week"), grains=("month",),
    eval_oracles=("feed_cost", "feed_cost_no_data"),
    dashboard=("fetch_feed_cost_by_domain", "fetch_feed_cost_by_month"),
))


# ============================================================================ feed purchases
def feed_purchases(conn, scope):
    first, last = table_range(conn, "expenses")
    msg, cov = check_period("feed purchases", scope, first, last)
    if msg:
        return no_record("feed_purchases", scope, "currency", msg, cov)
    lo, hi = bounds(scope)
    doms = list(scope.domains) if scope.domains else None
    raw = rows_of(conn, """
        SELECT COALESCE(domain, 'shared') AS domain, SUM(total_cost) AS total
        FROM expenses
        WHERE category = 'Feed' AND date BETWEEN %(lo)s AND %(hi)s
          AND (%(doms)s::text[] IS NULL OR COALESCE(domain, 'shared') = ANY(%(doms)s))
        GROUP BY 1 ORDER BY 2 DESC""", {"lo": lo, "hi": hi, "doms": doms})
    rows = [{"domain": r["domain"], "label": label(r["domain"]), "total": _f(r["total"])} for r in raw]
    return Result("feed_purchases", "ok", scope, "currency",
                  {"total": _f(sum(r["total"] for r in raw))}, rows, cov)


register(Metric(
    id="feed_purchases", title="feed purchases", group="money",
    definition="Money spent buying feed: expenses with category 'Feed', by the date of the expense.",
    sources=("expenses",), unit="currency", decimals=2, period="range", domains=ALL_DOMAINS,
    zero_tolerance=True,
    answers="How much was spent buying feed in a period, by domain.",
    does_not_answer="How much feed the animals ate (feed consumed cost).",
    compute=feed_purchases, eval_oracles=("feed_purchases",),
    dashboard=("fetch_expense_breakdown",),
))


# ============================================================================ expenses
def expenses(conn, scope):
    first, last = table_range(conn, "expenses")
    msg, cov = check_period("expenses", scope, first, last)
    if msg:
        return no_record("expenses", scope, "currency", msg, cov)
    lo, hi = bounds(scope)
    doms = list(scope.domains) if scope.domains else None
    dim = scope.dimension or ("month" if scope.grain == "month" else "domain")
    key = {"domain": "COALESCE(domain, 'shared')", "category": "category", "month": "'all'"}[dim]
    month = "date_trunc('month', date)::date" if scope.grain == "month" else "NULL::date"
    raw = rows_of(conn, f"""
        SELECT {key} AS key, {month} AS month, SUM(total_cost) AS total
        FROM expenses
        WHERE date BETWEEN %(lo)s AND %(hi)s
          AND (%(doms)s::text[] IS NULL OR COALESCE(domain, 'shared') = ANY(%(doms)s))
          AND (%(cat)s::text IS NULL OR category = %(cat)s)
        GROUP BY 1, 2 ORDER BY 2, 3 DESC""", {"lo": lo, "hi": hi, "doms": doms, "cat": scope.category})
    rows = [{"key": r["key"], "label": label(r["key"]) if dim == "domain" else r["key"],
             "month": r["month"] and month_label(r["month"]), "month_start": r["month"],
             "total": _f(r["total"])} for r in raw]
    total = _f(sum((r["total"] or Decimal(0)) for r in raw))
    return Result("expenses", "ok", scope, "currency", {"total": total, "dimension": dim}, rows, cov)


register(Metric(
    id="expenses", title="expenses", group="money",
    definition=("Money spent (expenses.total_cost) in a period, by domain or by category. Unallocated "
                "costs (domain 'shared' or empty) are shown as 'Shared (not allocated)' so the rows "
                "always sum to the total."),
    sources=("expenses",), unit="currency", decimals=2, period="range", domains=ALL_DOMAINS + ("shared",),
    zero_tolerance=True,
    answers="Total spend, spend by domain, spend by category, spend in a month, spend on one category.",
    does_not_answer=("Money owed TO suppliers (accounts payable is not tracked). Feed has its own metrics: what the animals ate "
                     "is feed consumed cost and what was bought is feed purchases, so a feed question is not an expense-category question."),
    compute=expenses, dimensions=("domain", "category"), grains=("month",),
    eval_oracles=("expenses", "expenses_by_domain", "expenses_by_category", "biggest_expense_category"),
    dashboard=("fetch_expense_breakdown", "fetch_expenses_vs_revenue"),
))


# ============================================================================ revenue
def revenue(conn, scope):
    first, last = table_range(conn, "revenue")
    msg, cov = check_period("revenue", scope, first, last)
    if msg:
        return no_record("revenue", scope, "currency", msg, cov)
    lo, hi = bounds(scope)
    doms = list(scope.domains) if scope.domains else None
    dim = None if scope.dimension == "domain" else scope.dimension     # by domain is the default view
    key = {"buyer": "buyer", "product": "product", None: "'all'" if scope.grain == "month" else "domain"}[dim]
    month = "date_trunc('month', date)::date" if scope.grain == "month" else "NULL::date"
    limit = "LIMIT 5" if dim in ("buyer", "product") and scope.grain != "month" else ""
    raw = rows_of(conn, f"""
        SELECT {key} AS key, {month} AS month, SUM(total_amount) AS total
        FROM revenue
        WHERE date BETWEEN %(lo)s AND %(hi)s AND (%(doms)s::text[] IS NULL OR domain = ANY(%(doms)s))
          AND {key} IS NOT NULL
        GROUP BY 1, 2 ORDER BY 2, 3 DESC {limit}""", {"lo": lo, "hi": hi, "doms": doms})
    rows = [{"key": r["key"], "label": label(r["key"]) if dim is None else r["key"],
             "month": r["month"] and month_label(r["month"]), "month_start": r["month"],
             "total": _f(r["total"])} for r in raw]
    total = one(conn, """SELECT COALESCE(SUM(total_amount), 0) FROM revenue
        WHERE date BETWEEN %(lo)s AND %(hi)s AND (%(doms)s::text[] IS NULL OR domain = ANY(%(doms)s))""",
                {"lo": lo, "hi": hi, "doms": doms})
    notes = ["Showing the top 5."] if limit else []
    return Result("revenue", "ok", scope, "currency", {"total": _f(total), "dimension": dim or "domain"},
                  rows, cov, notes)


register(Metric(
    id="revenue", title="revenue", group="money",
    definition="Sales income (revenue.total_amount) in a period, by domain, or the top 5 buyers or products.",
    sources=("revenue",), unit="currency", decimals=2, period="range", domains=ALL_DOMAINS,
    zero_tolerance=True,
    answers="Total sales, sales by domain, biggest buyers, best-selling products, sales in a month.",
    does_not_answer="Profit (needs expenses too); who has not paid (receivables).",
    compute=revenue, dimensions=("buyer", "product"), grains=("month",),
    eval_oracles=("revenue", "top_revenue"), dashboard=("fetch_expenses_vs_revenue",),
))


# ============================================================================ profit
def profit(conn, scope):
    rev_first, rev_last = table_range(conn, "revenue")
    exp_first, exp_last = table_range(conn, "expenses")
    for title, f, l in (("revenue", rev_first, rev_last), ("expenses", exp_first, exp_last)):
        msg, cov = check_period(title, scope, f, l)
        if msg:
            return no_record("profit", scope, "currency", msg + " Profit needs both revenue and expenses.", cov)
    rev = revenue(conn, scope.with_(dimension=None, grain=None))
    exp = expenses(conn, scope.with_(dimension="domain", grain=None, category=None))
    revenue_total, expenses_total = rev.figures["total"], exp.figures["total"]
    notes = []
    if scope.domains:
        notes.append("Costs in 'Shared (not allocated)' are not part of a single domain's profit.")
    else:
        notes.append("Farm-wide profit includes 'Shared (not allocated)' costs.")
    cov = rev.coverage
    cov.partial = cov.partial or exp.coverage.partial
    return Result("profit", "ok", scope, "currency",
                  {"revenue": revenue_total, "expenses": expenses_total,
                   "profit": _f(revenue_total - expenses_total)}, [], cov, notes)


register(Metric(
    id="profit", title="profit", group="money",
    definition="Revenue minus expenses over the same period and the same domains.",
    sources=("revenue", "expenses"), unit="currency", decimals=2, period="range", domains=ALL_DOMAINS,
    zero_tolerance=True,
    answers="Profit or loss for the farm or one domain, over a period.",
    does_not_answer="A profit figure when revenue or expenses have no record for the period.",
    compute=profit, eval_oracles=("profit",),
    dashboard=("fetch_expenses_vs_revenue",),
))


# ============================================================================ feed cost per animal
def feed_cost_per_animal(conn, scope):
    base = feed_consumed_cost(conn, scope.with_(aggregation="total", grain=None))
    if not base.ok:
        return Result("feed_cost_per_animal", base.status, scope, "currency", message=base.message,
                      coverage=base.coverage)
    lo, hi = bounds(scope)
    rows, tot_avg = [], 0.0
    tot_cost = base.figures["total_cost"]          # the unrounded sum, not a sum of rounded rows
    for r in base.rows:
        d = r["domain"]
        t, c = LOGS[d]["log"], LOGS[d]["count"]
        avg, days = conn.execute(
            f"SELECT AVG(day_total), COUNT(*) FROM (SELECT date, SUM({c}) AS day_total FROM {t} "
            f"WHERE date BETWEEN %s AND %s GROUP BY date) s", (lo, hi)).fetchone()
        avg = float(avg) if avg is not None else None
        rows.append({"domain": d, "label": r["label"], "feed_cost": r["feed_cost"],
                     "avg_headcount": _f(avg, 1) if avg else None, "days_logged": days,
                     "cost_per_animal": _f(r["feed_cost"] / avg) if avg else None})
        tot_avg += avg or 0.0
    rows.sort(key=lambda r: -(r["cost_per_animal"] or 0))
    notes = ["Feed cost per animal = feed consumed cost ÷ average headcount (the mean of the daily "
             "headcount over the days logged)."]
    return Result("feed_cost_per_animal", "ok", scope, "currency",
                  {"feed_cost": tot_cost, "avg_headcount": _f(tot_avg, 1),
                   "cost_per_animal": _f(tot_cost / tot_avg) if tot_avg else None},
                  rows, base.coverage, notes)


register(Metric(
    id="feed_cost_per_animal", title="feed consumption", group="money",
    definition=("Feed consumed cost ÷ average headcount, where average headcount is the mean of the daily "
                "total closing headcount over the days logged in the period. The denominator is stated."),
    sources=("pig_daily_log", "poultry_daily_log", "feed_inventory"), unit="currency", decimals=2,
    period="range", domains=LIVESTOCK, zero_tolerance=True,
    answers="Feed cost per pig, per bird, or per animal, over a period.",
    does_not_answer="Total cost per animal including vet, labour and chicks (not defined for launch).",
    compute=feed_cost_per_animal, eval_oracles=("feed_cost_per_animal",),
    dashboard=("fetch_feed_cost_by_domain",),             # the numerator only; no card shows a per-animal figure (see the parity test)
))


# ============================================================================ receivables
def receivables(conn, scope):
    first, last = table_range(conn, "revenue")
    msg, cov = check_period("revenue", scope, first, last)
    if msg:
        return no_record("receivables", scope, "currency", msg, cov)
    lo, hi = bounds(scope)
    doms = list(scope.domains) if scope.domains else None
    params = {"lo": lo, "hi": hi, "doms": doms}
    raw = rows_of(conn, """
        SELECT date, domain, product, buyer, total_amount, batch_ref FROM revenue
        WHERE payment_status = 'Owing' AND date BETWEEN %(lo)s AND %(hi)s
          AND (%(doms)s::text[] IS NULL OR domain = ANY(%(doms)s))
        ORDER BY date""", params)
    rows = [{"date": r["date"], "domain": r["domain"], "label": label(r["domain"]), "product": r["product"],
             "buyer": r["buyer"], "total_amount": _f(r["total_amount"]), "batch_ref": r["batch_ref"]} for r in raw]
    partial = one(conn, """SELECT COUNT(*) FROM revenue WHERE payment_status = 'Partial'
        AND date BETWEEN %(lo)s AND %(hi)s AND (%(doms)s::text[] IS NULL OR domain = ANY(%(doms)s))""", params)
    notes = []
    if partial:
        notes.append(f"{partial} partly-paid sales are not included: the amount still owing is not recorded.")
    return Result("receivables", "ok", scope, "currency",
                  {"total": _f(sum(r["total_amount"] for r in rows)), "count": len(rows)}, rows, cov, notes)


register(Metric(
    id="receivables", title="revenue", group="money",
    definition=("Money customers still owe the farm: sales with payment_status 'Owing', across ALL domains. "
                "Partly-paid sales are flagged, not counted (the part still owing isn't recorded)."),
    sources=("revenue",), unit="currency", decimals=2, period="range", domains=ALL_DOMAINS,
    zero_tolerance=True,
    answers="Who owes the farm money and how much.",
    does_not_answer="Money the farm owes others: accounts payable is not tracked.",
    compute=receivables, eval_oracles=("receivables",), dashboard=("fetch_debtors",),
    uses_filter=False,     # money owed is a balance: the dashboard date filter must not hide older debts
))


# ============================================================================ labour
def labour(conn, scope):
    first, last = table_range(conn, "labour_log")
    msg, cov = check_period("labour", scope, first, last)
    if msg:
        return no_record("labour", scope, "currency", msg, cov)
    lo, hi = bounds(scope)
    doms = list(scope.domains) if scope.domains else None
    raw = rows_of(conn, """
        SELECT COALESCE(domain, 'shared') AS domain, SUM(hours) AS hours, SUM(overtime_hours) AS overtime,
               SUM(labour_cost) AS cost
        FROM labour_log
        WHERE date BETWEEN %(lo)s AND %(hi)s AND (%(doms)s::text[] IS NULL OR COALESCE(domain, 'shared') = ANY(%(doms)s))
        GROUP BY 1 ORDER BY 4 DESC""", {"lo": lo, "hi": hi, "doms": doms})
    rows = [{"domain": r["domain"], "label": label(r["domain"]), "hours": _f(r["hours"], 1),
             "overtime_hours": _f(r["overtime"], 1), "labour_cost": _f(r["cost"])} for r in raw]
    zero = Decimal(0)
    figures = {"hours": _f(sum((r["hours"] or zero) for r in raw), 1),
               "overtime_hours": _f(sum((r["overtime"] or zero) for r in raw), 1),
               "labour_cost": _f(sum((r["cost"] or zero) for r in raw))}
    return Result("labour", "ok", scope, "currency", figures, rows, cov)


register(Metric(
    id="labour", title="labour", group="money",
    definition="Hours, overtime hours and labour cost logged in a period, by domain; unassigned labour is 'Shared (not allocated)'.",
    sources=("labour_log",), unit="currency", decimals=2, period="range", domains=ALL_DOMAINS + ("shared",),
    zero_tolerance=True,
    answers="Labour cost, hours worked and overtime, farm-wide or per domain.",
    does_not_answer="Payroll history or individual pay rates beyond what the labour log records.",
    compute=labour, eval_oracles=("labour",),
    parity_exempt="No dashboard page shows labour.",
))
