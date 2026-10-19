"""Integrity checks.

A failed check is reported with the two sides and the difference. Nothing in
this module rewrites a statement to make the check pass.
"""

from __future__ import annotations

from decimal import Decimal

import numpy as np

from financial_engine.dcf.valuation import _exponents, gordon_terminal_value, present_value
from financial_engine.model import CheckResult, CompanyModel, ModelResult
from financial_engine.precision import cagr


def _dec(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _diff(actual: Decimal | None, expected: Decimal | None) -> str | None:
    if actual is None or expected is None:
        return None
    return format(actual - expected, "f")


def _check(
    name: str,
    period: str | None,
    expected: Decimal | None,
    actual: Decimal | None,
    tolerance: Decimal,
    cause: str,
    *,
    severity: str = "fail",
    hard: bool = True,
) -> CheckResult:
    if expected is None or actual is None:
        status = "fail"
        difference = None
    else:
        difference_value = actual - expected
        difference = format(difference_value, "f")
        status = "pass" if abs(difference_value) <= tolerance else "fail"
    if status == "pass" and severity == "warning":
        # Passed the numeric test. Severity stays informational only when asked.
        pass
    return CheckResult(
        name=name,
        period=period,
        expected=_dec(expected),
        actual=_dec(actual),
        difference=difference if expected is not None and actual is not None else _diff(actual, expected),
        status=status,
        severity="info" if status == "pass" else ("fail" if hard else "warning"),
        cause=cause if status == "fail" else "Within tolerance.",
    )


def _sum_present(values: dict, keys: tuple[str, ...]) -> Decimal | None:
    if any(values.get(key) is None for key in keys):
        return None
    return sum((values[key] for key in keys), Decimal(0))


def run_checks(model: CompanyModel, result: ModelResult) -> list[CheckResult]:
    tolerance = model.assumptions.numeric_tolerance
    checks: list[CheckResult] = []
    currencies = {period.currency for period in model.historical}
    checks.append(
        CheckResult(
            name="Currency consistency",
            period=None,
            expected=next(iter(currencies)) if len(currencies) == 1 else "one currency",
            actual=", ".join(sorted(currencies)) if currencies else "none",
            difference=None,
            status="pass" if len(currencies) <= 1 else "fail",
            severity="info" if len(currencies) <= 1 else "fail",
            cause="Within tolerance." if len(currencies) <= 1 else "Periods were entered in more than one currency.",
        )
    )
    years = [period.year for period in model.historical]
    aligned = years == list(range(years[0], years[0] + len(years))) if years else False
    forecast_ok = True
    if model.historical and model.assumptions.forecast_years:
        forecast_ok = model.assumptions.forecast_years[0] == model.historical[-1].year + 1 and (
            model.assumptions.forecast_years
            == list(range(model.assumptions.forecast_years[0], model.assumptions.forecast_years[0] + len(model.assumptions.forecast_years)))
        )
    checks.append(
        CheckResult(
            name="Period alignment",
            period=None,
            expected="consecutive annual periods",
            actual="aligned" if aligned and forecast_ok else "gap or overlap",
            difference=None,
            status="pass" if aligned and forecast_ok else "fail",
            severity="info" if aligned and forecast_ok else "fail",
            cause="Within tolerance." if aligned and forecast_ok else "Historical or forecast years are not consecutive.",
        )
    )
    missing_sources = 0
    for period in model.historical:
        for statement in (period.income, period.balance):
            for key, value in statement.items():
                if value is None:
                    continue
                if key not in period.sources:
                    missing_sources += 1
    checks.append(
        CheckResult(
            name="Source completeness",
            period=None,
            expected="0",
            actual=str(missing_sources),
            difference=str(missing_sources),
            status="pass" if missing_sources == 0 else "fail",
            severity="info" if missing_sources == 0 else "warning",
            cause="Within tolerance." if missing_sources == 0 else "A reported figure has no source reference.",
        )
    )
    previous = None
    for year in result.years:
        component_assets = _sum_present(year.balance, (
            "cash", "accounts_receivable", "inventory", "other_current_assets",
            "ppe_net", "intangibles", "other_non_current_assets",
        ))
        component_liabilities = _sum_present(year.balance, (
            "accounts_payable", "accrued_expenses", "other_operating_cl",
            "short_term_debt", "revolver", "long_term_debt", "other_liabilities",
        ))
        component_equity = _sum_present(year.balance, (
            "share_capital", "apic", "retained_earnings", "other_equity",
        ))
        if component_assets is not None and year.balance.get("total_assets") is not None:
            checks.append(_check(
                "Reported total assets",
                year.period_id,
                component_assets,
                year.balance.get("total_assets"),
                tolerance,
                "The reported total assets figure does not equal the sum of the asset lines.",
            ))
        if component_liabilities is not None and component_equity is not None:
            checks.append(_check(
                "Balance sheet balances",
                year.period_id,
                component_liabilities + component_equity,
                component_assets,
                tolerance,
                "A balance-sheet movement is missing from the cash flow, or a historical statement was entered out of balance.",
            ))
        cash_cost_keys = ("personnel", "rd", "sales_marketing", "ga", "other_opex")
        if all(year.income.get(key) is not None for key in ("revenue", "cogs", *cash_cost_keys, "ebitda")):
            calculated_ebitda = (
                year.income["revenue"]
                - year.income["cogs"]
                - sum((year.income[key] for key in cash_cost_keys), Decimal(0))
            )
            checks.append(_check(
                "EBITDA reconciles to operating lines",
                year.period_id,
                calculated_ebitda,
                year.income.get("ebitda"),
                tolerance,
                "EBITDA does not equal revenue minus COGS minus cash operating costs.",
            ))
        if all(year.income.get(key) is not None for key in ("ebitda", "depreciation", "amortisation", "impairment", "ebit")):
            checks.append(_check(
                "EBIT reconciles to EBITDA",
                year.period_id,
                year.income["ebitda"] - year.income["depreciation"] - year.income["amortisation"] - year.income["impairment"],
                year.income.get("ebit"),
                tolerance,
                "EBIT does not equal EBITDA minus depreciation, amortisation and impairments.",
            ))
        if all(year.income.get(key) is not None for key in ("ebt", "tax_expense", "net_income")):
            checks.append(_check(
                "Net income reconciles to profit before tax",
                year.period_id,
                year.income["ebt"] - year.income["tax_expense"],
                year.income.get("net_income"),
                tolerance,
                "Net income does not equal profit before tax minus tax expense.",
            ))
        if year.cash_flow:
            opening = year.cash_flow.get("opening_cash")
            change = year.cash_flow.get("net_change_in_cash")
            closing = year.cash_flow.get("closing_cash")
            if opening is not None and change is not None and closing is not None:
                checks.append(_check(
                    "Cash flow reconciliation",
                    year.period_id,
                    opening + change,
                    closing,
                    tolerance,
                    "Closing cash does not equal opening cash plus the net change.",
                ))
                checks.append(_check(
                    "Balance-sheet cash equals cash-flow cash",
                    year.period_id,
                    closing,
                    year.balance.get("cash"),
                    tolerance,
                    "The cash line on the balance sheet is not the cash flow statement's closing cash.",
                ))
            ni_is = year.income.get("net_income")
            ni_cf = year.cash_flow.get("net_income")
            if ni_is is not None and ni_cf is not None:
                checks.append(_check(
                    "Net income consistency",
                    year.period_id,
                    ni_is,
                    ni_cf,
                    tolerance,
                    "Cash flow net income differs from the income statement.",
                ))
        if previous is not None and year.is_forecast:
            expected_re = (
                previous.balance["retained_earnings"]
                + year.income["net_income"]
                - year.cash_flow["dividends"]
            )
            buybacks = year.cash_flow["buybacks"]
            issued = year.cash_flow["equity_issued"]
            apic_change = year.balance["apic"] - previous.balance["apic"]
            buyback_from_apic = issued - apic_change
            buyback_from_re = buybacks - buyback_from_apic
            expected_re -= buyback_from_re
            checks.append(_check(
                "Retained earnings roll-forward",
                year.period_id,
                expected_re,
                year.balance.get("retained_earnings"),
                tolerance,
                "Retained earnings did not roll forward from net income, dividends and buybacks.",
            ))
            expected_debt = (
                previous.balance["short_term_debt"]
                + previous.balance["long_term_debt"]
                + previous.balance["revolver"]
                + year.cash_flow["borrowings"]
                - year.cash_flow["repayments"]
                + year.cash_flow["revolver_draw"]
            )
            actual_debt = (
                year.balance["short_term_debt"]
                + year.balance["long_term_debt"]
                + year.balance["revolver"]
            )
            checks.append(_check(
                "Debt roll-forward",
                year.period_id,
                expected_debt,
                actual_debt,
                tolerance,
                "Closing debt does not equal opening debt plus borrowings minus repayments plus the revolver.",
            ))
            if year.ppe:
                expected_ppe = (
                    year.ppe["opening"]
                    + year.ppe["capex"]
                    - year.ppe["depreciation"]
                    - year.ppe["disposals_nbv"]
                    - year.ppe["impairment"]
                )
                checks.append(_check(
                    "PP&E roll-forward",
                    year.period_id,
                    expected_ppe,
                    year.ppe.get("closing"),
                    tolerance,
                    "Closing PP&E does not equal opening PP&E plus CapEx minus depreciation, disposals and impairments.",
                ))
                checks.append(_check(
                    "PP&E disposals allocated",
                    year.period_id,
                    Decimal(0),
                    year.ppe.get("unallocated_disposal", Decimal(0)) + year.ppe.get("unallocated_impairment", Decimal(0)),
                    tolerance,
                    "Disposals or impairments exceed the net book value of the asset layers.",
                ))
            if year.working_capital.get("opening_nwc") is not None and year.working_capital.get("operating_nwc") is not None:
                expected_change = year.working_capital["operating_nwc"] - year.working_capital["opening_nwc"]
                checks.append(_check(
                    "Working capital consistency",
                    year.period_id,
                    expected_change,
                    year.working_capital.get("change_in_nwc"),
                    tolerance,
                    "The change in operating net working capital does not equal the two closing balances.",
                ))
                expected_cfo = (
                    year.income["net_income"]
                    + year.cash_flow["depreciation_amortisation"]
                    - year.cash_flow["disposal_gain"]
                    + year.cash_flow["other_non_cash"]
                    - expected_change
                )
                checks.append(_check(
                    "Operating cash flow build",
                    year.period_id,
                    expected_cfo,
                    year.cash_flow.get("cash_from_operations"),
                    tolerance,
                    "Operating cash flow does not rebuild from net income, non-cash items and working capital.",
                ))
            if previous.balance.get("cash") is not None and year.cash_flow.get("opening_cash") is not None:
                checks.append(_check(
                    "Cash ties to the prior balance sheet",
                    year.period_id,
                    previous.balance["cash"],
                    year.cash_flow["opening_cash"],
                    tolerance,
                    "Opening cash does not equal the prior period's closing cash.",
                ))
            expected_ufcf = (
                year.ufcf["nopat"]
                + year.ufcf["depreciation_amortisation"]
                - year.ufcf["capex"]
                + year.ufcf["disposal_proceeds"]
                - year.ufcf["change_in_nwc"]
                + year.ufcf["other_adjustments"]
            )
            checks.append(_check(
                "Unlevered free cash flow build",
                year.period_id,
                expected_ufcf,
                year.ufcf.get("ufcf"),
                tolerance,
                "UFCF does not rebuild from NOPAT, D&A, CapEx, disposals and working capital.",
            ))
            if year.income.get("interest_expense") is not None and year.ufcf.get("ufcf") is not None:
                contaminated = expected_ufcf - year.income["interest_expense"]
                differs = abs(contaminated - year.ufcf["ufcf"]) > tolerance
                interest_excluded = differs or year.income["interest_expense"] == 0
                checks.append(CheckResult(
                    name="UFCF excludes interest expense",
                    period=year.period_id,
                    expected="interest not deducted",
                    actual="excluded" if interest_excluded else "included",
                    difference=_dec(year.ufcf["ufcf"] - contaminated),
                    status="pass" if interest_excluded else "fail",
                    severity="info" if interest_excluded else "fail",
                    cause="Within tolerance." if interest_excluded else "UFCF equals a build that deducts interest.",
                ))
        if (
            previous is not None
            and not year.is_forecast
            and previous.balance.get("cash") is not None
            and year.cash_flow.get("opening_cash") is not None
        ):
            checks.append(_check(
                "Cash ties to the prior balance sheet",
                year.period_id,
                previous.balance["cash"],
                year.cash_flow["opening_cash"],
                tolerance,
                "Opening cash does not equal the prior period's closing cash.",
            ))
        previous = year

    if result.wacc and result.wacc.equity_weight is not None and result.wacc.debt_weight is not None:
        checks.append(_check(
            "WACC weights sum to 1",
            None,
            Decimal(1),
            result.wacc.equity_weight + result.wacc.debt_weight,
            tolerance,
            "Equity and debt weights do not sum to 100% of capital.",
        ))
    if result.dcf is not None:
        dcf = result.dcf
        if dcf.wacc is not None and dcf.terminal_growth is not None:
            ok = dcf.wacc > dcf.terminal_growth
            checks.append(CheckResult(
                name="Terminal growth is below WACC",
                period=None,
                expected=f"growth < {_dec(dcf.wacc)}",
                actual=_dec(dcf.terminal_growth),
                difference=_dec(dcf.terminal_growth - dcf.wacc) if dcf.terminal_growth is not None else None,
                status="pass" if ok else "fail",
                severity="info" if ok else "fail",
                cause="Within tolerance." if ok else "Perpetuity growth must be below WACC. No terminal value was forced through.",
            ))
        if dcf.enterprise_value is not None and dcf.pv_explicit is not None and dcf.pv_terminal is not None:
            checks.append(_check(
                "Enterprise value identity",
                None,
                dcf.pv_explicit + dcf.pv_terminal,
                dcf.enterprise_value,
                tolerance,
                "Enterprise value does not equal the present value of explicit cash flows plus the present value of the terminal value.",
            ))
        _float_shadow(result, checks, tolerance)
    shares = model.assumptions.valuation.diluted_shares if model.assumptions.valuation else None
    checks.append(CheckResult(
        name="Share count validity",
        period=None,
        expected="> 0",
        actual=_dec(shares),
        difference=None,
        status="pass" if shares is not None and shares > 0 else "fail",
        severity="info" if shares is not None and shares > 0 else "fail",
        cause="Within tolerance." if shares is not None and shares > 0 else "Diluted shares must be a positive number.",
    ))
    if not result.converged:
        checks.append(CheckResult(
            name="Circularity resolution",
            period=None,
            expected="converged",
            actual="not converged",
            difference=None,
            status="fail",
            severity="fail",
            cause=" ".join(result.circularity_notes) or "The revolver and interest search did not converge.",
        ))
    forecast_years = [year for year in result.years if year.is_forecast]
    historical_years = [year for year in result.years if not year.is_forecast]
    if historical_years and forecast_years:
        start = historical_years[-1].income.get("revenue")
        end = forecast_years[-1].income.get("revenue")
        if start is not None and end is not None:
            rate = cagr(start, end, len(forecast_years))
            if rate is not None:
                checks.append(CheckResult(
                    name="Projected revenue CAGR",
                    period=None,
                    expected="calculated",
                    actual=_dec(rate),
                    difference=None,
                    status="pass",
                    severity="info",
                    cause="CAGR from the last historical year to the final forecast year. It is a result, not an input.",
                ))
    return checks


def _float_shadow(result: ModelResult, checks: list[CheckResult], tolerance: Decimal) -> None:
    """Independent float64 cross-check. It is not the source of the valuation."""
    dcf = result.dcf
    if dcf is None or dcf.wacc is None or dcf.enterprise_value is None or dcf.terminal_method != "gordon":
        return
    if dcf.terminal_growth is None or dcf.wacc <= dcf.terminal_growth:
        return
    forecast = [year for year in result.years if year.is_forecast and year.ufcf.get("ufcf") is not None]
    if not forecast:
        return
    amounts = np.array([float(year.ufcf["ufcf"]) for year in forecast], dtype=float)
    exponents = np.array([float(item) for item in _exponents(len(forecast), dcf.convention)], dtype=float)
    wacc = float(dcf.wacc)
    growth = float(dcf.terminal_growth)
    pv = amounts / (1.0 + wacc) ** exponents
    terminal = float(forecast[-1].ufcf["ufcf"]) * (1.0 + growth) / (wacc - growth)
    pv_terminal = terminal / (1.0 + wacc) ** exponents[-1]
    shadow = Decimal(str(float(pv.sum() + pv_terminal)))
    gap = abs(shadow - dcf.enterprise_value)
    scale = abs(dcf.enterprise_value) if dcf.enterprise_value != 0 else Decimal(1)
    ok = gap / scale <= Decimal("0.000001")
    checks.append(CheckResult(
        name="Float64 shadow of enterprise value",
        period=None,
        expected=_dec(dcf.enterprise_value),
        actual=format(shadow, "f"),
        difference=format(shadow - dcf.enterprise_value, "f"),
        status="pass" if ok else "fail",
        severity="info" if ok else "warning",
        cause="Within tolerance." if ok else "The NumPy float shadow diverged from the Decimal valuation by more than 0.0001%.",
    ))
    _ = (present_value, gordon_terminal_value, tolerance)
