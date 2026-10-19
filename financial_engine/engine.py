"""Orchestrates projection, WACC, DCF, scenarios and sensitivities.

Scenario and sensitivity runs call the same projection. They do not apply a
percentage to a finished enterprise value.
"""

from __future__ import annotations

import copy

from financial_engine.dcf.valuation import equity_bridge, value_forecast
from financial_engine.lines import COST_PRECEDENCE, DEPENDENCY_GRAPH, ENGINE_VERSION
from financial_engine.model import CompanyModel, ModelResult, Trace
from financial_engine.precision import cagr
from financial_engine.sensitivities.analysis import build_sensitivities
from financial_engine.sensitivities.scenarios import BASE, ensure_default_cases
from financial_engine.statements.project import project
from financial_engine.validation.checks import run_checks
from financial_engine.wacc.calculator import calculate_wacc


def _fmt(value) -> str:
    if value is None:
        return "missing"
    return format(value, "f")


def suggestions_from_history(result_years) -> dict[str, str]:
    """Observed history. Nothing here is copied into the forecast assumptions."""
    historical = [year for year in result_years if not year.is_forecast]
    if not historical:
        return {}
    last = historical[-1]
    suggestions: dict[str, str] = {}
    labels = {
        "gross_margin": "Last historical gross margin",
        "ebitda_margin": "Last historical EBITDA margin",
        "operating_margin": "Last historical operating margin",
        "net_margin": "Last historical net margin",
        "effective_tax_rate": "Last historical effective tax rate",
    }
    for key, label in labels.items():
        value = last.ratios.get(key)
        if value is not None:
            suggestions[key] = f"{label}: {_fmt(value)}. This is not applied unless you copy it into an assumption."
    for key, label in (("dso", "DSO"), ("dio", "DIO"), ("dpo", "DPO")):
        value = last.working_capital.get(key)
        if value is not None:
            suggestions[key] = (
                f"Last historical {label}: {_fmt(value)} days, using the labelled historical convention. "
                "The forecast uses the days assumption you enter."
            )
    if len(historical) >= 2:
        start_revenue = historical[0].income.get("revenue")
        end_revenue = historical[-1].income.get("revenue")
        if start_revenue is not None and end_revenue is not None:
            rate = cagr(start_revenue, end_revenue, len(historical) - 1)
            if rate is not None:
                suggestions["historical_revenue_cagr"] = (
                    f"Historical revenue CAGR: {_fmt(rate)}. It is not used as the forecast growth rate."
                )
    return suggestions


def assemble(model: CompanyModel) -> ModelResult:
    projection = project(model)
    wacc = None
    dcf = None
    equity = None
    traces = list(projection.traces)
    if not projection.blocking_errors and model.assumptions.valuation is not None:
        wacc = calculate_wacc(model.assumptions, projection.years)
        dcf = value_forecast(projection.years, wacc.wacc, model.assumptions.valuation)
        equity = equity_bridge(projection.years, dcf.enterprise_value, model.assumptions.valuation)
        if wacc.wacc is not None:
            traces.append(Trace(
                id="wacc.wacc",
                label="WACC",
                period=None,
                formula="Equity weight × cost of equity + debt weight × after-tax cost of debt",
                components=[
                    ("cost of equity", _fmt(wacc.cost_of_equity)),
                    ("pre-tax cost of debt", _fmt(wacc.pre_tax_cost_of_debt)),
                    ("after-tax cost of debt", _fmt(wacc.after_tax_cost_of_debt)),
                    ("equity weight", _fmt(wacc.equity_weight)),
                    ("debt weight", _fmt(wacc.debt_weight)),
                    ("structure", wacc.capital_structure_method),
                ],
                result=_fmt(wacc.wacc),
                kind="calculation",
                note=" ".join(wacc.warnings),
            ))
        if dcf.enterprise_value is not None:
            traces.append(Trace(
                id="dcf.enterprise_value",
                label="Enterprise value",
                period=None,
                formula="Present value of explicit unlevered free cash flow + present value of terminal value",
                components=[
                    ("explicit forecast value", _fmt(dcf.pv_explicit)),
                    ("terminal value", _fmt(dcf.terminal_value)),
                    ("present value of terminal value", _fmt(dcf.pv_terminal)),
                    ("method", dcf.terminal_method),
                    ("convention", dcf.convention),
                    ("WACC", _fmt(dcf.wacc)),
                ],
                result=_fmt(dcf.enterprise_value),
                kind="calculation",
                note=" ".join(dcf.warnings),
            ))
        if equity and equity.equity_value is not None:
            traces.append(Trace(
                id="dcf.equity_value",
                label="Equity value",
                period=None,
                formula="Enterprise value − debt − debt-like claims − minority interest − preferred + excess cash + non-operating assets",
                components=[
                    ("enterprise value", _fmt(equity.enterprise_value)),
                    ("interest-bearing debt", _fmt(equity.interest_bearing_debt)),
                    ("excess cash", _fmt(equity.excess_cash)),
                    ("operating cash retained", _fmt(equity.operating_cash)),
                    ("diluted shares", _fmt(equity.diluted_shares)),
                    ("value per share", _fmt(equity.value_per_share)),
                ],
                result=_fmt(equity.equity_value),
                kind="calculation",
                note=" ".join(equity.notes),
            ))
        if dcf.terminal_growth is not None:
            traces.append(Trace(
                id="dcf.terminal_growth",
                label="Terminal growth rate",
                period=None,
                formula="Entered long-run growth rate. It is not estimated from history.",
                components=[("terminal growth", _fmt(dcf.terminal_growth))],
                result=_fmt(dcf.terminal_growth),
                kind="assumption",
            ))
        if dcf.terminal_share_of_ev is not None:
            traces.append(Trace(
                id="dcf.terminal_share",
                label="Terminal value share of enterprise value",
                period=None,
                formula="Present value of terminal value / enterprise value",
                components=[
                    ("present value of terminal value", _fmt(dcf.pv_terminal)),
                    ("enterprise value", _fmt(dcf.enterprise_value)),
                ],
                result=_fmt(dcf.terminal_share_of_ev),
                kind="calculation",
            ))
        forecast_years = [year for year in projection.years if year.is_forecast]
        historical_years = [year for year in projection.years if not year.is_forecast]
        if historical_years and forecast_years:
            start = historical_years[-1].income.get("revenue")
            end = forecast_years[-1].income.get("revenue")
            if start is not None and end is not None:
                rate = cagr(start, end, len(forecast_years))
                if rate is not None:
                    traces.append(Trace(
                        id="forecast.revenue_cagr",
                        label="Projected revenue CAGR",
                        period=None,
                        formula="Compound growth from the last historical revenue to the final forecast revenue",
                        components=[
                            ("last historical revenue", _fmt(start)),
                            ("final forecast revenue", _fmt(end)),
                            ("forecast years", str(len(forecast_years))),
                        ],
                        result=_fmt(rate),
                        kind="calculation",
                        note="This rate is a result. It is not written back into the growth assumptions.",
                    ))
        if forecast_years:
            margin = forecast_years[-1].ratios.get("ebitda_margin")
            if margin is not None:
                traces.append(Trace(
                    id="forecast.ebitda_margin",
                    label="Forecast EBITDA margin",
                    period=forecast_years[-1].period_id,
                    formula="EBITDA / revenue in the final forecast year",
                    components=[
                        ("EBITDA", _fmt(forecast_years[-1].income.get("ebitda"))),
                        ("revenue", _fmt(forecast_years[-1].income.get("revenue"))),
                    ],
                    result=_fmt(margin),
                    kind="calculation",
                ))
        if equity and equity.upside is not None:
            traces.append(Trace(
                id="dcf.upside",
                label="Upside versus the stored share price",
                period=None,
                formula="Value per share / stored share price − 1",
                components=[
                    ("value per share", _fmt(equity.value_per_share)),
                    ("stored share price", _fmt(equity.share_price)),
                ],
                result=_fmt(equity.upside),
                kind="calculation",
                note="No upside is calculated when a dated share price has not been entered.",
            ))
    result = ModelResult(
        engine_version=ENGINE_VERSION,
        company_id=model.company_id,
        company_name=model.name,
        currency=model.currency,
        display_scale=model.display_scale,
        synthetic=model.synthetic,
        synthetic_notice=model.synthetic_notice,
        scenario_name=model.assumptions.name,
        years=projection.years,
        wacc=wacc,
        dcf=dcf,
        equity=equity,
        checks=[],
        traces=traces,
        blocking_errors=list(projection.blocking_errors),
        drivers_applied=list(dict.fromkeys(projection.drivers_applied)),
        drivers_ignored=list(dict.fromkeys(projection.drivers_ignored)),
        suggestions=suggestions_from_history(projection.years),
        cost_mode=model.assumptions.cost_mode,
        cost_precedence_note=COST_PRECEDENCE[model.assumptions.cost_mode],
        dependency_graph=list(DEPENDENCY_GRAPH),
        converged=projection.converged,
        circularity_notes=list(projection.circularity_notes),
    )
    result.checks = run_checks(model, result)
    for error in projection.blocking_errors:
        result.checks.append(
            type(result.checks[0])(
                name="Forecast readiness",
                period=None,
                expected="ready",
                actual=error,
                difference=None,
                status="fail",
                severity="fail",
                cause=error,
            ) if result.checks else _blocking_check(error)
        )
    if projection.blocking_errors and not any(check.name == "Forecast readiness" for check in result.checks):
        for error in projection.blocking_errors:
            result.checks.append(_blocking_check(error))
    return result


def _blocking_check(error: str):
    from financial_engine.model import CheckResult
    return CheckResult(
        name="Forecast readiness",
        period=None,
        expected="ready",
        actual=error,
        difference=None,
        status="fail",
        severity="fail",
        cause=error,
    )


def run_model(
    model: CompanyModel,
    *,
    include_scenarios: bool = True,
    include_sensitivities: bool = True,
) -> ModelResult:
    result = assemble(model)
    if result.blocking_errors:
        return result
    if include_scenarios:
        cases = ensure_default_cases(model.assumptions, model.scenarios)
        for name, assumptions in cases.items():
            if name == BASE:
                continue
            scenario_model = copy.deepcopy(model)
            scenario_model.assumptions = assumptions
            scenario_model.scenarios = {}
            result.scenarios[name] = assemble(scenario_model)
    if include_sensitivities and result.dcf is not None and result.dcf.enterprise_value is not None:
        result.sensitivities = build_sensitivities(model, result.years)
    return result
