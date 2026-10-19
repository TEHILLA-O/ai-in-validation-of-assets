"""Discounted cash flow.

Unlevered free cash flow is discounted at WACC. Interest is not deducted again.
Terminal value uses either perpetuity growth or an exit EBITDA multiple.
The selected method is the one that enters enterprise value. The other method
is reported as a cross-check and does not change the result.
"""

from __future__ import annotations

from decimal import Decimal

from financial_engine.model import DcfResult, EquityBridge, ValuationSettings, YearBundle


def _power(base: Decimal, exponent: Decimal) -> Decimal:
    if base <= 0:
        raise ValueError("The discount base must be positive.")
    return (base.ln() * exponent).exp()


def _exponents(count: int, convention: str) -> list[Decimal]:
    if convention == "end":
        return [Decimal(index) for index in range(1, count + 1)]
    if convention == "mid":
        return [Decimal(index) - Decimal("0.5") for index in range(1, count + 1)]
    raise ValueError(f"Unknown discount convention {convention}.")


def present_value(amount: Decimal, wacc: Decimal, exponent: Decimal) -> Decimal:
    return amount / _power(Decimal(1) + wacc, exponent)


def gordon_terminal_value(final_ufcf: Decimal, wacc: Decimal, growth: Decimal) -> Decimal | None:
    if wacc <= growth:
        return None
    return final_ufcf * (Decimal(1) + growth) / (wacc - growth)


def exit_terminal_value(final_ebitda: Decimal, multiple: Decimal) -> Decimal:
    return final_ebitda * multiple


def implied_growth(terminal_value: Decimal, final_ufcf: Decimal, wacc: Decimal) -> Decimal | None:
    denominator = terminal_value + final_ufcf
    if denominator == 0:
        return None
    return (terminal_value * wacc - final_ufcf) / denominator


def implied_multiple(terminal_value: Decimal, final_ebitda: Decimal) -> Decimal | None:
    if final_ebitda == 0:
        return None
    return terminal_value / final_ebitda


def value_forecast(
    years: list[YearBundle],
    wacc: Decimal | None,
    settings: ValuationSettings,
) -> DcfResult:
    forecast = [year for year in years if year.is_forecast]
    warnings: list[str] = []
    empty = DcfResult(
        convention=settings.discount_convention,
        terminal_method=settings.terminal_method,
        wacc=wacc,
        terminal_growth=settings.terminal_growth,
        exit_multiple=settings.exit_ebitda_multiple,
        discount_factors={},
        pv_ufcf={},
        pv_explicit=None,
        terminal_value=None,
        pv_terminal=None,
        enterprise_value=None,
        terminal_share_of_ev=None,
        implied_exit_multiple=None,
        implied_growth=None,
        cross_check_terminal_value=None,
        cross_check_enterprise_value=None,
        warnings=warnings,
    )
    if wacc is None:
        warnings.append("Enterprise value is not calculated because WACC is unavailable.")
        return empty
    if wacc <= -1:
        warnings.append("WACC must be greater than -100% for the discount factor to be defined.")
        return empty
    if not forecast:
        warnings.append("There is no explicit forecast period to discount.")
        return empty
    if any(year.ufcf.get("ufcf") is None for year in forecast):
        warnings.append("Unlevered free cash flow is missing for at least one forecast year.")
        return empty
    if settings.terminal_growth >= Decimal("0.10"):
        warnings.append("Terminal growth is at least 10%, which is an extreme perpetual assumption.")
    elif settings.terminal_growth > settings.growth_warning_threshold:
        warnings.append(
            "Terminal growth is above the configured long-run warning threshold "
            f"({settings.growth_warning_threshold})."
        )
    if settings.terminal_growth < Decimal("-0.05"):
        warnings.append("Terminal growth is below -5%. Confirm that a perpetual decline is intended.")
    ufcfs = [year.ufcf["ufcf"] for year in forecast]
    final_ufcf = ufcfs[-1]
    final_ebitda = forecast[-1].income.get("ebitda")
    exponents = _exponents(len(forecast), settings.discount_convention)
    factors = {year.period_id: Decimal(1) / _power(Decimal(1) + wacc, exponent) for year, exponent in zip(forecast, exponents)}
    pv_map = {
        year.period_id: present_value(amount, wacc, exponent)
        for year, amount, exponent in zip(forecast, ufcfs, exponents)
    }
    pv_explicit = sum(pv_map.values(), Decimal(0))
    gordon = gordon_terminal_value(final_ufcf, wacc, settings.terminal_growth)
    exit_value = None
    if settings.exit_ebitda_multiple is not None and final_ebitda is not None:
        if settings.exit_ebitda_multiple <= 0:
            warnings.append("The exit multiple must be positive to be used.")
        else:
            exit_value = exit_terminal_value(final_ebitda, settings.exit_ebitda_multiple)
    if settings.terminal_method == "gordon":
        selected = gordon
        cross = exit_value
        if selected is None:
            warnings.append("Perpetuity growth was not applied because WACC is not greater than terminal growth.")
    elif settings.terminal_method == "exit_multiple":
        selected = exit_value
        cross = gordon
        if selected is None:
            warnings.append("The exit-multiple terminal value needs a positive multiple and a final-year EBITDA.")
    else:
        warnings.append("Unknown terminal-value method.")
        selected = None
        cross = None
    pv_terminal = None
    enterprise = None
    share = None
    if selected is not None:
        pv_terminal = present_value(selected, wacc, exponents[-1])
        enterprise = pv_explicit + pv_terminal
        if enterprise != 0:
            share = pv_terminal / enterprise
            if share > settings.terminal_value_warning_share:
                warnings.append(
                    "Most of enterprise value comes from the terminal value. "
                    "The explicit forecast is not the main driver of the result."
                )
    implied_exit = None
    implied_g = None
    if selected is not None and final_ebitda is not None:
        implied_exit = implied_multiple(selected, final_ebitda)
    if selected is not None:
        implied_g = implied_growth(selected, final_ufcf, wacc)
    cross_ev = None
    if cross is not None:
        cross_ev = pv_explicit + present_value(cross, wacc, exponents[-1])
    convention_note = (
        "End-of-year discounting: the first forecast cash flow is one full year from the valuation date."
        if settings.discount_convention == "end"
        else "Mid-year discounting: each cash flow is discounted from the middle of its forecast year."
    )
    warnings.append(convention_note)
    return DcfResult(
        convention=settings.discount_convention,
        terminal_method=settings.terminal_method,
        wacc=wacc,
        terminal_growth=settings.terminal_growth,
        exit_multiple=settings.exit_ebitda_multiple,
        discount_factors=factors,
        pv_ufcf=pv_map,
        pv_explicit=pv_explicit,
        terminal_value=selected,
        pv_terminal=pv_terminal,
        enterprise_value=enterprise,
        terminal_share_of_ev=share,
        implied_exit_multiple=implied_exit,
        implied_growth=implied_g,
        cross_check_terminal_value=cross,
        cross_check_enterprise_value=cross_ev,
        warnings=warnings,
    )


def equity_bridge(
    years: list[YearBundle],
    enterprise_value: Decimal | None,
    settings: ValuationSettings,
) -> EquityBridge:
    notes = [
        "The bridge uses the last historical balance sheet, which is the valuation-date capital structure.",
        "Forecast cash is not added again. Surplus cash is included once, at face value, at the valuation date.",
        "Operating cash is the portion of cash the user has said must stay in the business. It is not added to equity value.",
    ]
    historical = [year for year in years if not year.is_forecast]
    if not historical:
        notes.append("No historical balance sheet is available for the bridge.")
        return EquityBridge(
            enterprise_value=enterprise_value,
            interest_bearing_debt=None,
            debt_like_claims=settings.other_debt_like,
            minority_interest=settings.minority_interest,
            preferred_securities=settings.preferred_securities,
            excess_cash=None,
            operating_cash=None,
            non_operating_assets=settings.non_operating_assets,
            equity_value=None,
            diluted_shares=settings.diluted_shares,
            value_per_share=None,
            share_price=settings.share_price,
            upside=None,
            notes=notes,
        )
    last = historical[-1]
    debt_parts = ("short_term_debt", "long_term_debt", "revolver")
    if any(last.balance.get(part) is None for part in debt_parts) or last.balance.get("cash") is None:
        notes.append("Debt or cash is missing, so equity value is not calculated.")
        debt = None
        excess = None
        operating = None
        equity = None
    else:
        debt = last.balance["short_term_debt"] + last.balance["long_term_debt"] + last.balance["revolver"]
        cash = last.balance["cash"]
        operating = min(settings.operating_cash_requirement, max(cash, Decimal(0)))
        excess = cash - operating
        if excess < 0:
            notes.append(
                "Cash is below the operating-cash requirement. Excess cash is zero. "
                "The shortfall is not reclassified as debt."
            )
            excess = Decimal(0)
        if enterprise_value is None:
            equity = None
        else:
            equity = (
                enterprise_value
                - debt
                - settings.other_debt_like
                - settings.minority_interest
                - settings.preferred_securities
                + excess
                + settings.non_operating_assets
            )
    per_share = None
    if equity is not None and settings.diluted_shares > 0:
        per_share = equity / settings.diluted_shares
    elif settings.diluted_shares <= 0:
        notes.append("Diluted shares are missing or not positive, so a per-share value is not calculated.")
    upside = None
    if per_share is not None and settings.share_price is not None and settings.share_price != 0:
        upside = (per_share - settings.share_price) / settings.share_price
        notes.append(
            "The share price is a user-entered figure"
            + (f" dated {settings.share_price_as_of}." if settings.share_price_as_of else " with no date.")
            + " ValuationLab does not fetch a live market price."
        )
    else:
        notes.append("No share price has been entered, so upside or downside versus the market is not shown.")
    return EquityBridge(
        enterprise_value=enterprise_value,
        interest_bearing_debt=debt,
        debt_like_claims=settings.other_debt_like,
        minority_interest=settings.minority_interest,
        preferred_securities=settings.preferred_securities,
        excess_cash=excess,
        operating_cash=operating,
        non_operating_assets=settings.non_operating_assets,
        equity_value=equity,
        diluted_shares=settings.diluted_shares,
        value_per_share=per_share,
        share_price=settings.share_price,
        upside=upside,
        notes=notes,
    )
