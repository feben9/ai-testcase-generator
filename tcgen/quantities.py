"""Find numbers (with units) in requirement text and decide which ones are limits.

Deliberately small and rule-based: every decision here has to be explainable
in a review, so there is no fuzzy matching beyond a 1% tolerance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

# unit -> (family, factor to the family's base unit)
_UNITS: dict[str, tuple[str, int]] = {
    "%": ("percent", 1),
    "byte": ("size", 1),
    "bytes": ("size", 1),
    "kb": ("size", 1024),
    "mb": ("size", 1024**2),
    "gb": ("size", 1024**3),
    "second": ("time", 1),
    "seconds": ("time", 1),
    "sec": ("time", 1),
    "secs": ("time", 1),
    "minute": ("time", 60),
    "minutes": ("time", 60),
    "min": ("time", 60),
    "mins": ("time", 60),
    "hour": ("time", 3600),
    "hours": ("time", 3600),
    "hr": ("time", 3600),
    "hrs": ("time", 3600),
    "day": ("time", 86400),
    "days": ("time", 86400),
    "week": ("time", 604800),
    "weeks": ("time", 604800),
}

_WORD_UNITS = "|".join(sorted((re.escape(u) for u in _UNITS if u != "%"), key=len, reverse=True))

# "10,000.00", "10 MB", "60-minute", "0.5%", "6th". Not "TC-07", "US-101" or "3G".
_QUANTITY = re.compile(
    r"(?<![\w.,-])"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:st|nd|rd|th)?"
    rf"(?:\s?-?\s?(?P<unit>%|(?:{_WORD_UNITS})(?!\w)))?"
    r"(?!\w)",
    re.IGNORECASE,
)

# Words that turn a number in an acceptance criterion into a limit to test around.
AC_LIMIT_WORDS = (
    "at least", "at most", "up to", "no more than", "not more than", "no less than",
    "no fewer than", "not exceed", "exceed", "exceeds", "exceeding", "more than",
    "less than", "fewer than", "greater than", "larger than", "smaller than",
    "longer than", "shorter than", "above", "below", "over", "under", "minimum",
    "maximum", "min", "max", "limit", "within", "between", "after", "before",
    "expires", "expire", "valid for",
)

# Stricter list for expected results: only phrases that restate a rule, so test
# data ("open the link after 31 minutes") is not mistaken for a limit.
EXPECTED_LIMIT_WORDS = (
    "limit", "maximum", "minimum", "max", "min", "at most", "at least", "up to",
    "no more than", "no less than", "no fewer than", "not exceed", "exceed", "exceeds",
    "within", "expires", "expire", "valid for", "capped at", "cap",
)

_CLAUSE_BREAK = re.compile(r"[;!?\n\"“”]|[.:](?!\d)")
_WORD = re.compile(r"[a-z]+")


@dataclass(frozen=True)
class Quantity:
    text: str
    value: Decimal  # as written, in its own unit
    step: Decimal  # smallest step implied by how it was written (10,000.00 -> 0.01)
    unit: str | None
    family: str | None  # size | time | percent | None (plain number, money, count)
    factor: int
    start: int
    end: int

    @property
    def base(self) -> Decimal:
        return self.value * self.factor


def quantities(text: str) -> list[Quantity]:
    found = []
    for match in _QUANTITY.finditer(text):
        raw = match.group("num")
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        unit = (match.group("unit") or "").lower() or None
        family, factor = _UNITS.get(unit, (None, 1)) if unit else (None, 1)
        found.append(
            Quantity(
                text=match.group(0).strip(),
                value=Decimal(raw.replace(",", "")),
                step=Decimal(1).scaleb(-decimals),
                unit=unit,
                family=family,
                factor=factor,
                start=match.start(),
                end=match.end(),
            )
        )
    return found


def limit_quantities(text: str, keywords: tuple[str, ...], window: int) -> list[Quantity]:
    """Numbers preceded (within `window` words, same clause) by a limit keyword."""
    limits = []
    for quantity in quantities(text):
        before = text[: quantity.start]
        breaks = list(_CLAUSE_BREAK.finditer(before))
        if breaks:
            before = before[breaks[-1].end():]
        words = _WORD.findall(before.lower())[-window:]
        joined = f" {' '.join(words)} "
        if any(f" {keyword} " in joined for keyword in keywords):
            limits.append(quantity)
    return limits


def unique(items: list[Quantity]) -> list[Quantity]:
    seen, out = set(), []
    for q in items:
        key = (q.family, q.base) if q.family else (None, q.value)
        if key not in seen:
            seen.add(key)
            out.append(q)
    return out


def _comparable(a: Quantity, b: Quantity) -> tuple[Decimal, Decimal] | None:
    """Values to compare. Units are converted when both sides have one;
    when either side is a bare number the written values are compared."""
    if a.family and b.family:
        if a.family != b.family:
            return None
        return a.base, b.base
    return a.value, b.value


def same_amount(a: Quantity, b: Quantity) -> bool:
    pair = _comparable(a, b)
    return pair is not None and pair[0] == pair[1]


def offset_from_limit(limit: Quantity, q: Quantity) -> Decimal | None:
    """Signed distance of `q` from `limit` if q is at or next to the limit, else None.

    "Next to" means within one step of how the limit is written (1.00 -> 0.01,
    10 MB -> 1 MB, 30 minutes -> 1 minute) or 1% of the limit, whichever is larger.
    """
    pair = _comparable(q, limit)
    if pair is None:
        return None
    value, limit_value = pair
    if q.family and limit.family:
        step, magnitude = limit.step * limit.factor, limit.base
    else:
        step, magnitude = limit.step, limit.value
    tolerance = max(step, abs(magnitude) / 100)
    offset = value - limit_value
    return offset if abs(offset) <= tolerance else None
