"""Sensitivity tables.

WACC and terminal assumptions are re-discounted from the same unlevered cash
flows. Operating sensitivities rebuild the three statements and the DCF.
Cells are never filled by applying a percentage to enterprise value.
"""

from __future__ import annotations

import copy
from decimal import Decimal

from financial_engine.dcf.valuation import equity_bridge, value_forecast
from financial_engine.model import CompanyModel, SensitivityTable, YearBundle
from financial_engine.statements.project import project
from financial_engine.wacc.calculator import calculate_wacc


def _key(value: Decimal) -> str:
    return format(value, "f")


def _table(
    name: str,
    row_label: str,
    column_label: str,
    rows: list[Decimal],
    columns: list[Decimal],
    values: list[list[str | None]],
    statuses: list[list[str]],
    base_row: int | None,
    base_column: int | None,
    note: str,
) -> SensitivityTable:
    return SensitivityTable(
        name=name,
        row_label=row_label,
        column_label=column_label,
        row_keys=[_key(value) for value in rows],
        column_keys=[_key(value) for value in columns],
        values=values,
        statuses=statuses,
        base_row=base_row,
        base_column=base_column,
        note=note,
    )


def _nearest(values: list[Decimal], target: Decimal | None) -> int | None:
    if target is None or not values:
        return None
    return min(range(len(values)), key=lambda index: abs(values[index] - target))


def _axis(centre: Decimal, step: Decimal, count: int = 5) -> list[Decimal]:
    half = count // 2
    return [centre + step * Decimal(offset - half) for offset in range(count)]


def _ev_from_model(model: CompanyModel) -> tuple[str | None, str]:
    projected = project(model)
    if projected.blocking_errors or not projected.converged:
        return None, "invalid"
    wacc = calculate_wacc(model.assumptions, projected.years)
    if model.assumptions.valuation is None or wacc.wacc is None:
        return None, "invalid"
    dcf = value_forecast(projected.years, wacc.wacc, model.assumptions.valuation)
    if dcf.enterprise_value is None:
        return None, "invalid"
    return format(dcf.enterprise_value, "f"), "ok"


def wacc_growth_table(years: list[YearBundle], model: CompanyModel) -> SensitivityTable:
    valuation = model.assumptions.valuation
    wacc = calculate_wacc(model.assumptions, years).wacc or Decimal("0.08")
    growth = valuation.terminal_growth if valuation else Decimal("0.02")
    row_values = _axis(wacc, Decimal("0.005"))
    col_values = _axis(growth, Decimal("0.005"))
    # Keep the constraint visible. A column at the lowest WACC is invalid on that row.
    if max(col_values) < min(row_values):
        col_values = [*col_values, min(row_values)]
    saved_method = valuation.terminal_method
    saved_growth = valuation.terminal_growth
    values: list[list[str | None]] = []
    statuses: list[list[str]] = []
    try:
        for row in row_values:
            value_row: list[str | None] = []
            status_row: list[str] = []
            for column in col_values:
                if row <= column or row <= -1:
                    value_row.append(None)
                    status_row.append("invalid")
                    continue
                valuation.terminal_method = "gordon"
                valuation.terminal_growth = column
                dcf = value_forecast(years, row, valuation)
                value_row.append(format(dcf.enterprise_value, "f") if dcf.enterprise_value is not None else None)
                status_row.append("ok" if dcf.enterprise_value is not None else "invalid")
            values.append(value_row)
            statuses.append(status_row)
    finally:
        valuation.terminal_method = saved_method
        valuation.terminal_growth = saved_growth
    return _table(
        "WACC versus terminal growth",
        "WACC",
        "Terminal growth",
        row_values,
        col_values,
        values,
        statuses,
        _nearest(row_values, wacc),
        _nearest(col_values, growth),
        "Each cell discounts the base-case unlevered free cash flows. Operating forecasts are held constant.",
    )


def wacc_exit_table(years: list[YearBundle], model: CompanyModel) -> SensitivityTable:
    valuation = model.assumptions.valuation
    wacc = calculate_wacc(model.assumptions, years).wacc or Decimal("0.08")
    multiple = valuation.exit_ebitda_multiple or Decimal(8)
    row_values = _axis(wacc, Decimal("0.005"))
    col_values = _axis(multiple, Decimal("0.5"))
    saved_method = valuation.terminal_method
    saved_multiple = valuation.exit_ebitda_multiple
    values: list[list[str | None]] = []
    statuses: list[list[str]] = []
    try:
        for row in row_values:
            value_row = []
            status_row = []
            for column in col_values:
                if column <= 0 or row <= -1:
                    value_row.append(None)
                    status_row.append("invalid")
                    continue
                valuation.terminal_method = "exit_multiple"
                valuation.exit_ebitda_multiple = column
                dcf = value_forecast(years, row, valuation)
                value_row.append(format(dcf.enterprise_value, "f") if dcf.enterprise_value is not None else None)
                status_row.append("ok" if dcf.enterprise_value is not None else "invalid")
            values.append(value_row)
            statuses.append(status_row)
    finally:
        valuation.terminal_method = saved_method
        valuation.exit_ebitda_multiple = saved_multiple
    return _table(
        "WACC versus exit multiple",
        "WACC",
        "Exit EBITDA multiple",
        row_values,
        col_values,
        values,
        statuses,
        _nearest(row_values, wacc),
        _nearest(col_values, multiple),
        "Each cell uses the base-case EBITDA and unlevered free cash flow. This table is a cross-check when the live case uses perpetuity growth.",
    )


def _operating_grid(
    model: CompanyModel,
    name: str,
    row_label: str,
    column_label: str,
    rows: list[Decimal],
    columns: list[Decimal],
    apply_row,
    apply_column,
    note: str,
    base_row: Decimal | None,
    base_column: Decimal | None,
) -> SensitivityTable:
    values: list[list[str | None]] = []
    statuses: list[list[str]] = []
    for row in rows:
        value_row = []
        status_row = []
        for column in columns:
            case = copy.deepcopy(model)
            try:
                apply_row(case, row)
                apply_column(case, column)
                amount, status = _ev_from_model(case)
            except ValueError:
                amount, status = None, "invalid"
            value_row.append(amount)
            status_row.append(status)
        values.append(value_row)
        statuses.append(status_row)
    return _table(
        name,
        row_label,
        column_label,
        rows,
        columns,
        values,
        statuses,
        _nearest(rows, base_row),
        _nearest(columns, base_column),
        note,
    )


def growth_margin_table(model: CompanyModel, years: list[YearBundle]) -> SensitivityTable:
    forecast = [year for year in years if year.is_forecast]
    base_growth = None
    if model.assumptions.growth_rates:
        base_growth = next(iter(model.assumptions.growth_rates.values()))
    base_margin = forecast[0].ratios.get("ebitda_margin") if forecast else None
    base_gross = forecast[0].ratios.get("gross_margin") if forecast else Decimal("0.40")
    if base_growth is None:
        base_growth = Decimal("0.05")
    if base_margin is None:
        base_margin = Decimal("0.15")
    if base_gross is None:
        base_gross = Decimal("0.40")

    def apply_growth(case: CompanyModel, growth: Decimal) -> None:
        case.assumptions.revenue_method = "growth"
        case.assumptions.growth_rates = {str(year): growth for year in case.assumptions.forecast_years}

    def apply_margin(case: CompanyModel, margin: Decimal) -> None:
        case.assumptions.cost_mode = "margin_target"
        case.assumptions.gross_margin = {str(year): base_gross for year in case.assumptions.forecast_years}
        case.assumptions.ebitda_margin = {str(year): margin for year in case.assumptions.forecast_years}
        if margin > base_gross:
            raise ValueError("EBITDA margin exceeds the gross margin held constant in this table.")

    return _operating_grid(
        model,
        "Revenue growth versus EBITDA margin",
        "Revenue growth",
        "EBITDA margin",
        _axis(base_growth, Decimal("0.01")),
        _axis(base_margin, Decimal("0.01")),
        apply_growth,
        apply_margin,
        "Each cell rebuilds revenue, costs, working capital, tax, cash flow and the DCF. "
        "Gross margin is held at the base-case gross margin. Line-item cost drivers are not used inside this table.",
        base_growth,
        base_margin,
    )


def capex_growth_table(model: CompanyModel) -> SensitivityTable:
    base_growth = next(iter(model.assumptions.growth_rates.values()), Decimal("0.05"))
    base_capex = model.assumptions.capex_pct_revenue or Decimal("0.05")

    def apply_capex(case: CompanyModel, capex: Decimal) -> None:
        case.assumptions.capex_method = "pct_revenue"
        case.assumptions.capex_pct_revenue = capex

    def apply_growth(case: CompanyModel, growth: Decimal) -> None:
        case.assumptions.revenue_method = "growth"
        case.assumptions.growth_rates = {str(year): growth for year in case.assumptions.forecast_years}

    return _operating_grid(
        model,
        "CapEx versus revenue growth",
        "CapEx as a percentage of revenue",
        "Revenue growth",
        _axis(base_capex, Decimal("0.01")),
        _axis(base_growth, Decimal("0.01")),
        apply_capex,
        apply_growth,
        "Each cell rebuilds the three statements. CapEx changes depreciation, invested capital and free cash flow.",
        base_capex,
        base_growth,
    )


def working_capital_table(model: CompanyModel) -> SensitivityTable:
    base_dso = model.assumptions.flat_dso or next(iter(model.assumptions.dso.values()), Decimal(36))
    base_dpo = model.assumptions.flat_dpo or next(iter(model.assumptions.dpo.values()), Decimal(36))

    def apply_dso(case: CompanyModel, dso: Decimal) -> None:
        case.assumptions.flat_dso = dso
        case.assumptions.dso = {}

    def apply_dpo(case: CompanyModel, dpo: Decimal) -> None:
        case.assumptions.flat_dpo = dpo
        case.assumptions.dpo = {}

    return _operating_grid(
        model,
        "Working capital versus valuation",
        "Days sales outstanding",
        "Days payable outstanding",
        _axis(base_dso, Decimal(5)),
        _axis(base_dpo, Decimal(5)),
        apply_dso,
        apply_dpo,
        "Each cell rebuilds receivables, payables, the cash flow statement and enterprise value.",
        base_dso,
        base_dpo,
    )


def build_sensitivities(model: CompanyModel, years: list[YearBundle]) -> list[SensitivityTable]:
    if model.assumptions.valuation is None:
        return []
    return [
        wacc_growth_table(years, model),
        wacc_exit_table(years, model),
        growth_margin_table(model, years),
        capex_growth_table(model),
        working_capital_table(model),
    ]


def _bridge_unused() -> None:
    _ = equity_bridge
