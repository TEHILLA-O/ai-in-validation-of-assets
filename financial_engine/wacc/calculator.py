"""Weighted average cost of capital.

Cost of equity is CAPM plus optional premia that the user has named.
After-tax debt cost uses the marginal tax rate supplied for the tax shield.
Book equity is used only in the explicitly labelled book-proxy method.
"""

from __future__ import annotations

from decimal import Decimal

from financial_engine.model import Assumptions, WaccResult, YearBundle


def _warn_result(message: str, method: str, sources: dict[str, str]) -> WaccResult:
    return WaccResult(
        cost_of_equity=None,
        pre_tax_cost_of_debt=None,
        after_tax_cost_of_debt=None,
        equity_weight=None,
        debt_weight=None,
        wacc=None,
        capital_structure_method=method,
        market_value_equity=None,
        market_value_debt=None,
        components={},
        warnings=[message],
        sources=sources,
    )


def implied_pre_tax_cost(years: list[YearBundle]) -> tuple[Decimal | None, str]:
    historical = [year for year in years if not year.is_forecast]
    if not historical:
        return None, "No historical year is available for an implied borrowing rate."
    last = historical[-1]
    interest = last.income.get("interest_expense")
    closing = _debt(last)
    if interest is None or closing is None:
        return None, "Interest expense or closing debt is missing, so the implied rate is not calculated."
    if len(historical) >= 2:
        opening = _debt(historical[-2])
        if opening is None:
            return None, "Opening debt is missing, so an average-debt implied rate is not calculated."
        average = (opening + closing) / Decimal(2)
        if average == 0:
            return None, "Average interest-bearing debt is zero, so the implied rate is undefined."
        return interest / average, "Interest expense divided by the average of opening and closing interest-bearing debt."
    if closing == 0:
        return None, "Closing debt is zero, so the implied rate is undefined."
    return interest / closing, (
        "Only one historical year is available. The rate uses closing debt, not an average, and is labelled as such."
    )


def _debt(year: YearBundle) -> Decimal | None:
    balance = year.balance
    parts = ("short_term_debt", "long_term_debt", "revolver")
    if any(balance.get(part) is None for part in parts):
        return None
    return balance["short_term_debt"] + balance["long_term_debt"] + balance["revolver"]


def _equity_book(year: YearBundle) -> Decimal | None:
    if year.balance.get("total_equity") is not None:
        return year.balance["total_equity"]
    parts = ("share_capital", "apic", "retained_earnings", "other_equity")
    if any(year.balance.get(part) is None for part in parts):
        return None
    return sum((year.balance[part] for part in parts), Decimal(0))


def calculate_wacc(assumptions: Assumptions, years: list[YearBundle]) -> WaccResult:
    inputs = assumptions.wacc
    if inputs is None:
        return _warn_result("WACC inputs are missing.", "missing", {})
    sources = {
        "risk_free": f"{inputs.risk_free_source} | {inputs.risk_free_as_of or 'date not recorded'}",
        "beta": f"{inputs.beta_source} | {inputs.beta_as_of or 'date not recorded'}",
        "equity_risk_premium": f"{inputs.erp_source} | {inputs.erp_as_of or 'date not recorded'}",
        "country_risk": inputs.country_risk_source,
        "cost_of_debt": f"{inputs.cost_of_debt_source} | {inputs.cost_of_debt_as_of or 'date not recorded'}",
        "capital_structure": f"{inputs.market_value_source} | {inputs.market_value_as_of or 'date not recorded'}",
    }
    warnings: list[str] = []
    if not inputs.risk_free_source or not inputs.beta_source or not inputs.erp_source:
        warnings.append("One or more cost-of-equity inputs has no source. The calculation still uses the entered figures.")
    cost_of_equity = (
        inputs.risk_free_rate
        + inputs.beta * inputs.equity_risk_premium
        + inputs.country_risk_premium
        + inputs.other_equity_adjustment
    )
    if inputs.cost_of_debt_method == "observed":
        pre_tax = inputs.pre_tax_cost_of_debt
        debt_note = "Observed borrowing rate entered by the user."
    elif inputs.cost_of_debt_method == "market":
        pre_tax = inputs.pre_tax_cost_of_debt
        debt_note = "Market-implied borrowing rate entered by the user. It is not a live feed."
    elif inputs.cost_of_debt_method == "implied":
        pre_tax, debt_note = implied_pre_tax_cost(years)
    else:
        return _warn_result("Unknown cost-of-debt method.", inputs.capital_structure_method, sources)
    if pre_tax is None:
        result = _warn_result(debt_note, inputs.capital_structure_method, sources)
        result.cost_of_equity = cost_of_equity
        result.warnings.extend(warnings)
        return result
    if inputs.marginal_tax_rate < 0 or inputs.marginal_tax_rate >= 1:
        return _warn_result("Marginal tax rate must be at least zero and below 100%.", inputs.capital_structure_method, sources)
    after_tax = pre_tax * (Decimal(1) - inputs.marginal_tax_rate)
    historical = [year for year in years if not year.is_forecast]
    last = historical[-1] if historical else None
    equity_value: Decimal | None
    debt_value: Decimal | None
    if inputs.capital_structure_method == "market":
        equity_value = inputs.market_value_equity
        debt_value = inputs.market_value_debt
        if equity_value is None or debt_value is None:
            return _warn_result(
                "Market-value weights need both a market value of equity and a market value of debt.",
                "market",
                sources,
            )
        if equity_value < 0 or debt_value < 0:
            return _warn_result("Market values of capital cannot be negative.", "market", sources)
        warnings.append("Equity weight uses the entered market value, not book equity.")
    elif inputs.capital_structure_method == "target":
        if inputs.target_equity_weight is None or inputs.target_debt_weight is None:
            return _warn_result("Target weights are incomplete.", "target", sources)
        if abs(inputs.target_equity_weight + inputs.target_debt_weight - Decimal(1)) > Decimal("0.000001"):
            return _warn_result("Target equity and debt weights must sum to 1.", "target", sources)
        equity_value = inputs.target_equity_weight
        debt_value = inputs.target_debt_weight
        # Weights are already the values. Total capital is 1 so the weight math below still works
        # if we treat these as the market values of a unit of capital.
    elif inputs.capital_structure_method == "book_proxy":
        if last is None:
            return _warn_result("Book-proxy weights need a historical balance sheet.", "book_proxy", sources)
        equity_value = _equity_book(last)
        debt_value = _debt(last)
        warnings.append(
            "Book equity and book debt are a proxy for private-company weights. They are not market values."
        )
    else:
        return _warn_result("Unknown capital-structure method.", inputs.capital_structure_method, sources)
    if equity_value is None or debt_value is None:
        return _warn_result("Capital values are incomplete.", inputs.capital_structure_method, sources)
    total = equity_value + debt_value
    if total == 0:
        return _warn_result("Total capital is zero, so weights are undefined.", inputs.capital_structure_method, sources)
    equity_weight = equity_value / total
    debt_weight = debt_value / total
    wacc = equity_weight * cost_of_equity + debt_weight * after_tax
    if inputs.capital_structure_method == "market":
        reported_equity, reported_debt = inputs.market_value_equity, inputs.market_value_debt
    elif inputs.capital_structure_method == "book_proxy":
        reported_equity, reported_debt = equity_value, debt_value
    else:
        reported_equity, reported_debt = None, None
    return WaccResult(
        cost_of_equity=cost_of_equity,
        pre_tax_cost_of_debt=pre_tax,
        after_tax_cost_of_debt=after_tax,
        equity_weight=equity_weight,
        debt_weight=debt_weight,
        wacc=wacc,
        capital_structure_method=inputs.capital_structure_method,
        market_value_equity=reported_equity,
        market_value_debt=reported_debt,
        components={
            "risk_free_rate": inputs.risk_free_rate,
            "beta": inputs.beta,
            "equity_risk_premium": inputs.equity_risk_premium,
            "country_risk_premium": inputs.country_risk_premium,
            "other_equity_adjustment": inputs.other_equity_adjustment,
            "marginal_tax_rate": inputs.marginal_tax_rate,
        },
        warnings=warnings + [debt_note],
        sources=sources,
    )
