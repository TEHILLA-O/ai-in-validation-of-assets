"""Decimal precision policy for ValuationLab.

Financial amounts stay as Decimal from input through valuation. They are not
cast to float inside the calculation engine. Display rounding is a presentation
concern and is not allowed to feed back into the statements.

Division uses the default Decimal context (28 significant digits). Integrity
checks compare exact engine results with a configurable tolerance so that a
later display layer can round without hiding a real imbalance.
"""

from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Any

TWOPLACES = Decimal("0.01")
TOLERANCE = Decimal("0.000001")


def D(value: Any) -> Decimal:
    """Convert an input to Decimal without a binary float detour."""
    if isinstance(value, Decimal):
        return value
    if value is None:
        raise TypeError("Cannot convert None to Decimal")
    if isinstance(value, bool):
        raise TypeError("Boolean is not a financial amount")
    if isinstance(value, float):
        raise TypeError(
            "Float is refused. Pass a string or Decimal so binary rounding "
            "cannot enter the model."
        )
    return Decimal(str(value))


def money(value: Decimal) -> Decimal:
    """Quantize only when a caller explicitly wants display cents."""
    return D(value).quantize(TWOPLACES)


def require_finite(value: Decimal, label: str) -> Decimal:
    if not value.is_finite():
        raise ValueError(f"{label} is not a finite number")
    return value


def cagr(start: Decimal, end: Decimal, periods: int) -> Decimal | None:
    """Compound annual growth. Returns None when the ratio is undefined."""
    if periods <= 0 or start <= 0 or end <= 0:
        return None
    ratio = end / start
    with localcontext() as ctx:
        ctx.prec = 28
        return (ratio.ln() / Decimal(periods)).exp() - Decimal(1)


def nearly_equal(left: Decimal | None, right: Decimal | None, tolerance: Decimal) -> bool:
    if left is None or right is None:
        return left is right
    return abs(left - right) <= tolerance
