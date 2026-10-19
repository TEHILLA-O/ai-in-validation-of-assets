"""Tax on a signed taxable base, with a separate loss carryforward.

Book tax uses profit before tax. Unlevered tax uses EBIT. The two loss pools
are not mixed, because the interest tax shield belongs in WACC rather than in
unlevered free cash flow.
"""

from __future__ import annotations

from decimal import Decimal


def tax_and_nol(base: Decimal, nol: Decimal, rate: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    """Return tax expense, taxable income after the loss, and closing loss balance."""
    if rate < 0 or rate >= 1:
        raise ValueError("The tax rate must be at least zero and below 100%.")
    if nol < 0:
        raise ValueError("A tax-loss balance cannot be negative.")
    if base < 0:
        return Decimal(0), Decimal(0), nol - base
    used = min(nol, base)
    taxable = base - used
    return taxable * rate, taxable, nol - used
