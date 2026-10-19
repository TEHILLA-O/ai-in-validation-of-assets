"""Operating cost forecasting.

Precedence is explicit. In margin-target mode the line-item drivers are not
applied, even if they are filled in. In line-item mode margin targets are not
applied. The active rule is returned with the result so the interface can show
it beside the editable assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from financial_engine.lines import COST_PRECEDENCE
from financial_engine.model import Assumptions, CostDriver

CASH_COST_LINES = ("personnel", "rd", "sales_marketing", "ga", "other_opex")
MIX_LINES = ("personnel", "rd", "sales_marketing", "ga", "other_opex")


@dataclass
class CostYear:
    cogs: Decimal
    cash_costs: dict[str, Decimal]
    gross_profit: Decimal
    ebitda: Decimal
    applied: list[str] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _historical_amount(history: dict[str, Decimal | None], key: str) -> Decimal:
    value = history.get(key)
    if value is None:
        raise ValueError(
            f"Cannot seed {key} from history because the last historical statement does not contain it. "
            "Enter an explicit assumption. Missing values are not treated as zero."
        )
    return value


def _line_item_cost(
    driver: CostDriver,
    period_id: str,
    revenue: Decimal,
    units: Decimal | None,
    prior_amount: Decimal | None,
    line_name: str,
) -> Decimal:
    if driver.method == "pct_revenue":
        pct = driver.pct_for(period_id)
        if pct is None:
            raise ValueError(f"{line_name} is set to a percentage of revenue but no percentage is stored for {period_id}.")
        return revenue * pct
    if driver.method == "fixed_growth":
        growth = driver.growth_by_period.get(period_id, driver.growth_rate)
        if growth is None:
            raise ValueError(f"{line_name} uses fixed-cost growth but no growth rate is stored.")
        base = prior_amount if prior_amount is not None else driver.base_amount
        if base is None:
            raise ValueError(f"{line_name} uses fixed-cost growth but has no base amount.")
        return base * (Decimal(1) + growth)
    if driver.method == "headcount":
        heads = driver.headcount.get(period_id)
        comp = driver.compensation.get(period_id)
        if heads is None or comp is None:
            raise ValueError(f"{line_name} uses headcount × compensation, and one of those inputs is missing for {period_id}.")
        return heads * comp
    if driver.method == "per_unit":
        unit_cost = driver.cost_per_unit.get(period_id)
        if unit_cost is None:
            raise ValueError(f"{line_name} uses a cost per unit but none is stored for {period_id}.")
        if units is None:
            raise ValueError(
                f"{line_name} uses cost per unit, which needs a volume forecast. "
                "Select price-and-volume revenue or supply units another way."
            )
        return units * unit_cost
    if driver.method == "custom":
        if period_id not in driver.custom_amount:
            raise ValueError(f"{line_name} uses a custom schedule but {period_id} is missing.")
        return driver.custom_amount[period_id]
    raise ValueError(f"Unknown cost method {driver.method}")


def forecast_costs(
    assumptions: Assumptions,
    period_id: str,
    revenue: Decimal,
    units: Decimal | None,
    prior_income: dict[str, Decimal | None],
) -> CostYear:
    if assumptions.cost_mode == "margin_target":
        gross_margin = assumptions.gross_margin.get(period_id)
        ebitda_margin = assumptions.ebitda_margin.get(period_id)
        if gross_margin is None or ebitda_margin is None:
            raise ValueError(f"Margin-target mode requires a gross margin and an EBITDA margin for {period_id}.")
        if ebitda_margin > gross_margin:
            raise ValueError(
                f"EBITDA margin cannot exceed gross margin in {period_id}. "
                "Cash operating costs would have to be negative."
            )
        cogs = revenue * (Decimal(1) - gross_margin)
        ebitda = revenue * ebitda_margin
        cash_opex_total = revenue - cogs - ebitda
        weights = dict(assumptions.margin_mix)
        if not weights:
            weights = {name: Decimal(1) / Decimal(len(MIX_LINES)) for name in MIX_LINES}
        weight_sum = sum(weights.values(), Decimal(0))
        if weight_sum == 0:
            raise ValueError("Margin allocation weights sum to zero.")
        cash_costs = {
            name: cash_opex_total * weights.get(name, Decimal(0)) / weight_sum
            for name in MIX_LINES
        }
        gross_profit = revenue - cogs
        return CostYear(
            cogs=cogs,
            cash_costs=cash_costs,
            gross_profit=gross_profit,
            ebitda=ebitda,
            applied=[
                "cost mode: margin target",
                COST_PRECEDENCE["margin_target"],
            ],
            ignored=[
                "Line-item cost drivers were not applied because margin-target mode is active.",
            ],
            notes=[
                "COGS = revenue × (1 − gross margin).",
                "EBITDA = revenue × EBITDA margin.",
                "Cash operating cost = revenue − COGS − EBITDA, allocated by mix weights.",
            ],
        )

    ignored = []
    if assumptions.gross_margin or assumptions.ebitda_margin:
        ignored.append(
            "Gross-margin and EBITDA-margin targets are stored but were not applied. "
            "Line-item mode is active; margins will be outputs."
        )
    cogs_driver = assumptions.costs.get("cogs")
    if cogs_driver is None:
        raise ValueError("COGS has no cost driver.")
    prior_cogs = prior_income.get("cogs")
    cogs = _line_item_cost(cogs_driver, period_id, revenue, units, prior_cogs, "COGS")
    cash_costs: dict[str, Decimal] = {}
    applied = ["cost mode: line item", COST_PRECEDENCE["line_item"]]
    for name in CASH_COST_LINES:
        driver = assumptions.costs.get(name)
        if driver is None:
            raise ValueError(
                f"{name} has no driver. Add a driver, including an explicit custom amount of zero "
                "if the line is deliberately unused. It will not be invented as zero."
            )
        prior = prior_income.get(name)
        cash_costs[name] = _line_item_cost(driver, period_id, revenue, units, prior, name)
        applied.append(f"{name}: {driver.method}")
    gross_profit = revenue - cogs
    ebitda = gross_profit - sum(cash_costs.values(), Decimal(0))
    return CostYear(
        cogs=cogs,
        cash_costs=cash_costs,
        gross_profit=gross_profit,
        ebitda=ebitda,
        applied=applied,
        ignored=ignored,
        notes=["EBITDA = revenue − COGS − cash operating costs. Depreciation is not included."],
    )
