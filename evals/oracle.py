"""
Independent oracle: computes the golden figures for each eval case with its
own plain SQL against the fixture database. Deliberately imports nothing from
chatbot/ or ui/ - if the oracle and the engine disagree, that is a finding,
not a test to patch (spec-chatbot-v2-plan.md, section 11).

Definitions that are NOT yet owner-approved are not guessed here: such cases
are marked `scored=False` (outputs recorded, excluded from the rates) and are
listed in the review notes.
"""

import calendar
import datetime as dt
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

# The calendar "today" the eval treats as now (Africa/Harare), fixed so the
# expected figures for relative periods ("last month") never drift with the
# real clock. Latest data in the fixture is 2026-09-15.
EVAL_TODAY = dt.date(2026, 10, 15)

DOMAINS = ("piggery", "poultry", "crops")


@dataclass
class Expect:
    required: list = field(default_factory=list)      # every one must appear
    any_of: list = field(default_factory=list)        # [[a, b], ...]: at least one of each group
    forbidden: list = field(default_factory=list)     # none may appear (wrong-scope figures)
    words: list = field(default_factory=list)         # case-insensitive substrings that must appear
    words_any: list = field(default_factory=list)     # at least one must appear
    forbidden_words: list = field(default_factory=list)
    not_claims: list = field(default_factory=list)    # regexes that must NOT match (false "not tracked")
    claim_exempt_words: list = field(default_factory=list)  # a claim that also mentions one of these is not false
    sign_agnostic: bool = False                       # profit/loss: compare absolute values
    scored: bool = True                               # False: record only
    note: str = ""


def month_bounds(year, month):
    return dt.date(year, month, 1), dt.date(year, month, calendar.monthrange(year, month)[1])


def r2(x):
    return hu(x, 2)


def human_date(d):
    """15 Sep 2026: the way answers show dates."""
    return f"{d.day} {d:%b} {d.year}"


def hu(x, nd=2):
    """Round half-up on the exact decimal (never via a binary float)."""
    d = x if isinstance(x, Decimal) else Decimal(str(x or 0))
    return float(d.quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP))


class Oracle:
    def __init__(self, conn):
        self.c = conn

    # --- helpers ----------------------------------------------------------
    def one(self, sql, params=()):
        return self.c.execute(sql, params).fetchone()[0]

    def rows(self, sql, params=()):
        return self.c.execute(sql, params).fetchall()

    @property
    def last_data_date(self):
        return self.one("SELECT GREATEST((SELECT MAX(date) FROM pig_daily_log),"
                        " (SELECT MAX(date) FROM poultry_daily_log))")

    @staticmethod
    def bounds(start, end):
        return (start or dt.date(1900, 1, 1)), (end or dt.date(2999, 1, 1))

    # --- headcount / batches ------------------------------------------------
    def headcount(self, domain=None, as_of=None):
        last = as_of or self.last_data_date
        if as_of:                       # a past date: batches logging on both sides of it, at their latest count on or before it
            totals = {}
            for d, (log, cnt) in {"piggery": ("pig_daily_log", "closing_count"),
                                  "poultry": ("poultry_daily_log", "closing_birds")}.items():
                n = 0
                for code, first, final in self.rows(f"SELECT batch_code, MIN(date), MAX(date) FROM {log} GROUP BY batch_code"):
                    if first <= as_of <= final:
                        n += self.one(f"SELECT {cnt} FROM {log} WHERE batch_code=%s AND date <= %s ORDER BY date DESC LIMIT 1", (code, as_of))
                totals[d] = n
            if domain:
                return Expect(required=[totals[domain]], note=f"as of {as_of}")
            return Expect(required=list(totals.values()), note=f"as of {as_of}")
        last = self.last_data_date
        pig = self.one("SELECT COALESCE(SUM(closing_count),0) FROM pig_daily_log WHERE date=%s", (last,))
        poultry = self.one("SELECT COALESCE(SUM(closing_birds),0) FROM poultry_daily_log WHERE date=%s", (last,))
        if domain == "piggery":
            return Expect(required=[pig], note=f"as of {last}")
        if domain == "poultry":
            return Expect(required=[poultry], note=f"as of {last}")
        return Expect(required=[pig, poultry], note=f"as of {last}; total {pig + poultry}")

    def headcount_total(self):
        e = self.headcount()
        return Expect(any_of=[[sum(e.required)]], note=e.note)

    def batch_count(self, domain, which="both"):
        """Decision 6: the answer always gives both, 'N batches in total, M active'. Active = not Sold and
        not Closed (the status lists in 99_LISTS)."""
        total = active = sold = 0
        for d, t in (("piggery", "pig_batches"), ("poultry", "poultry_batches")):
            if domain in (None, d):
                total += self.one(f"SELECT COUNT(*) FROM {t}")
                active += self.one(f"SELECT COUNT(*) FROM {t} WHERE status NOT IN ('Sold','Closed')")
                sold += self.one(f"SELECT COUNT(*) FROM {t} WHERE status='Sold'")
        if which == "sold":
            return Expect(required=[sold])
        if which == "total":
            return Expect(required=[total])
        if which == "active":
            return Expect(required=[active])
        return Expect(required=[total, active], note="'N batches in total, M active'")

    def sow_count(self, status=None):
        if status:
            return Expect(required=[self.one("SELECT COUNT(*) FROM sow_register WHERE status=%s", (status,))])
        n = self.one("SELECT COUNT(*) FROM sow_register WHERE status <> 'Culled'")
        return Expect(required=[n], note="sows on the farm, not culled; the status split is shown too")

    # --- deaths --------------------------------------------------------------
    def deaths(self, domain=None, start=None, end=None):
        lo, hi = self.bounds(start, end)
        pig = self.one("SELECT COALESCE(SUM(deaths),0) FROM pig_daily_log WHERE date BETWEEN %s AND %s", (lo, hi))
        poultry = self.one("SELECT COALESCE(SUM(deaths),0) FROM poultry_daily_log WHERE date BETWEEN %s AND %s", (lo, hi))
        if domain == "piggery":
            return Expect(required=[pig])
        if domain == "poultry":
            return Expect(required=[poultry])
        return Expect(required=[pig + poultry])

    def batch_deaths(self, batch_code):
        t = "pig_daily_log" if batch_code.startswith("PIG") else "poultry_daily_log"
        # A named batch is answered with its own figure; "Highest:" is the lead of a ranking of every batch (the shadow_log defect, plan 27.3).
        return Expect(required=[self.one(f"SELECT COALESCE(SUM(deaths),0) FROM {t} WHERE batch_code=%s", (batch_code,))],
                      forbidden_words=["Highest:"])

    def worst_poultry_mortality_batch(self):
        row = self.rows(
            "SELECT b.batch_code FROM poultry_batches b JOIN poultry_daily_log d USING(batch_code) "
            "GROUP BY b.batch_code, b.chicks_placed ORDER BY SUM(d.deaths)::numeric / b.chicks_placed DESC LIMIT 1")[0][0]
        return Expect(words=[row])

    # --- mortality rate (decision 1) ------------------------------------------------
    _T = {"piggery": ("pig_daily_log", "closing_count", "pig_batches", "start_count", "start_date"),
          "poultry": ("poultry_daily_log", "closing_birds", "poultry_batches", "chicks_placed", "placement_date")}

    def mortality_rate(self, domain=None, start=None, end=None):
        """Deaths / animals at risk. At risk = headcount when the period starts (batches already on the farm that
        still log on or after the start, at their last count before it) + animals placed during the period."""
        lo, hi = self.bounds(start, end)
        deaths = opening = added = 0
        for d, (log, cnt, bt, placed, startcol) in self._T.items():
            if domain not in (None, d):
                continue
            deaths += self.one(f"SELECT COALESCE(SUM(deaths),0) FROM {log} WHERE date BETWEEN %s AND %s", (lo, hi))
            if start:
                for code, last in self.rows(f"SELECT batch_code, MAX(date) FROM {log} GROUP BY batch_code"):
                    if last >= start:
                        prior = self.rows(f"SELECT {cnt} FROM {log} WHERE batch_code=%s AND date < %s ORDER BY date DESC LIMIT 1", (code, start))
                        opening += prior[0][0] if prior else 0
            added += self.one(f"SELECT COALESCE(SUM({placed}),0) FROM {bt} WHERE {startcol} BETWEEN %s AND %s", (lo, hi))
        at_risk = opening + added
        if not at_risk:
            return Expect(required=[deaths])
        return Expect(required=[hu(Decimal(deaths) / Decimal(at_risk) * 100, 2), at_risk, deaths],
                      note=f"{deaths} deaths / {at_risk} at risk ({opening} opening + {added} added)")

    # --- FCR (decision 3) ---------------------------------------------------------------
    def _fcr_by_batch(self):
        """feed kg / weight gained kg per batch between its first and latest weight sample (a pig batch's starting
        weight counts as its first sample); None where fewer than two samples or no gain."""
        out = {}
        for d, wsql, startsql in (
                ("piggery", "SELECT batch_code, date, avg_weight_kg FROM pig_weights",
                 "SELECT batch_code, start_date, start_avg_kg FROM pig_batches WHERE start_avg_kg IS NOT NULL"),
                ("poultry", "SELECT batch_code, date, avg_weight_g/1000.0 FROM poultry_weights", None)):
            log, cnt = self._T[d][0], self._T[d][1]
            samples = {}
            for code, date, w in self.rows(wsql) + (self.rows(startsql) if startsql else []):
                samples.setdefault(code, []).append((date, float(w)))
            for code in [r[0] for r in self.rows(f"SELECT batch_code FROM {self._T[d][2]}")]:
                pts = sorted(samples.get(code, []))
                out[code] = None
                if len(pts) < 2:
                    continue
                (d0, w0), (d1, w1) = pts[0], pts[-1]
                count = self.one(f"SELECT {cnt} FROM {log} WHERE batch_code=%s AND date <= %s ORDER BY date DESC LIMIT 1", (code, d1))
                feed = self.one(f"SELECT COALESCE(SUM(feed_kg),0) FROM {log} WHERE batch_code=%s AND date > %s AND date <= %s", (code, d0, d1))
                gain = Decimal(str(w1 - w0)) * count
                if gain > 0:
                    out[code] = hu(Decimal(feed) / gain, 2)
        return out

    def fcr_batch(self, batch_code):
        v = self._fcr_by_batch().get(batch_code)
        if v is None:
            return Expect(words_any=["weight"], note="needs two weight samples: a named refusal")
        return Expect(required=[v], words=[batch_code])

    def fcr_best_worst(self, which="worst"):
        vals = {k: v for k, v in self._fcr_by_batch().items() if v is not None}
        code = (max if which == "worst" else min)(vals, key=vals.get)
        return Expect(required=[vals[code]], words=[code])

    # --- crops ------------------------------------------------------------------------------
    def crop_area(self):
        return Expect(required=[r2(self.one("SELECT COALESCE(SUM(area_ha),0) FROM plantings"))])

    def crop_types(self):
        return Expect(words=[r[0] for r in self.rows("SELECT DISTINCT crop FROM plantings WHERE crop IS NOT NULL ORDER BY 1")])

    # --- feed ------------------------------------------------------------------
    _FEED_SQL = """
        SELECT l.domain,
               COALESCE(SUM(l.feed_kg), 0),
               COALESCE(SUM(l.feed_kg * p.unit_cost_per_kg), 0)
        FROM (SELECT date, 'piggery' AS domain, feed_type, feed_kg FROM pig_daily_log
              UNION ALL
              SELECT date, 'poultry', feed_type, feed_kg FROM poultry_daily_log) l
        LEFT JOIN LATERAL (
            SELECT unit_cost_per_kg FROM feed_inventory f
            WHERE f.domain = l.domain AND f.feed_type = l.feed_type AND f.date <= l.date
            ORDER BY f.date DESC LIMIT 1) p ON TRUE
        WHERE l.date BETWEEN %s AND %s
        GROUP BY l.domain
    """

    def feed_consumed(self, start=None, end=None):
        lo, hi = self.bounds(start, end)
        # Exact decimals, never floats: a float sum turned 1717.535 into 1717.53 (half-up gives 1717.54).
        return {d: (Decimal(kg), Decimal(cost)) for d, kg, cost in self.rows(self._FEED_SQL, (lo, hi))}

    def feed_cost(self, domain=None, start=None, end=None, split=False, kg=False, forbid=(), avg_weekly=False):
        by = self.feed_consumed(start, end)
        if not by:
            return Expect(forbidden=list(forbid), note="no feed logged in this period")
        idx = 0 if kg else 1
        if avg_weekly:
            # Decision 2: total consumed cost / days covered x 7, with the days stated.
            first = min(self.one("SELECT MIN(date) FROM pig_daily_log"), self.one("SELECT MIN(date) FROM poultry_daily_log"))
            last = max(self.one("SELECT MAX(date) FROM pig_daily_log"), self.one("SELECT MAX(date) FROM poultry_daily_log"))
            lo, hi = self.bounds(start, end)
            days = (min(hi, last) - max(lo, first)).days + 1
            total = sum(Decimal(str(v[1])) for v in by.values())
            avg = hu(total / Decimal(days) * 7, 2)
            return Expect(required=[avg, days], forbidden=list(forbid), note=f"{total} / {days} days x 7")
        if domain:
            req = [r2(by.get(domain, (0, 0))[idx])]
        elif split:
            req = [r2(v[idx]) for v in by.values()]
        else:
            req = [r2(sum(v[idx] for v in by.values()))]
        return Expect(required=req, forbidden=list(forbid))

    def feed_cost_no_data(self, start, end):
        """Decision 4: a period after the last record says 'No ... recorded for that period; latest record is
        <date>', never a figure."""
        assert not self.feed_consumed(start, end), "case expects no data in this period"
        last = max(self.one("SELECT MAX(date) FROM pig_daily_log"), self.one("SELECT MAX(date) FROM poultry_daily_log"))
        return Expect(words=[human_date(last)], words_any=["recorded", "no "],
                      note="no feed data in this period: must say so and name the latest record date")

    def no_record(self, latest, what="records"):
        return Expect(words=[human_date(latest)], words_any=["recorded", "no "],
                      note=f"no {what} for this period: must say so and name the latest record, {human_date(latest)}")

    def feed_cost_per_animal(self, domain=None, start=None, end=None):
        """Feed consumed cost / average headcount (mean daily total headcount over the days logged in the period)."""
        by = self.feed_consumed(start, end)
        lo, hi = self.bounds(start, end)
        cost, avg = Decimal(0), Decimal(0)
        for d, (log, cnt) in {"piggery": ("pig_daily_log", "closing_count"),
                              "poultry": ("poultry_daily_log", "closing_birds")}.items():
            if domain in (None, d):
                cost += Decimal(str(by.get(d, (0, 0))[1]))
                mean = self.one(f"SELECT AVG(t) FROM (SELECT SUM({cnt}) t FROM {log} WHERE date BETWEEN %s AND %s GROUP BY date) s", (lo, hi))
                avg += Decimal(str(mean or 0))
        return Expect(required=[hu(cost / avg, 2)], note=f"{cost} / avg headcount {avg:.1f}")

    def feed_purchases(self, domain=None, start=None, end=None):
        lo, hi = self.bounds(start, end)
        sql = "SELECT COALESCE(SUM(total_cost),0) FROM expenses WHERE category='Feed' AND date BETWEEN %s AND %s"
        params = [lo, hi]
        if domain:
            sql += " AND domain=%s"
            params.append(domain)
        return Expect(required=[r2(self.one(sql, params))])

    # --- expenses / revenue / profit -------------------------------------------
    def expenses(self, domain=None, category=None, start=None, end=None):
        lo, hi = self.bounds(start, end)
        sql = "SELECT COALESCE(SUM(total_cost),0) FROM expenses WHERE date BETWEEN %s AND %s"
        params = [lo, hi]
        if domain:
            sql += " AND domain=%s"
            params.append(domain)
        if category:
            sql += " AND category=%s"
            params.append(category)
        return Expect(required=[r2(self.one(sql, params))])

    def expenses_by_domain(self, domains=None):
        rows = self.rows("SELECT domain, SUM(total_cost) FROM expenses GROUP BY domain ORDER BY domain")
        if domains:
            rows = [(d, v) for d, v in rows if d in domains]
            return Expect(required=[r2(v) for _, v in rows], note=f"only the named domains: {', '.join(domains)}")
        return Expect(required=[r2(v) for _, v in rows], words=["Shared (not allocated)"],
                      note="decision 5: the unallocated costs show as 'Shared (not allocated)' so the rows sum to the total")

    def expenses_by_category(self):
        rows = self.rows("SELECT category, SUM(total_cost) FROM expenses GROUP BY category ORDER BY 2 DESC")
        return Expect(required=[r2(v) for _, v in rows])

    def biggest_expense_category(self):
        cat, amount = self.rows("SELECT category, SUM(total_cost) FROM expenses GROUP BY category ORDER BY 2 DESC LIMIT 1")[0]
        return Expect(required=[r2(amount)], words=[cat])

    def revenue(self, domain=None, start=None, end=None):
        lo, hi = self.bounds(start, end)
        sql = "SELECT COALESCE(SUM(total_amount),0) FROM revenue WHERE date BETWEEN %s AND %s"
        params = [lo, hi]
        if domain:
            sql += " AND domain=%s"
            params.append(domain)
        return Expect(required=[r2(self.one(sql, params))])

    def top_revenue(self, by):
        col = "buyer" if by == "buyer" else "product"
        name, amount = self.rows(f"SELECT {col}, SUM(total_amount) FROM revenue GROUP BY {col} ORDER BY 2 DESC LIMIT 1")[0]
        return Expect(required=[r2(amount)], words=[name.split(" (")[0]])

    def profit(self, domain=None, start=None, end=None):
        lo, hi = self.bounds(start, end)
        rparams, eparams = [lo, hi], [lo, hi]
        rsql = "SELECT COALESCE(SUM(total_amount),0) FROM revenue WHERE date BETWEEN %s AND %s"
        esql = "SELECT COALESCE(SUM(total_cost),0) FROM expenses WHERE date BETWEEN %s AND %s"
        if domain:
            rsql += " AND domain=%s"; rparams.append(domain)
            esql += " AND domain=%s"; eparams.append(domain)
        p = r2(self.one(rsql, rparams) - self.one(esql, eparams))
        words_any = ["loss", "negative", "-", "deficit", "not profitable", "not making"] if p < 0 else []
        return Expect(required=[p], sign_agnostic=True, words_any=words_any)

    # --- receivables -------------------------------------------------------------
    def receivables(self, domain=None):
        sql = "SELECT buyer, SUM(total_amount) FROM revenue WHERE payment_status='Owing'"
        params = []
        if domain:
            sql += " AND domain=%s"
            params.append(domain)
        rows = self.rows(sql + " GROUP BY buyer ORDER BY 2 DESC", params)
        if not rows:
            return Expect(words_any=["no ", "none", "nothing", "zero", "not owing", "0"],
                          forbidden=[r2(v) for v in self.rows(
                              "SELECT SUM(total_amount) FROM revenue WHERE payment_status='Owing' GROUP BY buyer")[0]],
                          forbidden_words=["Chikafu"],
                          note="nobody owes in this domain; must not list another domain's debtor")
        return Expect(required=[r2(v) for _, v in rows], words=[b.split(" (")[0] for b, _ in rows])

    # --- labour -------------------------------------------------------------------
    def labour(self, domain=None, start=None, end=None, measure="cost"):
        lo, hi = self.bounds(start, end)
        col = {"cost": "labour_cost", "hours": "hours", "overtime": "overtime_hours"}[measure]
        sql = f"SELECT COALESCE(SUM({col}),0) FROM labour_log WHERE date BETWEEN %s AND %s"
        params = [lo, hi]
        if domain:
            sql += " AND domain=%s"
            params.append(domain)
        return Expect(required=[r2(self.one(sql, params))])

    # --- weights / harvest / breeding ------------------------------------------------
    def batch_weight(self, batch_code):
        if batch_code.startswith("PIG"):
            v = self.one("SELECT avg_weight_kg FROM pig_weights WHERE batch_code=%s ORDER BY date DESC LIMIT 1", (batch_code,))
        else:
            v = self.one("SELECT avg_weight_g FROM poultry_weights WHERE batch_code=%s ORDER BY date DESC LIMIT 1", (batch_code,))
        return Expect(required=[r2(v)], words=[batch_code])

    def harvest_total_kg(self, crop=None):
        sql = "SELECT COALESCE(SUM(h.quantity_kg),0) FROM harvest_log h JOIN plantings p USING(planting_code)"
        params = []
        if crop:
            sql += " WHERE p.crop ILIKE %s"
            params.append(crop)
        return Expect(required=[r2(self.one(sql, params))])

    def best_yield_plot(self):
        row = self.rows(
            "SELECT p.plot_code, p.crop, SUM(h.quantity_kg) / p.area_ha AS y FROM harvest_log h "
            "JOIN plantings p USING(planting_code) GROUP BY p.plot_code, p.crop, p.area_ha ORDER BY y DESC LIMIT 1")[0]
        return Expect(required=[r2(row[2])], words=[row[0]])

    def yield_for_crop(self, crop):
        row = self.rows(
            "SELECT SUM(h.quantity_kg) / p.area_ha FROM harvest_log h JOIN plantings p USING(planting_code) "
            "WHERE p.crop ILIKE %s GROUP BY p.planting_code, p.area_ha", (crop,))[0]
        return Expect(required=[r2(row[0])])

    def breeding(self, measure):
        litters = self.one("SELECT COUNT(*) FROM breeding_farrowing WHERE farrow_date IS NOT NULL")
        born = self.one("SELECT COALESCE(SUM(born_alive),0) FROM breeding_farrowing WHERE farrow_date IS NOT NULL")
        weaned = self.one("SELECT COALESCE(SUM(weaned_count),0) FROM breeding_farrowing WHERE farrow_date IS NOT NULL")
        if measure == "litters":
            return Expect(required=[litters])
        if measure == "born":
            return Expect(required=[born])
        if measure == "weaned":
            return Expect(required=[weaned])
        if measure == "avg_litter":
            return Expect(required=[round(born / litters, 1)])
        if measure == "best_sow":
            sow, n = self.rows("SELECT sow_tag, born_alive FROM breeding_farrowing WHERE farrow_date IS NOT NULL ORDER BY born_alive DESC LIMIT 1")[0]
            return Expect(required=[n], words=[sow])
        raise ValueError(measure)

    # --- stock / readiness / health / weather --------------------------------------------
    def feed_stock(self, domain=None):
        sql = ("SELECT SUM(closing_kg) FROM (SELECT DISTINCT ON (domain, feed_type) domain, closing_kg "
               "FROM feed_inventory {w} ORDER BY domain, feed_type, date DESC) s")
        if domain:
            v = self.one(sql.format(w="WHERE domain=%s"), (domain,))
        else:
            v = self.one(sql.format(w=""))
        return Expect(required=[r2(v)])

    def market_ready(self, domain=None, overdue_only=False):
        """Batches not yet sold whose target date has passed or falls within 30
        days of the latest data date. Sold batches are never 'ready to sell'."""
        last = self.last_data_date
        live, sold = [], []
        for t, d, col, live_status in (("pig_batches", "piggery", "target_market_date", "Active"),
                                       ("poultry_batches", "poultry", "target_off_date", "Growing")):
            if domain in (None, d):
                for code, target, status in self.rows(f"SELECT batch_code, {col}, status FROM {t}"):
                    (sold if status == "Sold" else live).append((code, target))
        due = [c for c, t in live if (t < last if overdue_only else t <= last + dt.timedelta(days=30))]
        return Expect(words=due, forbidden_words=[c for c, _ in sold],
                      note=f"as of {last}; sold batches must not be listed as ready/overdue")

    def no_overdue(self, domain=None):
        last = self.last_data_date
        live_overdue = []
        for t, d, col, live_status in (("pig_batches", "piggery", "target_market_date", "Active"),
                                       ("poultry_batches", "poultry", "target_off_date", "Growing")):
            if domain in (None, d):
                live_overdue += [c for c, tg in self.rows(f"SELECT batch_code, {col} FROM {t} WHERE status<>'Sold'") if tg < last]
        sold = [c for t in ("pig_batches", "poultry_batches") for (c,) in self.rows(f"SELECT batch_code FROM {t} WHERE status='Sold'")]
        return Expect(words_any=["no ", "none", "nothing", "not overdue", "aren't any", "are not any", "0 overdue"] if not live_overdue else [],
                      words=live_overdue, forbidden_words=sold,
                      note=f"as of {last}; sold batches are not overdue")

    def health(self, domain=None, event_type=None, measure="count", start=None, end=None):
        lo, hi = self.bounds(start, end)
        sql = "SELECT COUNT(*), COALESCE(SUM(cost),0) FROM health_log WHERE date BETWEEN %s AND %s"
        params = [lo, hi]
        if domain:
            sql += " AND domain=%s"; params.append(domain)
        if event_type:
            sql += " AND event_type=%s"; params.append(event_type)
        n, cost = self.rows(sql, params)[0]
        return Expect(required=[n if measure == "count" else r2(cost)])

    def weather_latest(self):
        d, rain, tmin, tmax, hum, _ = self.rows("SELECT * FROM weather_log ORDER BY date DESC LIMIT 1")[0]
        return Expect(required=[float(tmin), float(tmax), float(hum)], note=f"latest logged day {d}; rainfall {rain}")

    def rainfall_total(self, start, end):
        return Expect(required=[r2(self.one("SELECT COALESCE(SUM(rainfall_mm),0) FROM weather_log WHERE date BETWEEN %s AND %s", (start, end)))])

    # --- structural expectations ----------------------------------------------------------
    def refuse(self, note="", not_claims=(), forbidden=(), exempt=()):
        return Expect(not_claims=list(not_claims), forbidden=list(forbidden), note=note,
                      claim_exempt_words=list(exempt))

    def clarify(self, note=""):
        return Expect(note=note)

    def pending(self, note, forbidden=()):
        return Expect(scored=False, forbidden=list(forbidden), note=note)
