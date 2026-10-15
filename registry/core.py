"""
Metric registry: core types.

One definition per metric, shared by the chatbot (v2 path) and the dashboard
(ui/queries.py). See spec-chatbot-v2-plan.md, sections 3 to 5.

Nothing here parses language or reads the dashboard filter: building a Scope
from a question is the scope resolver's job (plan step 3). A Scope is just the
typed input every metric takes.

A period that lies outside a table's records answers "No <metric> recorded for
that period; latest record is <date>", never 0 (decision 4). Zero is only
returned inside coverage.
"""

import datetime as dt
from dataclasses import dataclass, field, replace
from decimal import ROUND_HALF_UP, Decimal

DOMAIN_LABELS = {
    "piggery": "Piggery",
    "poultry": "Poultry",
    "crops": "Crops",
    "shared": "Shared (not allocated)",
}
LIVESTOCK = ("piggery", "poultry")
ALL_DOMAINS = ("piggery", "poultry", "crops")
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

# Batch statuses (99_LISTS: STATUS_BATCH, POULTRY_STATUS) that mean the batch is
# no longer on the farm. Only batches NOT in this set count as "active".
INACTIVE_BATCH_STATUSES = ("Sold", "Closed")

# Daily-log tables: domain -> (table, headcount column, batch table, placed column, start-date column)
LOGS = {
    "piggery": {"log": "pig_daily_log", "count": "closing_count", "batches": "pig_batches",
                "placed": "start_count", "start": "start_date", "target": "target_market_date"},
    "poultry": {"log": "poultry_daily_log", "count": "closing_birds", "batches": "poultry_batches",
                "placed": "chicks_placed", "start": "placement_date", "target": "target_off_date"},
}


def rnd(x, nd=2):
    """Round half-up on the exact decimal value, never through a binary float: 4781.455 must show
    4781.46 (a float would give 4781.45). Money and counts only ever pass through here."""
    if x is None:
        return 0.0
    d = x if isinstance(x, Decimal) else Decimal(str(x))
    return float(d.quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP))


def label(domain):
    """Human domain name; NULL or 'shared' is the unallocated bucket."""
    return DOMAIN_LABELS.get(domain or "shared", str(domain))


@dataclass(frozen=True)
class Scope:
    """The typed scope every metric takes (plan section 5). `domains=None`
    means every domain the metric supports. `start`/`end` are inclusive."""
    domains: tuple = None
    start: dt.date = None
    end: dt.date = None
    as_of: dt.date = None            # snapshot metrics
    aggregation: str = "total"       # total | avg_per_week
    grain: str = None                # None | "month"
    dimension: str = None            # metric-specific: category | domain | buyer | product
    batch_code: str = None
    category: str = None             # expense category filter
    period_source: str = None        # question | filter | all_time | snapshot (set by the resolver)

    def with_(self, **kw):
        return replace(self, **kw)


@dataclass
class Coverage:
    first_record: dt.date = None
    last_record: dt.date = None
    partial: bool = False            # requested period reaches beyond the records
    days_covered: int = None         # days of the requested period that fall inside the records


@dataclass
class Result:
    metric_id: str
    status: str                      # ok | no_record | not_available
    scope: Scope
    unit: str = ""
    figures: dict = field(default_factory=dict)   # headline numbers
    rows: list = field(default_factory=list)      # breakdown rows, largest first where ranked
    coverage: Coverage = field(default_factory=Coverage)
    notes: list = field(default_factory=list)     # statements an answer must carry (denominators, days used)
    message: str = None              # the exact sentence for no_record / not_available

    @property
    def ok(self):
        return self.status == "ok"


@dataclass(frozen=True)
class Metric:
    id: str
    title: str                       # used in "No <title> recorded ..."
    group: str                       # money | headcount | performance | operations
    definition: str
    sources: tuple                   # source tables
    unit: str
    decimals: int
    period: str                      # range | snapshot | none
    domains: tuple                   # domains it supports
    zero_tolerance: bool
    answers: str
    does_not_answer: str
    compute: callable
    dimensions: tuple = ()
    aggregations: tuple = ("total",)
    grains: tuple = ()
    eval_oracles: tuple = ()         # oracle method names whose eval cases cover this metric
    dashboard: tuple = ()            # ui.queries functions that must show this metric's numbers (parity)
    parity_exempt: str = ""          # why a metric has no dashboard counterpart
    uses_filter: bool = True         # False: a balance or snapshot that ignores the dashboard date filter
    snapshot_default: bool = False   # True: with no period named it answers "latest" (weather), else a range


REGISTRY = {}


def register(metric: Metric):
    if metric.id in REGISTRY:
        raise ValueError(f"duplicate metric {metric.id}")
    if not metric.dashboard and not metric.parity_exempt:
        raise ValueError(f"{metric.id}: declare a dashboard parity hook or a parity_exempt reason")
    REGISTRY[metric.id] = metric
    return metric


# --------------------------------------------------------------------------- helpers
def rows_of(conn, sql, params=None):
    cur = conn.execute(sql, params or {})
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def one(conn, sql, params=None):
    return conn.execute(sql, params or {}).fetchone()[0]


def table_range(conn, table, column="date"):
    """(first, last) record date of a table, or (None, None) if empty."""
    first, last = conn.execute(f"SELECT MIN({column}), MAX({column}) FROM {table}").fetchone()
    return first, last


def union_range(conn, tables, column="date"):
    firsts, lasts = [], []
    for t in tables:
        f, l = table_range(conn, t, column)
        if f is not None:
            firsts.append(f)
            lasts.append(l)
    return (min(firsts), max(lasts)) if firsts else (None, None)


def latest_log_date(conn, domains=LIVESTOCK):
    """The latest logged operational date across the livestock daily logs: what a
    snapshot ("as of") uses as today (decision D3)."""
    return union_range(conn, [LOGS[d]["log"] for d in domains])[1]


def check_period(metric_title, scope, first, last):
    """Apply the no-record rule to one source's [first, last] coverage. Returns
    (message_or_None, Coverage). No message means the period is inside, or
    partly inside, the records."""
    cov = Coverage(first_record=first, last_record=last)
    if first is None:
        return f"No {metric_title} recorded.", cov
    lo, hi = scope.start, scope.end
    if lo is not None and lo > last:
        return f"No {metric_title} recorded for that period; latest record is {last}.", cov
    if hi is not None and hi < first:
        return f"No {metric_title} recorded for that period; earliest record is {first}.", cov
    eff_lo = max(lo, first) if lo else first
    eff_hi = min(hi, last) if hi else last
    cov.days_covered = (eff_hi - eff_lo).days + 1
    cov.partial = bool((lo and lo < first) or (hi and hi > last))
    return None, cov


def no_record(metric_id, scope, unit, message, coverage):
    return Result(metric_id=metric_id, status="no_record", scope=scope, unit=unit,
                  message=message, coverage=coverage)


def bounds(scope):
    return (scope.start or dt.date(1900, 1, 1)), (scope.end or dt.date(2999, 12, 31))


def pick_domains(scope, allowed):
    """Domains in scope intersected with those the metric supports, in a stable order."""
    wanted = scope.domains if scope.domains else allowed
    return tuple(d for d in allowed if d in wanted)


def month_label(d):
    return d.strftime("%Y-%m")
