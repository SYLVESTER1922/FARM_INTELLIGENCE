"""
Formatting rules for templated answers (plan decision D5): currency symbol and thousand separators, fixed decimals per
unit, human domain names, ISO-free dates. Pure functions; every number an answer shows passes through here.
"""

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "ZAR": "R"}


def _q(x, nd):
    return Decimal(str(x)).quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP)


def num(x, nd=0) -> str:
    """1,234.5 with a fixed number of decimals, half-up on the exact value."""
    if x is None:
        return "n/a"
    return f"{_q(x, nd):,.{nd}f}"


def money(x, currency="USD", nd=2) -> str:
    """$1,234.50 and -$1,234.50. An unknown currency code is shown as a prefix (ZWG 1,234.50), never dropped."""
    if x is None:
        return "n/a"
    sym = CURRENCY_SYMBOLS.get(currency)
    body = num(abs(Decimal(str(x))), nd)
    sign = "-" if Decimal(str(x)) < 0 else ""
    return f"{sign}{sym}{body}" if sym else f"{sign}{currency} {body}"


def pct(x, nd=2) -> str:
    return "n/a" if x is None else f"{num(x, nd)}%"


def date(d) -> str:
    """15 Sep 2026."""
    if d is None:
        return "n/a"
    if isinstance(d, str):
        d = dt.date.fromisoformat(d)
    return f"{d.day} {d:%b} {d.year}"


def plural(n, one, many=None) -> str:
    return f"{num(n)} {one if n == 1 else (many or one + 's')}"


def join_names(names) -> str:
    names = list(names)
    return names[0] if len(names) == 1 else (", ".join(names[:-1]) + " and " + names[-1])
