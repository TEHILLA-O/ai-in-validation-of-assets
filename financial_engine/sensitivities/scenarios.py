"""Scenario cases.

Bull and bear cases are complete assumption sets. They are not haircuts applied
to a finished enterprise value. Default offsets are a starting point; every
rate remains editable.
"""

from __future__ import annotations

import copy
from decimal import Decimal

from financial_engine.model import Assumptions, CostDriver, SegmentDriver

BULL = "Bull"
BASE = "Base"
BEAR = "Bear"


def _floor_rate(value: Decimal, lower: Decimal = Decimal(0), upper: Decimal = Decimal("0.95")) -> Decimal:
    return min(max(value, lower), upper)


def _shift_cost(driver: CostDriver, delta: Decimal) -> None:
    if driver.flat_pct is not None:
        driver.flat_pct = _floor_rate(driver.flat_pct + delta)
    driver.pct_of_revenue = {key: _floor_rate(value + delta) for key, value in driver.pct_of_revenue.items()}


def _shift_days(mapping: dict[str, Decimal], flat: Decimal | None, delta: Decimal) -> tuple[dict[str, Decimal], Decimal | None]:
    shifted = {key: max(Decimal(0), value + delta) for key, value in mapping.items()}
    flat_shifted = None if flat is None else max(Decimal(0), flat + delta)
    return shifted, flat_shifted


def derive_case(base: Assumptions, name: str) -> Assumptions:
    """Copy the base case and apply an operating offset.

    Direction is +1 for bull and -1 for bear. WACC, terminal assumptions and
    the explicit forecast horizon are copied unchanged so the comparison is
    about operations unless the user later edits them.
    """
    scenario = copy.deepcopy(base)
    scenario.name = name
    if name == BASE:
        return scenario
    direction = Decimal(1) if name == BULL else Decimal(-1)
    growth_delta = Decimal("0.02") * direction
    cogs_delta = Decimal("-0.015") * direction
    margin_delta = Decimal("0.015") * direction
    dso_delta = Decimal(-5) * direction
    dio_delta = Decimal(-2) * direction
    dpo_delta = Decimal(2) * direction

    scenario.growth_rates = {key: value + growth_delta for key, value in scenario.growth_rates.items()}
    scenario.volume_growth = {key: value + growth_delta for key, value in scenario.volume_growth.items()}
    for segment in scenario.segments:
        segment.growth_rates = {key: value + growth_delta for key, value in segment.growth_rates.items()}
        segment.volume_growth = {key: value + growth_delta for key, value in segment.volume_growth.items()}

    if scenario.cost_mode == "line_item" and "cogs" in scenario.costs:
        _shift_cost(scenario.costs["cogs"], cogs_delta)
    if scenario.cost_mode == "margin_target":
        scenario.gross_margin = {
            key: _floor_rate(value - cogs_delta, Decimal("0.01"), Decimal("0.95"))
            for key, value in scenario.gross_margin.items()
        }
        scenario.ebitda_margin = {
            key: _floor_rate(value + margin_delta, Decimal("-0.20"), Decimal("0.80"))
            for key, value in scenario.ebitda_margin.items()
        }
    scenario.dso, scenario.flat_dso = _shift_days(scenario.dso, scenario.flat_dso, dso_delta)
    scenario.dio, scenario.flat_dio = _shift_days(scenario.dio, scenario.flat_dio, dio_delta)
    scenario.dpo, scenario.flat_dpo = _shift_days(scenario.dpo, scenario.flat_dpo, dpo_delta)
    scenario.notes = (
        f"{name} case starts from the base assumptions. Growth {growth_delta}, COGS percentage {cogs_delta}, "
        f"DSO {dso_delta} days, DIO {dio_delta} days, DPO {dpo_delta} days. "
        "Enterprise value is not scaled by a fixed percentage."
    )
    return scenario


def ensure_default_cases(base: Assumptions, provided: dict[str, Assumptions]) -> dict[str, Assumptions]:
    cases = {BASE: copy.deepcopy(base)}
    cases[BASE].name = BASE
    for name in (BULL, BEAR):
        if name in provided:
            cases[name] = copy.deepcopy(provided[name])
            cases[name].name = name
        else:
            cases[name] = derive_case(base, name)
    for name, case in provided.items():
        if name not in cases:
            custom = copy.deepcopy(case)
            custom.name = name
            cases[name] = custom
    return cases


def _keep_types_used() -> None:
    _ = (CostDriver, SegmentDriver)
