"""
Period phrases to dates. Pure functions: no LLM, no database. Part of the scope resolver
(spec-chatbot-v2-plan.md, section 5; decision D2).

Relative phrases resolve against a calendar `today` (the farm's own date, Africa/Harare), never the
latest data date and never an LLM's guess. "This month" is the whole calendar month; whether the data
covers it is the registry's coverage check, not this module's business.
"""

import calendar
import datetime as dt
import difflib
import re
from dataclasses import dataclass
from zoneinfo import ZoneInfo

FARM_TZ = ZoneInfo("Africa/Harare")

FULL_MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
ABBREV_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
                 "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}
ALL_MONTHS = {**FULL_MONTHS, **ABBREV_MONTHS}
_M = "|".join(sorted(ALL_MONTHS, key=len, reverse=True))

# Words that mean "everything on record", overriding the dashboard filter (rule 2).
ALL_TIME_RE = re.compile(
    r"\b(all[\s-]?time|alltime|overall|ever|lifetime|since we (?:started|began|opened)|since the (?:start|beginning))\b")

# Time words this resolver cannot turn into dates. Better to say so than to guess a period.
UNSUPPORTED_RE = re.compile(
    r"\b(fortnight|season|recently|lately|these days|a while|couple of (?:days|weeks|months)|"
    r"few (?:days|weeks|months)|this (?:morning|afternoon|evening)|tonight|"
    r"(?:last|this|next) (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekend))\b")


def harare_today(now: dt.datetime = None) -> dt.date:
    """The calendar date on the farm (Africa/Harare)."""
    return (now.astimezone(FARM_TZ) if now else dt.datetime.now(FARM_TZ)).date()


@dataclass(frozen=True)
class Period:
    start: dt.date
    end: dt.date          # inclusive
    label: str
    kind: str             # explicit | relative


@dataclass(frozen=True)
class BareMonth:
    month: int
    word: str


# ---------------------------------------------------------------------------------------------- date helpers
def month_range(y, m):
    return dt.date(y, m, 1), dt.date(y, m, calendar.monthrange(y, m)[1])


def quarter_range(y, q):
    return dt.date(y, 3 * q - 2, 1), month_range(y, 3 * q)[1]


def add_months(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.year * 12 + d.month - 1 + n, 12)
    m += 1
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def month_name(m):
    return calendar.month_name[m]


def fmt_range(start: dt.date, end: dt.date) -> str:
    """'1–31 Aug 2026', '1 Aug 2026 – 15 Oct 2026', 'August 2026', '2026'."""
    if start == end:
        return f"{start.day} {start:%b} {start.year}"
    if start.year == end.year and start.month == end.month:
        return f"{start.day}–{end.day} {start:%b} {start.year}"
    return f"{start.day} {start:%b} {start.year} – {end.day} {end:%b} {end.year}"


def _month_label(y, m):
    return f"{month_name(m)} {y}"


# ---------------------------------------------------------------------------------------------- text preparation
_UNIT_WORDS = ("month", "week", "year", "quarter", "day", "months", "weeks", "years", "days", "quarters")


def normalise(text: str) -> str:
    """Lower-case, strip punctuation (keeping hyphens), fix month-name typos that sit next to a year."""
    t = re.sub(r"[^\w\s\-]", " ", text.lower())
    t = re.sub(r"\s+", " ", t).strip()

    def fix(m):
        word, year = m.group(1), m.group(2)
        if word in ALL_MONTHS or word in ("year", "since", "batch", "period", "quarter", "week", "month"):
            return m.group(0)
        close = difflib.get_close_matches(word, list(FULL_MONTHS), n=1, cutoff=0.8)
        return f"{close[0]} {year}" if close else m.group(0)

    t = re.sub(r"\b([a-z]{4,9}) (\d{4})\b", fix, t)

    def fix_unit(m):                                            # "last montth", "this wek", "previous yeer"
        word = m.group(2)
        if word in _UNIT_WORDS:
            return m.group(0)
        close = difflib.get_close_matches(word, _UNIT_WORDS, n=1, cutoff=0.8)
        return f"{m.group(1)} {close[0]}" if close else m.group(0)

    return re.sub(r"\b(last|this|previous|next|past|current|same) ([a-z]{3,9})\b", fix_unit, t)


def has_all_time_words(text: str) -> bool:
    return bool(ALL_TIME_RE.search(normalise(text)))


def unsupported_period_phrase(text: str):
    m = UNSUPPORTED_RE.search(normalise(text))
    return m.group(0) if m else None


# ---------------------------------------------------------------------------------------------- extraction
def _mask(t, m):
    return t[:m.start()] + " " * (m.end() - m.start()) + t[m.end():]


WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def start_of_week(today: dt.date, week_start: int = 0) -> dt.date:
    """The most recent `week_start` weekday on or before `today` (0 = Monday ... 6 = Sunday)."""
    return today - dt.timedelta(days=(today.weekday() - week_start) % 7)


def extract_periods(text: str, today: dt.date, week_start: int = 0):
    """Every period named in `text`, as (periods, bare_months). A bare month ("in March", no year) is returned
    separately: it cannot be resolved without guessing the year. `week_start` is the farm's first day of the
    week (0 = Monday, the default): "last week" is the previous full week from that day."""
    t = normalise(text)
    periods, bare = [], []

    # --- ranges: "from <M> [Y] to <M> [Y]" / "between <M> [Y] and <M> [Y]"
    rx = re.compile(rf"\b(?:from|between) ({_M})(?: (\d{{4}}))? (?:to|and|until|through) ({_M})(?: (\d{{4}}))?\b")
    for m in list(rx.finditer(t)):
        m1, y1, m2, y2 = ALL_MONTHS[m.group(1)], m.group(2), ALL_MONTHS[m.group(3)], m.group(4)
        if y1 is None and y2 is None:
            continue                                   # no year anywhere: leave it to the bare-month rule
        y2 = int(y2) if y2 else int(y1) + (1 if m2 < m1 else 0)
        y1 = int(y1) if y1 else y2 - (1 if m1 > m2 else 0)
        periods.append(Period(dt.date(y1, m1, 1), month_range(y2, m2)[1],
                              f"{_month_label(y1, m1)} to {_month_label(y2, m2)}", "explicit"))
        t = _mask(t, m)

    # --- "since <M> <Y>" / "since <Y>"
    for m in list(re.finditer(rf"\bsince ({_M}) (\d{{4}})\b", t)):
        start = dt.date(int(m.group(2)), ALL_MONTHS[m.group(1)], 1)
        periods.append(Period(start, today, f"since {_month_label(start.year, start.month)}", "explicit"))
        t = _mask(t, m)
    for m in list(re.finditer(r"\bsince (20\d{2})\b", t)):
        periods.append(Period(dt.date(int(m.group(1)), 1, 1), today, f"since {m.group(1)}", "explicit"))
        t = _mask(t, m)

    # --- quarters: "Q2 2026"
    for m in list(re.finditer(r"\bq([1-4]) ?(20\d{2})\b", t)):
        q, y = int(m.group(1)), int(m.group(2))
        periods.append(Period(*quarter_range(y, q), f"Q{q} {y}", "explicit"))
        t = _mask(t, m)

    # --- "<Month> <Year>", "<Month> of <Year>", ISO "2026-08"
    for m in list(re.finditer(rf"\b({_M}) (?:of )?(20\d{{2}})\b", t)):
        mo, y = ALL_MONTHS[m.group(1)], int(m.group(2))
        periods.append(Period(*month_range(y, mo), _month_label(y, mo), "explicit"))
        t = _mask(t, m)
    for m in list(re.finditer(r"\b(20\d{2})-(0[1-9]|1[0-2])\b", t)):
        y, mo = int(m.group(1)), int(m.group(2))
        periods.append(Period(*month_range(y, mo), _month_label(y, mo), "explicit"))
        t = _mask(t, m)

    # --- the same day a month or a year ago: ONE date, clamped to the last day of a shorter month
    #     (31 Mar - 1 month = 28/29 Feb; 29 Feb - 1 year = 28 Feb). Read before "last month" so it is never mistaken for it.
    for m in list(re.finditer(r"\b(?:the )?same day (?:last|previous) (month|year)\b|\b(?:on )?this (?:day|date) (?:in |of |on )?(?:the )?(?:last|previous) (month|year)\b|"
                              r"\b(?:the )?same date (?:in |of |on )?(?:the )?(?:last|previous) (month|year)\b|"
                              r"\btoday (?:last|previous) (month|year)\b|\b(?:a|one|1) (month|year) ago (?:today|to the day)\b", t)):
        unit = next(g for g in m.groups() if g)
        d = add_months(today, -1 if unit == "month" else -12)
        periods.append(Period(d, d, f"same day last {unit} ({fmt_range(d, d)})", "relative"))
        t = _mask(t, m)

    # --- relative phrases
    for m in list(re.finditer(r"\b(?:in |over |for |during )?the (?:last|past) (\d{1,3}) (day|days|week|weeks|month|months)\b|"
                              r"\b(?:in |over |for |during )?(?:last|past) (\d{1,3}) (day|days|week|weeks|month|months)\b", t)):
        n = int(m.group(1) or m.group(3))
        unit = (m.group(2) or m.group(4)).rstrip("s")
        if unit == "day":
            start = today - dt.timedelta(days=n - 1)
        elif unit == "week":
            start = today - dt.timedelta(days=7 * n - 1)
        else:
            start = add_months(today, -n) + dt.timedelta(days=1)
        periods.append(Period(start, today, f"last {n} {unit}{'s' if n != 1 else ''} ({fmt_range(start, today)})", "relative"))
        t = _mask(t, m)

    monday = start_of_week(today, week_start)          # the farm's first day of the week
    rel = [
        (r"\b(?:year to date|ytd|so far this year)\b", lambda: (dt.date(today.year, 1, 1), today, "year to date")),
        (r"\b(?:last|previous) month\b", lambda: (*month_range(*_prev_month(today)), "last month")),
        (r"\b(?:this|current) month\b", lambda: (*month_range(today.year, today.month), "this month")),
        (r"\b(?:next) month\b", lambda: (*month_range(*_next_month(today)), "next month")),
        (r"\b(?:last|previous) week\b", lambda: (monday - dt.timedelta(days=7), monday - dt.timedelta(days=1), "last week")),
        (r"\b(?:this|current) week\b", lambda: (monday, monday + dt.timedelta(days=6), "this week")),
        (r"\bnext week\b", lambda: (monday + dt.timedelta(days=7), monday + dt.timedelta(days=13), "next week")),
        (r"\b(?:last|previous) quarter\b", lambda: (*quarter_range(*_prev_quarter(today)), "last quarter")),
        (r"\b(?:this|current) quarter\b", lambda: (*quarter_range(today.year, (today.month - 1) // 3 + 1), "this quarter")),
        (r"\b(?:last|previous) year\b", lambda: (dt.date(today.year - 1, 1, 1), dt.date(today.year - 1, 12, 31), "last year")),
        (r"\b(?:this|current) year\b", lambda: (dt.date(today.year, 1, 1), dt.date(today.year, 12, 31), "this year")),
        (r"\byesterday\b", lambda: (today - dt.timedelta(days=1), today - dt.timedelta(days=1), "yesterday")),
        (r"\btoday\b", lambda: (today, today, "today")),
    ]
    for rx_s, build in rel:
        for m in list(re.finditer(rx_s, t)):
            start, end, name = build()
            label = name if name in ("year to date", "today", "yesterday") else f"{name} ({_pretty(start, end)})"
            periods.append(Period(start, end, label, "relative"))
            t = _mask(t, m)

    # --- a bare year: "in 2026"
    for m in list(re.finditer(r"\b(20\d{2})\b", t)):
        y = int(m.group(1))
        periods.append(Period(dt.date(y, 1, 1), dt.date(y, 12, 31), str(y), "explicit"))
        t = _mask(t, m)

    # --- bare months (no year): full names anywhere (except "may"); abbreviations and "may" only after a preposition
    for m in re.finditer(r"\b(january|february|march|april|june|july|august|september|october|november|december)\b", t):
        bare.append(BareMonth(FULL_MONTHS[m.group(1)], m.group(1)))
    for m in re.finditer(rf"\b(?:in|during|for|of|since|from|to|until|through|between|last|this|early|late|mid) ({_M})\b(?! \d)", t):
        if m.group(1) not in FULL_MONTHS or m.group(1) == "may":
            bare.append(BareMonth(ALL_MONTHS[m.group(1)], m.group(1)))
    return periods, bare


def _prev_month(today):
    return (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)


def _next_month(today):
    return (today.year, today.month + 1) if today.month < 12 else (today.year + 1, 1)


def _prev_quarter(today):
    q = (today.month - 1) // 3 + 1
    return (today.year, q - 1) if q > 1 else (today.year - 1, 4)


def _pretty(start, end):
    if start.day == 1 and end == month_range(start.year, start.month)[1]:
        return _month_label(start.year, start.month)
    if start.month == 1 and start.day == 1 and end.month == 12 and end.day == 31 and start.year == end.year:
        return str(start.year)
    if start.day == 1 and end.day == calendar.monthrange(end.year, end.month)[1] and (end.month - start.month) % 12 == 2:
        return f"{start:%b}–{end:%b} {end.year}"
    return fmt_range(start, end)


# ---------------------------------------------------------------------------------------------- comparisons
_CUE = re.compile(r"\b(vs\.?|versus|compared (?:to|with)|compare[sd]? (?:to|with)|comparison (?:to|with)|against|relative to|"
                  r"in comparison (?:to|with)|as opposed to|"
                  r"(?:up|down) from|change (?:from|since)|difference (?:between|from|to)|how (?:does|did|do) .{0,40} compare(?: to| with)?)\b")
# "more than last month", "higher than the same day last year": the period word is part of the cue itself
_THAN_PERIOD = re.compile(r"\b(?:more|less|higher|lower|bigger|smaller|greater|fewer|better|worse|up|down|different) than "
                          r"(?:last|this|the same|previous|yesterday|today|a (?:week|month|year)|20\d{2})\b")
# what follows the cue: another period, not another domain ("pigs vs chickens" compares domains, which is fine)
_PERIOD_TAIL = re.compile(rf"\s*(?:the |a |an )?(?:last|previous|this|same|yesterday|today|now|current|20\d{{2}}|q[1-4]|{_M})\b")
_WEAK_COMPARE = re.compile(r"\b(compare|compared|comparison)\b")


_COMPARE_WORDS = ("compare", "compared", "comparison", "comparing")


def _fix_compare_typos(t):
    def fix(m):
        w = m.group(0)
        if w in _COMPARE_WORDS or len(w) < 5:
            return w
        close = difflib.get_close_matches(w, _COMPARE_WORDS, n=1, cutoff=0.8)
        return close[0] if close else w
    return re.sub(r"[a-z]{5,11}", fix, t)


def comparison_cue(text: str):
    """'period' when the text sets one PERIOD against another ("vs last month", "compared to today", "more than last
    year"); 'weak' for a bare "compare" (which may only compare domains: "compare piggery and poultry costs"); else
    None. resolve() refuses a 'period' comparison, and a 'weak' one only if two periods are named."""
    t = _fix_compare_typos(normalise(text))
    if _THAN_PERIOD.search(t):
        return "period"
    for m in _CUE.finditer(t):
        if _PERIOD_TAIL.match(t[m.end():m.end() + 40]):
            return "period"
    return "weak" if _WEAK_COMPARE.search(t) else None
