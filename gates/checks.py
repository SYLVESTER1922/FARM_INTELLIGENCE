"""
The gates. Each check reads the STAGING copy (schema `staging`, loaded in the same transaction) and returns Firings; none writes. Severities
follow plan section 9:

    block   invalid or missing currency; suspected mixed currency; unrecognised units; duplicate primary keys
    warn    a month with no rows; a 10x jump or drop in an expense category between consecutive months; rows the sync rejected;
            a value outside its 99_LISTS list that the sync does not itself reject (an addition to the plan's table, like rejected rows)
    report  feed consumption reconciliation (daily log vs feed_inventory.used_kg) above the farm's tolerance: listed in the
            data-quality report only, never a banner or a caveat

"Rows the sync rejected" (a category or batch reference that is not in 99_LISTS or the batch register) is a WARN, an addition to the plan's
table: the rows are missing from the live copy, so the affected metrics carry a caveat. Whether it should block is Sylvester's decision.
"""

import calendar
import datetime as dt
import re
from dataclasses import dataclass, field

from gates import BLOCK, REPORT, WARN
from registry import REGISTRY

S = "staging"

# ISO 4217 codes a farm might use (active codes; the workbook's own list is USD and ZWG).
ISO_CURRENCIES = frozenset("""AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BRL BSD BTN BWP BYN BZD CAD CDF CHF
CLP CNY COP CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD
JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR
NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD
TWD TZS UAH UGX USD UYU UZS VES VND VUV WST XAF XCD XOF XPF YER ZAR ZMW ZWG""".split())
_CURRENCY_ALIASES = {"ZIG": "ZWG", "ZWL": "ZWL", "RAND": "ZAR"}
_SYMBOLS = {"£": "GBP", "€": "EUR"}
# Codes that are not ordinary English words, so a bare mention is evidence; any other ISO code counts only next to an amount ("ALL" and "TOP" are words).
_UNAMBIGUOUS = frozenset("USD ZWG ZWL ZAR BWP MZN EUR GBP ZMW MWK AUD CAD".split())
# Text columns where a different currency named in the words is evidence of mixed currency.
TEXT_COLUMNS = {"expenses": ("item", "supplier", "allocation_note", "payment_method"),
                "revenue": ("buyer", "product", "notes"), "labour_log": ("notes",)}
UNIT_COLUMNS = {("expenses", "unit"): "UNIT_GENERAL", ("revenue", "unit"): "UNIT_SALES", ("field_operations", "unit"): "UNIT_FIELD"}
MONTHLY_TABLES = {"expenses": "date", "labour_log": "date", "pig_daily_log": "date", "poultry_daily_log": "date",
                  "feed_inventory": "date", "weather_log": "date"}
JUMP = 10


@dataclass
class Firing:
    gate: str
    severity: str
    message: str
    table: str = None
    rows: int = 0
    period: tuple = None                 # (start, end) the issue covers, when it is about a period
    key: str = ""                        # stable identity, so a later run can tell "the same issue" from a new one
    metrics: tuple = None                # metric ids whose answers it affects (derived from the registry's `sources`); () = none

    def __post_init__(self):
        if not self.key:
            self.key = f"{self.gate}:{self.table}:{self.period}"
        if self.metrics is None:
            self.metrics = metrics_reading(self.table)


def metrics_reading(table):
    """Metrics that read `table`; with no table (currency) every money metric."""
    if table is None:
        return tuple(m.id for m in REGISTRY.values() if m.unit == "currency")
    return tuple(m.id for m in REGISTRY.values() if table in m.sources)


def _exists(conn, table):
    return conn.execute("SELECT to_regclass(%s)", (f"{S}.{table}",)).fetchone()[0] is not None


def _months(first: dt.date, last: dt.date):
    y, m = first.year, first.month
    while (y, m) <= (last.year, last.month):
        yield dt.date(y, m, 1)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def _month_end(d):
    return dt.date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


# ------------------------------------------------------------------------------------------------------------------------------ block
def currency_gate(conn, farm_code):
    row = conn.execute(f"SELECT currency FROM {S}.farm_profile WHERE farm_code = %s", (farm_code,)).fetchone() if _exists(conn, "farm_profile") else None
    code = (row[0] if row else None)
    if code is None or not str(code).strip():
        return [Firing("currency_missing", BLOCK, "The farm profile has no currency.", "farm_profile", 1, key="currency")]
    if str(code).strip() not in ISO_CURRENCIES:
        return [Firing("currency_invalid", BLOCK, f"The farm currency '{code}' is not a recognised ISO currency code.", "farm_profile", 1, key="currency")]
    return []


def _foreign_markers(text, home):
    found = {code for sym, code in _SYMBOLS.items() if sym in text}
    for tok in re.findall(r"(?<![A-Za-z])(?:[A-Z]{3}|[Zz][Ii][Gg]|[Zz][Ww][Ll]|[Rr]and)(?![A-Za-z])", text):
        code = _CURRENCY_ALIASES.get(tok.upper(), tok.upper())
        if code in _UNAMBIGUOUS or tok.upper() in _CURRENCY_ALIASES:
            found.add(code)
    for m in re.finditer(r"(?<![A-Za-z])([A-Z]{3})\s?\d|\d\s?([A-Z]{3})(?![A-Za-z])", text):
        code = m.group(1) or m.group(2)
        if code in ISO_CURRENCIES:
            found.add(code)
    if re.search(r"(?<![A-Za-z])R ?\d", text):
        found.add("ZAR")
    found.discard(home)
    return found


def mixed_currency_gate(conn, farm_code):
    home = None
    if _exists(conn, "farm_profile"):
        r = conn.execute(f"SELECT currency FROM {S}.farm_profile WHERE farm_code = %s", (farm_code,)).fetchone()
        home = (r[0] if r else None)
    if home not in ISO_CURRENCIES:
        return []                                        # the currency gate already blocks; nothing to compare with
    out = []
    for table, cols in TEXT_COLUMNS.items():
        if not _exists(conn, table):
            continue
        present = {r[0] for r in conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s", (S, table))}
        cols = [c for c in cols if c in present]
        if not cols:
            continue
        hits, codes = 0, set()
        for row in conn.execute(f"SELECT {', '.join(cols)} FROM {S}.{table}").fetchall():
            f = _foreign_markers(" ".join(str(v) for v in row if v), home)
            if f:
                hits += 1
                codes |= f
        if hits:
            out.append(Firing("mixed_currency", BLOCK, f"{hits} {table} row(s) name {', '.join(sorted(codes))} but the farm currency is {home}.", table, hits,
                              key=f"mixed_currency:{table}"))
    return out


def unit_gate(conn, sync_errors):
    out = []
    lists = {}
    if _exists(conn, "list_values"):
        for name, value in conn.execute(f"SELECT list_name, value FROM {S}.list_values").fetchall():
            lists.setdefault(name, set()).add(value)
    for (table, col), list_name in UNIT_COLUMNS.items():
        if not _exists(conn, table) or list_name not in lists:
            continue
        bad = conn.execute(f"SELECT {col}, COUNT(*) FROM {S}.{table} WHERE {col} IS NOT NULL GROUP BY 1").fetchall()
        bad = [(v, n) for v, n in bad if v not in lists[list_name]]
        rejected = [e for e in sync_errors if e.get("table") == table and e.get("field") == col]
        if bad or rejected:
            vals = sorted({str(v) for v, _ in bad} | {str(e["value"]) for e in rejected})
            n = sum(n for _, n in bad) + len(rejected)
            out.append(Firing("unrecognised_unit", BLOCK, f"{table} has {n} row(s) with a unit not in the {list_name} list: {', '.join(vals)}.", table, n,
                              key=f"unrecognised_unit:{table}.{col}"))
    return out


def duplicate_key_gate(duplicates):
    """`duplicates`: {table: [sample, ...]} recorded while staging (an insert that conflicted with a row of the same load)."""
    return [Firing("duplicate_primary_key", BLOCK, f"{table} has {len(rows)} row(s) repeating a key that appears earlier in the upload (e.g. {rows[0]}).", table, len(rows),
                   key=f"duplicate_primary_key:{table}") for table, rows in sorted(duplicates.items()) if rows]


# ------------------------------------------------------------------------------------------------------------------------------- warn
# Daily logs follow batches: a month with no batch on the farm has no rows, and that is not a gap. Batch span = start .. its last logged day
# (or its target date if later).
BATCH_LOGS = {"pig_daily_log": ("pig_batches", "start_date", "target_market_date"),
              "poultry_daily_log": ("poultry_batches", "placement_date", "target_off_date")}


def _expected_months(conn, table, col, first, last):
    if table not in BATCH_LOGS or not _exists(conn, BATCH_LOGS[table][0]):
        return list(_months(first.replace(day=1), last))
    batches, start_col, end_col = BATCH_LOGS[table]
    spans = conn.execute(f"""SELECT b.{start_col}, GREATEST(COALESCE(b.{end_col}, b.{start_col}), COALESCE(MAX(l.date), b.{start_col}))
                             FROM {S}.{batches} b LEFT JOIN {S}.{table} l ON l.batch_code = b.batch_code
                             WHERE b.{start_col} IS NOT NULL GROUP BY b.batch_code, b.{start_col}, b.{end_col}""").fetchall()
    months = set()
    for lo, hi in spans:
        months |= set(_months(lo.replace(day=1), min(hi, last)))
    return sorted(m for m in months if first.replace(day=1) <= m <= last)


def empty_month_gate(conn, modules=None):
    out = []
    for table, col in MONTHLY_TABLES.items():
        if not _exists(conn, table):
            continue
        if modules is not None:
            dom = {"pig_daily_log": "piggery", "poultry_daily_log": "poultry"}.get(table)
            if dom and not modules.get(dom, True):
                continue
        first, last = conn.execute(f"SELECT MIN({col}), MAX({col}) FROM {S}.{table}").fetchone()
        if first is None:
            continue
        have = {r[0] for r in conn.execute(f"SELECT date_trunc('month', {col})::date FROM {S}.{table} GROUP BY 1")}
        for m in _expected_months(conn, table, col, first, last):
            if m not in have:
                out.append(Firing("month_without_rows", WARN, f"{table} has no rows for {m.strftime('%B %Y')}.", table, 1, (m, _month_end(m)),
                                  key=f"month_without_rows:{table}:{m}"))
    return out


def category_jump_gate(conn):
    if not _exists(conn, "expenses"):
        return []
    rows = conn.execute(f"""SELECT category, date_trunc('month', date)::date AS m, SUM(total_cost) FROM {S}.expenses
                            WHERE category IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2""").fetchall()
    by = {}
    for cat, m, total in rows:
        by.setdefault(cat, {})[m] = float(total or 0)
    out = []
    for cat, months in by.items():
        for m in sorted(months):
            nxt = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
            if nxt in months and months[m] > 0 and months[nxt] > 0:
                ratio = months[nxt] / months[m]
                if ratio >= JUMP or ratio <= 1 / JUMP:
                    out.append(Firing("category_jump", WARN,
                                      f"{cat} expenses {'rose' if ratio > 1 else 'fell'} {max(ratio, 1 / ratio):.0f}x from {m.strftime('%b %Y')} "
                                      f"({months[m]:,.2f}) to {nxt.strftime('%b %Y')} ({months[nxt]:,.2f}).",
                                      "expenses", 1, (m, _month_end(nxt)), key=f"category_jump:{cat}:{nxt}"))
    return out


# Columns the sync does not validate against 99_LISTS (it validates others and rejects those rows). A value outside its list still goes live, so it
# is a warning: a typo'd category splits a total ("Feeed") and no category question would find it.
LIST_COLUMNS = (("expenses", "category", "EXP_CATEGORY"), ("expenses", "domain", "DOMAIN"), ("expenses", "payment_method", "PAYMENT_METHOD"),
                ("revenue", "domain", "DOMAIN"), ("revenue", "product", "PRODUCT"), ("labour_log", "domain", "DOMAIN"),
                ("feed_inventory", "feed_type", "FEED_TYPE"), ("feed_inventory", "domain", "DOMAIN"))


def unknown_value_gate(conn):
    if not _exists(conn, "list_values"):
        return []
    lists = {}
    for name, value in conn.execute(f"SELECT list_name, value FROM {S}.list_values").fetchall():
        lists.setdefault(name, set()).add(value)
    out = []
    for table, col, list_name in LIST_COLUMNS:
        if not _exists(conn, table) or list_name not in lists:
            continue
        bad = [(v, n) for v, n in conn.execute(f"SELECT {col}, COUNT(*) FROM {S}.{table} WHERE {col} IS NOT NULL GROUP BY 1").fetchall() if v not in lists[list_name]]
        if bad:
            vals = ", ".join(repr(v) for v, _ in sorted(bad, key=lambda x: str(x[0]))[:5])
            out.append(Firing("unknown_value", WARN, f"{sum(n for _, n in bad)} {table} row(s) have a {col} that is not in the {list_name} list: {vals}.",
                              table, sum(n for _, n in bad), key=f"unknown_value:{table}.{col}"))
    return out


def rejected_rows_gate(sync_errors):
    by = {}
    for e in sync_errors:
        if e.get("field") == "unit":
            continue                                    # reported by the unit gate (block)
        by.setdefault(e.get("table"), []).append(e)
    return [Firing("rows_rejected", WARN, f"{len(es)} {t} row(s) were left out because a value is not allowed ({es[0].get('field')}: {es[0].get('value')!r}, {es[0].get('reason')}).",
                   t, len(es), key=f"rows_rejected:{t}") for t, es in sorted(by.items(), key=lambda kv: str(kv[0]))]


# ------------------------------------------------------------------------------------------------------------------------- report only
def feed_reconciliation_report(conn, tolerance_pct=5.0):
    """Months where the daily logs' feed_kg and feed_inventory.used_kg differ by more than the tolerance. Report only: no banner, no caveat."""
    if not (_exists(conn, "feed_inventory") and _exists(conn, "pig_daily_log") and _exists(conn, "poultry_daily_log")):
        return []
    out = []
    for domain, log in (("piggery", "pig_daily_log"), ("poultry", "poultry_daily_log")):
        rows = conn.execute(f"""
            WITH l AS (SELECT date_trunc('month', date)::date m, SUM(feed_kg) kg FROM {S}.{log} GROUP BY 1),
                 i AS (SELECT date_trunc('month', date)::date m, SUM(used_kg) kg FROM {S}.feed_inventory WHERE domain = %s GROUP BY 1)
            SELECT COALESCE(l.m, i.m), l.kg, i.kg FROM l FULL JOIN i ON l.m = i.m ORDER BY 1""", (domain,)).fetchall()
        for m, log_kg, inv_kg in rows:
            if log_kg is None or inv_kg is None or float(inv_kg) == 0:
                continue
            diff = abs(float(log_kg) - float(inv_kg)) / float(inv_kg) * 100
            if diff > tolerance_pct:
                out.append(Firing("feed_reconciliation", REPORT,
                                  f"{domain} {m.strftime('%b %Y')}: daily logs {float(log_kg):,.0f} kg vs feed inventory {float(inv_kg):,.0f} kg ({diff:.1f}% apart; tolerance {tolerance_pct:g}%).",
                                  log, 1, (m, _month_end(m)), key=f"feed_reconciliation:{domain}:{m}", metrics=()))
    return out


def run_all(conn, farm_code, *, sync_errors=(), duplicates=None, tolerance_pct=5.0, modules=None):
    sync_errors = list(sync_errors)
    out = []
    out += currency_gate(conn, farm_code)
    out += mixed_currency_gate(conn, farm_code)
    out += unit_gate(conn, sync_errors)
    out += duplicate_key_gate(duplicates or {})
    out += empty_month_gate(conn, modules)
    out += category_jump_gate(conn)
    out += unknown_value_gate(conn)
    out += rejected_rows_gate(sync_errors)
    out += feed_reconciliation_report(conn, tolerance_pct)
    return out
