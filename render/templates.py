"""
One template per registry metric (plan D5). Each is a plain function that turns a structured Result into lines of text:
no LLM, no free text around a number. Every figure and every row of the result must be read here - the completeness
test (tests/test_render.py) fails if a result field is never touched. Breakdown rows are largest first, except a monthly
series, which is chronological.

A template gets the tracked figures (`fig`), the tracked rows (`rows`) and a context (`c`) holding the currency; it
returns (title_suffix, lines). The layout around it (echoed scope, notes, coverage, hint) is in render/__init__.py.
"""

from render.format import date, join_names, num, pct, plural
from render.tracking import rendered_by_note

TITLES = {
    "feed_consumed_cost": "Feed consumed cost", "feed_purchases": "Feed purchases", "expenses": "Expenses",
    "revenue": "Revenue", "profit": "Profit", "feed_cost_per_animal": "Feed cost per animal",
    "receivables": "Money owed to us", "labour": "Labour", "active_headcount": "Headcount", "batch_count": "Batches",
    "sow_count": "Sows", "mortality": "Mortality", "fcr": "Feed conversion ratio (FCR)", "weight": "Average weight",
    "harvest_yield": "Harvest yield", "breeding": "Breeding", "crop_plantings": "Crops planted",
    "feed_stock": "Feed stock", "market_readiness": "Market readiness", "health_events": "Health events",
    "weather": "Weather",
}
# Metrics whose first line carries no domain ("Weather, ...").
NO_DOMAIN_IN_ECHO = {"weather"}


def _desc(rows, key):
    return sorted(rows, key=lambda r: (-(r[key] or 0), str(r.get("label", ""))))


# ============================================================================ money
def feed_consumed_cost(r, fig, rows, c):
    lines = []
    if "avg_weekly_cost" in r.figures:
        lines.append(f"Average per week: {c.money(fig['avg_weekly_cost'])}")
        lines.append(f"Total consumed: {c.money(fig['total_cost'])} ({num(fig['total_kg'], 1)} kg)")
        rendered_by_note(r, fig, "days_covered")           # the note states: total ÷ N days covered × 7
    else:
        lines.append(f"Total: {c.money(fig['total_cost'])} ({num(fig['total_kg'], 1)} kg)")
    monthly = any(row.get("month") for row in rows)
    for row in (rows if monthly else _desc(rows, "feed_cost")):
        when = f"{row['month']} " if row["month"] else ""
        unpriced = f" ({plural(row['unpriced_rows'], 'log row')} had no price)" if row["unpriced_rows"] else ""
        lines.append(f"- {when}{row['label']}: {c.money(row['feed_cost'])} ({num(row['feed_kg'], 1)} kg){unpriced}")
    return "", lines


def feed_purchases(r, fig, rows, c):
    lines = [f"Total: {c.money(fig['total'])}"]
    lines += [f"- {row['label']}: {c.money(row['total'])}" for row in _desc(rows, "total")]
    return "", lines


def expenses(r, fig, rows, c):
    suffix = {"domain": " by domain", "category": " by category", "month": " by month"}.get(fig["dimension"], "")
    lines = [f"Total: {c.money(fig['total'])}"]
    monthly = any(row.get("month") for row in rows)
    for row in (rows if monthly else _desc(rows, "total")):
        _ = row["key"]
        name = row["label"]
        lines.append(f"- {row['month'] or name}: {c.money(row['total'])}")
    return suffix, lines


def revenue(r, fig, rows, c):
    suffix = {"buyer": " by buyer", "product": " by product", "month": " by month"}.get(fig["dimension"], "")
    lines = [f"Total: {c.money(fig['total'])}"]
    monthly = any(row.get("month") for row in rows)
    for row in (rows if monthly else _desc(rows, "total")):
        _ = row["key"]
        name = row["label"]
        lines.append(f"- {row['month'] or name}: {c.money(row['total'])}")
    return suffix, lines


def profit(r, fig, rows, c):
    p = fig["profit"]
    return "", [f"{'Profit' if p >= 0 else 'Loss'}: {c.money(p)}",
                f"- Revenue: {c.money(fig['revenue'])}", f"- Expenses: {c.money(fig['expenses'])}"]


def feed_cost_per_animal(r, fig, rows, c):
    lines = [f"Feed cost per animal: {c.money(fig['cost_per_animal'])} (feed consumed {c.money(fig['feed_cost'])} "
             f"÷ average headcount {num(fig['avg_headcount'], 1)})"]
    for row in _desc(rows, "cost_per_animal"):
        lines.append(f"- {row['label']}: {c.money(row['cost_per_animal'])} per animal (feed {c.money(row['feed_cost'])} "
                     f"÷ average headcount {num(row['avg_headcount'], 1)}, {plural(row['days_logged'], 'day')} logged)")
    return "", lines


def receivables(r, fig, rows, c):
    if not rows:
        return "", [f"Nobody owes us money ({plural(fig['count'], 'sale')} owing, total {c.money(fig['total'])})."]
    lines = [f"Total owed: {c.money(fig['total'])} ({plural(fig['count'], 'sale')} owing)"]
    for row in _desc(rows, "total_amount"):
        lines.append(f"- {row['buyer']}: {c.money(row['total_amount'])} ({row['product']}, {row['label']}, "
                     f"sold {date(row['date'])}, batch {row['batch_ref'] or 'not recorded'})")
    return "", lines


def labour(r, fig, rows, c):
    lines = [f"Labour cost: {c.money(fig['labour_cost'])} ({num(fig['hours'], 1)} hours, "
             f"{num(fig['overtime_hours'], 1)} overtime hours)"]
    for row in _desc(rows, "labour_cost"):
        lines.append(f"- {row['label']}: {c.money(row['labour_cost'])} ({num(row['hours'], 1)} hours, "
                     f"{num(row['overtime_hours'], 1)} overtime)")
    return "", lines


# ============================================================================ headcount
def active_headcount(r, fig, rows, c):
    lines = [f"Total: {plural(fig['total'], 'animal')}"]
    lines += [f"- {row['label']}: {num(row['headcount'])}" for row in _desc(rows, "headcount")]
    return "", lines


def batch_count(r, fig, rows, c):
    lines = [f"{plural(fig['total'], 'batch', 'batches')} in total, {num(fig['active'])} active ({num(fig['sold'])} sold)"]
    for row in rows:
        lines.append(f"- {row['label']}: {plural(row['total'], 'batch', 'batches')} in total, {num(row['active'])} active "
                     f"({num(row['sold'])} sold, {num(row['closed'])} closed)")
    return "", lines


def sow_count(r, fig, rows, c):
    split = ", ".join(f"{num(n)} {s.lower()}" for s, n in fig["by_status"].items())
    lines = [f"{plural(fig['total'], 'sow')} on the farm ({split})"]
    if fig["culled"]:
        lines.append(f"{plural(fig['culled'], 'culled sow')} not counted.")
    lines += [f"- {row['status']}: {num(row['count'])}" for row in rows]
    return "", lines


def mortality(r, fig, rows, c):
    if "worst_batch" in r.figures:
        lines = [f"Highest: {fig['worst_batch']} at {pct(fig['worst_rate_pct'])}"]
        for row in rows:
            lines.append(f"- {row['batch_code']} ({row['label']}): {pct(row['rate_pct'])} "
                         f"({plural(row['deaths'], 'death')} of {num(row['at_risk'])} placed)")
        return " by batch", lines
    if rows and "month" in r.rows[0]:
        lines = [f"Deaths: {num(fig['deaths'])}"]
        lines += [f"- {row['month']} {row['label']}: {plural(row['deaths'], 'death')}" for row in rows]
        return " by month", lines
    if "opening" not in r.figures:                                    # a single batch
        row = rows[0]
        return "", [f"{row['batch_code']}: {pct(fig['rate_pct'])} ({plural(fig['deaths'], 'death')} of "
                    f"{num(fig['at_risk'])} placed)",
                    f"- {row['label']}: {plural(row['deaths'], 'death')} of {num(row['at_risk'])} placed ({pct(row['rate_pct'])})"]
    lines = [f"Mortality rate: {pct(fig['rate_pct'])} ({plural(fig['deaths'], 'death')} of {num(fig['at_risk'])} animals at risk)"]
    rendered_by_note(r, fig, "opening", "additions")       # the note states: N at the start + M added = at risk
    for row in _desc(rows, "deaths"):
        lines.append(f"- {row['label']}: {pct(row['rate_pct'])} ({plural(row['deaths'], 'death')} ÷ {num(row['at_risk'])}: "
                     f"{num(row['opening'])} at the start + {num(row['additions'])} added)")
    return "", lines


# ============================================================================ performance
def fcr(r, fig, rows, c):
    lines = [f"Best: {fig['best_batch']} at {num(fig['best_fcr'], 2)}; worst: {fig['worst_batch']} at "
             f"{num(fig['worst_fcr'], 2)} (lower is better)"]
    for row in rows:
        reason = row["reason"]
        if row["fcr"] is None:
            lines.append(f"- {row['batch_code']} ({row['label']}): not available, {reason} "
                         f"({num(row['samples'])} sample(s))")
        else:
            lines.append(f"- {row['batch_code']} ({row['label']}): {num(row['fcr'], 2)} (feed {num(row['feed_kg'], 1)} kg ÷ "
                         f"gain {num(row['gain_kg'], 1)} kg, {date(row['from'])} to {date(row['to'])}, "
                         f"{num(row['samples'])} samples)")
    return "", lines


def weight(r, fig, rows, c):
    lines = [f"Latest sample on or before {date(fig['as_of'])}:"]
    for row in rows:
        state = "" if row["active"] else " (batch no longer on the farm)"
        lines.append(f"- {row['batch_code']} ({row['label']}): {num(row['avg_weight'], 1)} {row['unit']}, "
                     f"sampled {date(row['date'])}{state}")
    return "", lines


def harvest_yield(r, fig, rows, c):
    lines = [f"Total harvested: {num(fig['total_harvested_kg'], 1)} kg (field loss {num(fig['total_field_loss_kg'], 1)} kg)"]
    if fig["best_plot"]:
        lines.append(f"Best: plot {fig['best_plot']} at {num(fig['best_yield_kg_per_ha'], 1)} kg/ha; worst: plot "
                     f"{fig['worst_plot']} at {num(fig['worst_yield_kg_per_ha'], 1)} kg/ha")
    for row in _desc(rows, "yield_kg_per_ha"):
        lines.append(f"- Plot {row['plot_code']}, {row['crop']} ({row['planting_code']}): "
                     f"{num(row['yield_kg_per_ha'], 1)} kg/ha ({num(row['harvested_kg'], 1)} kg from {num(row['area_ha'], 2)} ha; "
                     f"field loss {num(row['field_loss_kg'], 1)} kg)")
    return "", lines


def breeding(r, fig, rows, c):
    lines = [f"{plural(fig['litters'], 'litter')}: {num(fig['born_alive'])} born alive, {num(fig['weaned'])} weaned, "
             f"average litter size {num(fig['avg_litter_size'], 1)}"]
    if fig["best_sow"]:
        lines.append(f"Best litter: {fig['best_sow']} with {num(fig['best_sow_born_alive'])} born alive")
    for row in rows:
        farrowed = f"farrowed {date(row['farrow_date'])}" if row["farrow_date"] else "not yet farrowed"
        lines.append(f"- {row['sow_tag']}: served {date(row['service_date'])}, {farrowed}, {num(row['born_alive'])} born alive, "
                     f"{num(row['stillborn'])} stillborn, {num(row['weaned_count'])} weaned")
    return "", lines


def crop_plantings(r, fig, rows, c):
    return "", [f"Area planted: {num(fig['total_area_ha'], 2)} ha across {plural(fig['plot_count'], 'plot')} "
                f"({plural(fig['planting_count'], 'planting')}, {num(fig['active_planting_count'])} still active)",
                f"Crops: {join_names(fig['crops']) if fig['crops'] else 'none recorded'}"]


# ============================================================================ operations
def feed_stock(r, fig, rows, c):
    per = ", ".join(f"{d.title()} {num(v, 1)} kg" for d, v in fig["by_domain"].items())
    lines = [f"Total on hand: {num(fig['total_kg'], 1)} kg ({per})"]
    for row in sorted(rows, key=lambda x: (x["label"], -(x["closing_kg"] or 0))):
        lines.append(f"- {row['label']}, {row['feed_type']}: {num(row['closing_kg'], 1)} kg (counted {date(row['date'])})")
    return "", lines


def market_readiness(r, fig, rows, c):
    if not rows:
        return "", [f"No active batch is overdue or due within 30 days (overdue {num(fig['overdue'])}, "
                    f"due soon {num(fig['due_soon'])})."]
    lines = [f"{num(fig['overdue'])} overdue, {num(fig['due_soon'])} due within 30 days"]
    for row in rows:
        when = (f"{abs(row['days_to_target'])} days overdue" if row["state"] == "overdue"
                else ("due today" if row["days_to_target"] == 0 else f"due in {row['days_to_target']} days"))
        lines.append(f"- {row['batch_code']} ({row['label']}, {row['status']}): target {date(row['target_date'])}, {when}")
    return "", lines


def health_events(r, fig, rows, c):
    types = ", ".join(f"{num(n)} {t.lower()}{'s' if n != 1 else ''}" for t, n in fig["by_event_type"].items())
    lines = [f"{plural(fig['total_events'], 'event')}, costing {c.money(fig['total_cost'])}" + (f" ({types})" if types else "")]
    for row in sorted(rows, key=lambda x: (x["label"], x["event_type"])):
        lines.append(f"- {row['label']}, {row['event_type']}: {plural(row['event_count'], 'event')}, "
                     f"{c.money(row['total_cost'])}")
    return "", lines


def weather(r, fig, rows, c):
    if "rainfall_total_mm" in r.figures:
        return "", [f"Rainfall: {num(fig['rainfall_total_mm'], 1)} mm over {plural(fig['days_logged'], 'logged day')}",
                    f"Average temperature: {num(fig['avg_temp_min_c'], 1)}°C to {num(fig['avg_temp_max_c'], 1)}°C; "
                    f"average humidity {num(fig['avg_humidity_pct'], 1)}%"]
    return "", [f"{date(fig['date'])}: rainfall {num(fig['rainfall_mm'], 1)} mm, temperature {num(fig['temp_min_c'], 1)}°C to "
                f"{num(fig['temp_max_c'], 1)}°C, humidity {num(fig['humidity_pct'], 1)}%, conditions: "
                f"{fig['event'] or 'not recorded'}"]


TEMPLATES = {f.__name__: f for f in (
    feed_consumed_cost, feed_purchases, expenses, revenue, profit, feed_cost_per_animal, receivables, labour,
    active_headcount, batch_count, sow_count, mortality, fcr, weight, harvest_yield, breeding, crop_plantings,
    feed_stock, market_readiness, health_events, weather)}
