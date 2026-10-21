"""
Dev cases added to reach the minimums Sylvester set (plan section 25.2): 8 per zero-tolerance metric (money, headcount), 4 per other metric,
5 per refusal class that is new in step 6. Drafted 2026-10-20, APPROVED by Sylvester the same day (dca05: the "Feed cost per animal" label
is a valid answer; dfo04: a clarification is accepted as well as the refusal). They are appended to evals.cases_dev.CASES and their gold specs
to evals.case_specs.SPECS. Expected figures come from the independent oracle. The questions were written before the router was run on them.
All `split="dev"`; nothing here is locked.
"""

import datetime as dt

from evals.cases import Case
from evals.oracle import month_bounds as M
from registry import Scope

APR, AUG, JUN, MAR, SEP = M(2026, 4), M(2026, 8), M(2026, 6), M(2026, 3), M(2026, 9)
Q2 = (dt.date(2026, 4, 1), dt.date(2026, 6, 30))

C = Case
P, C_ = ("piggery",), ("poultry",)


def S(metric, **kw):
    return metric, Scope(**kw)


_NOT_DENIED_STAFF = [r"(?:isn't|aren't|not|n't)\s+(?:recorded|tracked|logged)[^.]{0,60}\b(?:staff|employees?|workers?)\b"]
_NOT_DENIED_CROPS = [r"(?:isn't|aren't|not|n't)\s+(?:recorded|tracked|logged)[^.]{0,60}\b(?:scout\w*|pests?|crops?|fields?)\b"]
_NOT_DENIED_FIELDS = [r"(?:isn't|aren't|not|n't)\s+(?:recorded|tracked|logged)[^.]{0,60}\b(?:irrigat\w*|spray\w*|operations?|fields?)\b"]

ROUND2 = [
    # ------------------------------------------------------------ feed purchases (6 -> 8)
    C("dfp01", "Show me the feed purchases for poultry in March 2026", "answer",
      ("feed_purchases", dict(domain="poultry", start=MAR[0], end=MAR[1])), "money", "v2_only", review="domain + month"),
    C("dfp02", "How much was spent on feed purchases in Q2 2026?", "answer",
      ("feed_purchases", dict(start=Q2[0], end=Q2[1])), "money", "v2_only", review="quarter wording"),
    # ------------------------------------------------------------ profit (6 -> 8)
    C("dpf01", "Did the farm make a loss in March 2026?", "answer", ("profit", dict(start=MAR[0], end=MAR[1])), "money", "v2_only",
      review="yes/no wording; the answer must state profit or loss with the figure"),
    C("dpf02", "What was the poultry profit in June 2026?", "answer", ("profit", dict(domain="poultry", start=JUN[0], end=JUN[1])), "money",
      "v2_only", review="domain + month"),
    # ------------------------------------------------------------ feed cost per animal (3 -> 8)
    C("dca01", "What was the feed cost per pig in August 2026?", "answer",
      ("feed_cost_per_animal", dict(domain="piggery", start=AUG[0], end=AUG[1])), "money", "v2_only", review="period; the denominator must be stated"),
    C("dca02", "Feed cost per chicken in March 2026", "answer",
      ("feed_cost_per_animal", dict(domain="poultry", start=MAR[0], end=MAR[1])), "money", "v2_only"),
    C("dca03", "Average feed cost per head for the broilers", "answer", ("feed_cost_per_animal", dict(domain="poultry")), "money",
      review="'per head' and 'broilers' wording"),
    C("dca04", "What was the feed cost per animal last month?", "answer", ("feed_cost_per_animal", dict(start=SEP[0], end=SEP[1])), "money",
      "v2_only", review="calendar last month; data stops 15 Sep"),
    C("dca05", "How much does each animal cost us?", "answer", ("feed_cost_per_animal", {}), "money", "v2_only",
      review="Approved: the answer labelled 'Feed cost per animal' is valid (total cost per animal is not defined; the label says what is shown)"),
    # ------------------------------------------------------------ labour (6 -> 8)
    C("dlb01", "Total hours worked in the piggery in September 2026", "answer",
      ("labour", dict(domain="piggery", measure="hours", start=SEP[0], end=SEP[1])), "money", "v2_only"),
    C("dlb02", "What did labour cost the farm in June 2026?", "answer", ("labour", dict(start=JUN[0], end=JUN[1])), "money", "v2_only"),
    # ------------------------------------------------------------ batch count (6 -> 8)
    C("dbc01", "How many broiler batches are active?", "answer", ("batch_count", dict(domain="poultry", which="active")), "headcount"),
    C("dbc02", "How many pig batches are still running?", "answer", ("batch_count", dict(domain="piggery", which="active")), "headcount"),
    # ------------------------------------------------------------ sow count (3 -> 8)
    C("dsw01", "How many sows are open?", "answer", ("sow_count", dict(status="Open")), "headcount", "v2_only"),
    C("dsw02", "How many sows have been served?", "answer", ("sow_count", dict(status="Served")), "headcount", "v2_only"),
    C("dsw03", "Number of sows in the piggery", "answer", ("sow_count", {}), "headcount", "v2_only"),
    C("dsw04", "How many breeding sows do we have right now?", "answer", ("sow_count", {}), "headcount", "v2_only"),
    C("dsw05", "How many sows did we have in March 2026?", "refuse",
      ("refuse", dict(note="only the current sow status is stored; no history. A named refusal that offers the current count, not a made-up past figure")),
      "refusal", "v2_only", zt=True, review="the refuse path for this metric"),
    # ------------------------------------------------------------ other metrics under 4
    C("dfr01", "What is the feed conversion ratio of BRO-P03?", "answer", ("fcr_batch", dict(batch_code="BRO-P03")), "perf"),
    C("dcr01", "What is the total planted area in hectares?", "answer", ("crop_area", {}), "perf"),
    C("dfs01", "How much feed is on hand across the whole farm?", "answer", ("feed_stock", {}), "ops"),
    C("dwx01", "What is the latest weather reading?", "answer", ("weather_latest", {}), "ops"),
    C("dwx02", "Total rainfall in April 2026", "answer", ("rainfall_total", dict(start=APR[0], end=APR[1])), "ops"),

    # ------------------------------------------------------------ refusal class: staff_info (recorded, no metric)
    C("dst01", "How many staff do we have?", "refuse", ("refuse", dict(note="staff are recorded but no metric reads them; the refusal says so", not_claims=_NOT_DENIED_STAFF)), "refusal", "v2_only"),
    C("dst02", "Who works in the piggery?", "refuse", ("refuse", dict(note="staff are recorded but no metric reads them", not_claims=_NOT_DENIED_STAFF)), "refusal", "v2_only"),
    C("dst03", "List the names of all our workers", "refuse", ("refuse", dict(note="staff are recorded but no metric reads them", not_claims=_NOT_DENIED_STAFF)), "refusal", "v2_only"),
    C("dst04", "What roles do our employees have?", "refuse", ("refuse", dict(note="staff are recorded but no metric reads them", not_claims=_NOT_DENIED_STAFF)), "refusal", "v2_only"),
    C("dst05", "Which supervisors do we have on the farm?", "refuse", ("refuse", dict(note="staff are recorded but no metric reads them", not_claims=_NOT_DENIED_STAFF)), "refusal", "v2_only"),
    # ------------------------------------------------------------ refusal class: staff_pay (policy)
    C("dsp01", "What is each worker's salary?", "refuse", ("refuse", dict(note="per-person pay is never shown (policy); total labour cost is offered")), "refusal", "v2_only"),
    C("dsp02", "How much does the piggery supervisor earn?", "refuse", ("refuse", dict(note="per-person pay is never shown (policy)")), "refusal", "v2_only"),
    C("dsp03", "What are the pay rates for our staff?", "refuse", ("refuse", dict(note="per-person pay is never shown (policy)")), "refusal", "v2_only"),
    C("dsp04", "What is the hourly rate we pay our labourers?", "refuse", ("refuse", dict(note="per-person pay is never shown (policy)")), "refusal", "v2_only"),
    C("dsp05", "Show me salary per employee", "refuse", ("refuse", dict(note="per-person pay is never shown (policy)")), "refusal", "v2_only"),
    # ------------------------------------------------------------ refusal class: crop_scouting (recorded, no metric)
    C("dsc01", "Which plots had pests last month?", "refuse", ("refuse", dict(note="scouting is recorded but no metric reads it", not_claims=_NOT_DENIED_CROPS)), "refusal", "v2_only"),
    C("dsc02", "Have we had any aphid problems in the tomatoes?", "refuse", ("refuse", dict(note="scouting is recorded but no metric reads it", not_claims=_NOT_DENIED_CROPS)), "refusal", "v2_only"),
    C("dsc03", "What growth stage is the maize at?", "refuse", ("refuse", dict(note="scouting is recorded but no metric reads it", not_claims=_NOT_DENIED_CROPS)), "refusal", "v2_only"),
    C("dsc04", "Is there a weed infestation in any of the fields?", "refuse", ("refuse", dict(note="scouting is recorded but no metric reads it", not_claims=_NOT_DENIED_CROPS)), "refusal", "v2_only"),
    C("dsc05", "What was the soil moisture in the wheat plot?", "refuse", ("refuse", dict(note="scouting is recorded but no metric reads it", not_claims=_NOT_DENIED_CROPS)), "refusal", "v2_only"),
    # ------------------------------------------------------------ refusal class: field_operations (recorded, no metric)
    C("dfo01", "When was the maize last irrigated?", "refuse", ("refuse", dict(note="field operations are recorded but no metric reads them", not_claims=_NOT_DENIED_FIELDS)), "refusal", "v2_only"),
    C("dfo02", "How many machine hours were used on the tomatoes?", "refuse", ("refuse", dict(note="field operations are recorded but no metric reads them", not_claims=_NOT_DENIED_FIELDS)), "refusal", "v2_only"),
    C("dfo03", "Which fields were sprayed last month?", "refuse", ("refuse", dict(note="field operations are recorded but no metric reads them", not_claims=_NOT_DENIED_FIELDS)), "refusal", "v2_only"),
    C("dfo04", "When did we last apply fertiliser to the maize?", "refuse", ("refuse", dict(note="field operations are recorded but no metric reads them", not_claims=_NOT_DENIED_FIELDS)), "refusal", "v2_only",
      accept_clarify=True, review="Approved: a clarification (fertiliser spend or field operations?) is accepted as well as the refusal"),
    C("dfo05", "What chemicals were applied to the wheat?", "refuse", ("refuse", dict(note="field operations are recorded but no metric reads them", not_claims=_NOT_DENIED_FIELDS)), "refusal", "v2_only"),
]

ROUND2_SPECS = {
    "dfp01": S("feed_purchases", domains=C_, start=MAR[0], end=MAR[1]), "dfp02": S("feed_purchases", start=Q2[0], end=Q2[1]),
    "dpf01": S("profit", start=MAR[0], end=MAR[1]), "dpf02": S("profit", domains=C_, start=JUN[0], end=JUN[1]),
    "dca01": S("feed_cost_per_animal", domains=P, start=AUG[0], end=AUG[1]), "dca02": S("feed_cost_per_animal", domains=C_, start=MAR[0], end=MAR[1]),
    "dca03": S("feed_cost_per_animal", domains=C_), "dca04": S("feed_cost_per_animal", start=SEP[0], end=SEP[1]), "dca05": S("feed_cost_per_animal"),
    "dlb01": S("labour", domains=P, start=SEP[0], end=SEP[1]), "dlb02": S("labour", start=JUN[0], end=JUN[1]),
    "dbc01": S("batch_count", domains=C_), "dbc02": S("batch_count", domains=P),
    "dsw01": S("sow_count"), "dsw02": S("sow_count"), "dsw03": S("sow_count"), "dsw04": S("sow_count"),
    "dfr01": S("fcr", batch_code="BRO-P03"), "dcr01": S("crop_plantings"), "dfs01": S("feed_stock"),
    "dwx01": S("weather"), "dwx02": S("weather", start=APR[0], end=APR[1]),
}

REFUSAL_CLASS = {"dst": "staff_info", "dsp": "staff_pay", "dsc": "crop_scouting", "dfo": "field_operations"}
for _c in ROUND2:
    _c.refusal = REFUSAL_CLASS.get(_c.id[:3], "") if _c.kind == "refuse" else ""
IDS = [c.id for c in ROUND2]
assert len(IDS) == len(set(IDS))


