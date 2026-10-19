"""Operating working capital.

Projection convention: period-end balances, not averages.

    AR  = revenue × DSO / days
    Inv = COGS × DIO / days
    AP  = COGS × DPO / days

Historical days ratios use an average balance when the prior closing balance
exists, and that choice is labelled. Forecast balances stay on the ending
convention above so the cash-flow change is the change in the closing balance.
Cash and interest-bearing debt are excluded.
"""

from __future__ import annotations

from decimal import Decimal

from financial_engine.model import Assumptions


def _days_metric(
    current: Decimal | None,
    prior: Decimal | None,
    flow: Decimal | None,
    days: int,
) -> tuple[Decimal | None, str]:
    if current is None or flow is None or flow == 0:
        return None, "Not calculated. A balance or a non-zero flow is missing."
    if prior is None:
        metric = current / flow * Decimal(days)
        return metric, "Ending balance, because no prior closing balance is available. This is not an average."
    average = (current + prior) / Decimal(2)
    return average / flow * Decimal(days), "Average of opening and closing balances."


def ending_balance(flow: Decimal, days_metric: Decimal, days: int) -> Decimal:
    if days <= 0:
        raise ValueError("Days in the period must be positive.")
    return flow * days_metric / Decimal(days)


def project_working_capital(
    assumptions: Assumptions,
    period_id: str,
    revenue: Decimal,
    cogs: Decimal,
    days: int,
) -> dict[str, Decimal]:
    dso = assumptions.rate_for(assumptions.dso, period_id, assumptions.flat_dso)
    dio = assumptions.rate_for(assumptions.dio, period_id, assumptions.flat_dio)
    dpo = assumptions.rate_for(assumptions.dpo, period_id, assumptions.flat_dpo)
    if dso is None or dio is None or dpo is None:
        raise ValueError(f"DSO, DIO and DPO are required for {period_id}.")
    receivables = ending_balance(revenue, dso, days)
    inventory = ending_balance(cogs, dio, days)
    payables = ending_balance(cogs, dpo, days)
    other_ca = revenue * assumptions.other_ca_pct_revenue
    accrued = revenue * assumptions.accrued_pct_revenue
    other_ocl = revenue * assumptions.other_ocl_pct_revenue
    operating_assets = receivables + inventory + other_ca
    operating_liabilities = payables + accrued + other_ocl
    nwc = operating_assets - operating_liabilities
    return {
        "dso": dso,
        "dio": dio,
        "dpo": dpo,
        "days": Decimal(days),
        "accounts_receivable": receivables,
        "inventory": inventory,
        "other_current_assets": other_ca,
        "accounts_payable": payables,
        "accrued_expenses": accrued,
        "other_operating_cl": other_ocl,
        "operating_current_assets": operating_assets,
        "operating_current_liabilities": operating_liabilities,
        "operating_nwc": nwc,
    }


def nwc_from_balance(balance: dict[str, Decimal | None]) -> Decimal | None:
    keys = (
        "accounts_receivable",
        "inventory",
        "other_current_assets",
        "accounts_payable",
        "accrued_expenses",
        "other_operating_cl",
    )
    if any(balance.get(key) is None for key in keys):
        return None
    assets = (
        balance["accounts_receivable"]
        + balance["inventory"]
        + balance["other_current_assets"]
    )
    liabilities = (
        balance["accounts_payable"]
        + balance["accrued_expenses"]
        + balance["other_operating_cl"]
    )
    return assets - liabilities


def historical_days(
    current: dict[str, Decimal | None],
    prior: dict[str, Decimal | None] | None,
    income: dict[str, Decimal | None],
    days: int,
) -> dict[str, tuple[Decimal | None, str]]:
    prior = prior or {}
    return {
        "dso": _days_metric(
            current.get("accounts_receivable"),
            prior.get("accounts_receivable"),
            income.get("revenue"),
            days,
        ),
        "dio": _days_metric(
            current.get("inventory"),
            prior.get("inventory"),
            income.get("cogs"),
            days,
        ),
        "dpo": _days_metric(
            current.get("accounts_payable"),
            prior.get("accounts_payable"),
            income.get("cogs"),
            days,
        ),
    }
