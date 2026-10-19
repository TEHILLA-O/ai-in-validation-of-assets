"""Debt schedule and interest.

Scheduled borrowings and repayments are applied before the minimum-cash
revolver. Repayments reduce current debt first and long-term debt afterwards.
That order is a documented allocation of the total repayment the user entered.
The total itself is not reduced.

Interest basis:
- opening: rate × opening interest-bearing debt, including the opening revolver.
  New drawings do not accrue interest until the next year. This case has no
  circularity.
- average: rate × (opening + closing) / 2, including the revolver solved below.
- closing: rate × closing interest-bearing debt, including the revolver.

When the basis depends on the current revolver, the engine solves for the
smallest revolver draw that restores minimum cash. The search is bounded.
It does not iterate without a stop, and a failure is reported rather than
replaced with a balancing plug.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from financial_engine.model import Assumptions


@dataclass
class DebtPosition:
    opening_short: Decimal
    opening_long: Decimal
    opening_revolver: Decimal
    borrowings_short: Decimal
    borrowings_long: Decimal
    repayment_short: Decimal
    repayment_long: Decimal
    revolver_flow: Decimal
    closing_short: Decimal
    closing_long: Decimal
    closing_revolver: Decimal
    interest_expense: Decimal
    interest_base: Decimal
    interest_rate: Decimal

    @property
    def opening_total(self) -> Decimal:
        return self.opening_short + self.opening_long + self.opening_revolver

    @property
    def closing_total(self) -> Decimal:
        return self.closing_short + self.closing_long + self.closing_revolver


def allocate_repayment(
    opening_short: Decimal,
    opening_long: Decimal,
    borrowings_short: Decimal,
    borrowings_long: Decimal,
    total_repayment: Decimal,
) -> tuple[Decimal, Decimal]:
    if total_repayment < 0:
        raise ValueError("Repayments are entered as a positive amount.")
    short_available = opening_short + borrowings_short
    if total_repayment <= short_available:
        return total_repayment, Decimal(0)
    return short_available, total_repayment - short_available


def interest_on(base: Decimal, rate: Decimal) -> Decimal:
    return base * rate


def debt_before_revolver(
    assumptions: Assumptions,
    period_id: str,
    opening_short: Decimal,
    opening_long: Decimal,
    opening_revolver: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]:
    borrowings = assumptions.borrowings.get(period_id, Decimal(0))
    repayments = assumptions.repayments.get(period_id, Decimal(0))
    borrowings_short = Decimal(0)
    borrowings_long = borrowings
    repay_short, repay_long = allocate_repayment(
        opening_short, opening_long, borrowings_short, borrowings_long, repayments
    )
    closing_short = opening_short + borrowings_short - repay_short
    closing_long = opening_long + borrowings_long - repay_long
    return (
        borrowings_short,
        borrowings_long,
        repay_short,
        repay_long,
        closing_short,
        closing_long,
    )


def interest_amount(
    assumptions: Assumptions,
    opening_short: Decimal,
    opening_long: Decimal,
    opening_revolver: Decimal,
    closing_short: Decimal,
    closing_long: Decimal,
    closing_revolver: Decimal,
) -> tuple[Decimal, Decimal]:
    rate = assumptions.interest_rate
    revolver_rate = assumptions.revolver_rate if assumptions.revolver_rate is not None else rate
    if assumptions.interest_basis == "opening":
        base_core = opening_short + opening_long
        base_revolver = opening_revolver
    elif assumptions.interest_basis == "closing":
        base_core = closing_short + closing_long
        base_revolver = closing_revolver
    elif assumptions.interest_basis == "average":
        base_core = (opening_short + opening_long + closing_short + closing_long) / Decimal(2)
        base_revolver = (opening_revolver + closing_revolver) / Decimal(2)
    else:
        raise ValueError(f"Unknown interest basis {assumptions.interest_basis}")
    interest = interest_on(base_core, rate) + interest_on(base_revolver, revolver_rate)
    return interest, base_core + base_revolver


def build_debt(
    assumptions: Assumptions,
    period_id: str,
    opening_short: Decimal,
    opening_long: Decimal,
    opening_revolver: Decimal,
    revolver_flow: Decimal,
) -> DebtPosition:
    borrowings_short, borrowings_long, repay_short, repay_long, closing_short, closing_long = debt_before_revolver(
        assumptions, period_id, opening_short, opening_long, opening_revolver
    )
    closing_revolver = opening_revolver + revolver_flow
    interest, base = interest_amount(
        assumptions,
        opening_short,
        opening_long,
        opening_revolver,
        closing_short,
        closing_long,
        closing_revolver,
    )
    return DebtPosition(
        opening_short=opening_short,
        opening_long=opening_long,
        opening_revolver=opening_revolver,
        borrowings_short=borrowings_short,
        borrowings_long=borrowings_long,
        repayment_short=repay_short,
        repayment_long=repay_long,
        revolver_flow=revolver_flow,
        closing_short=closing_short,
        closing_long=closing_long,
        closing_revolver=closing_revolver,
        interest_expense=interest,
        interest_base=base,
        interest_rate=assumptions.interest_rate,
    )
