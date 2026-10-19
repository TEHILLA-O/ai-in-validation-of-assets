"""Independent reference calculations for Northline Industrial.

The expected figures below are written out from the accounting identities.
They do not call the engine to produce the expected value.
"""

from __future__ import annotations

import copy
from datetime import date
from decimal import Decimal

import pytest

from financial_engine.engine import run_model
from financial_engine.reference.northline import northline_model


def _year(result, period_id):
    return next(year for year in result.years if year.period_id == period_id)


def test_historical_statements_balance_without_a_plug():
    result = run_model(northline_model(), include_scenarios=False, include_sensitivities=False)
    for period in ("2022", "2023", "2024"):
        year = _year(result, period)
        assets = sum(
            year.balance[key]
            for key in (
                "cash",
                "accounts_receivable",
                "inventory",
                "other_current_assets",
                "ppe_net",
                "intangibles",
                "other_non_current_assets",
            )
        )
        claims = sum(
            year.balance[key]
            for key in (
                "accounts_payable",
                "accrued_expenses",
                "other_operating_cl",
                "short_term_debt",
                "revolver",
                "long_term_debt",
                "other_liabilities",
                "share_capital",
                "apic",
                "retained_earnings",
                "other_equity",
            )
        )
        assert assets == claims


def test_first_forecast_year_matches_hand_calculation():
    result = run_model(northline_model(), include_scenarios=False, include_sensitivities=False)
    year = _year(result, "2025")
    assert year.income["revenue"] == Decimal("110000")
    assert year.income["cogs"] == Decimal("66000")
    assert year.income["gross_profit"] == Decimal("44000")
    assert year.income["ebitda"] == Decimal("16500")
    assert year.income["depreciation"] == Decimal("4550")
    assert year.income["amortisation"] == Decimal("1000")
    assert year.income["ebit"] == Decimal("10950")
    assert year.income["interest_expense"] == Decimal("1200")
    assert year.income["interest_income"] == Decimal("160")
    assert year.income["ebt"] == Decimal("9910")
    assert year.income["tax_expense"] == Decimal("2477.5")
    assert year.income["net_income"] == Decimal("7432.5")
    assert year.working_capital["accounts_receivable"] == Decimal("11000")
    assert year.working_capital["inventory"] == Decimal("6600")
    assert year.working_capital["accounts_payable"] == Decimal("6600")
    assert year.working_capital["operating_nwc"] == Decimal("12100")
    assert year.working_capital["change_in_nwc"] == Decimal("1100")
    assert year.ppe["closing"] == Decimal("40950")
    assert year.balance["intangibles"] == Decimal("4000")
    assert year.cash_flow["dividends"] == Decimal("2229.75")
    assert year.balance["cash"] == Decimal("11152.75")
    assert year.balance["retained_earnings"] == Decimal("25202.75")
    assert year.balance["total_assets"] == year.balance["total_liabilities_and_equity"]
    assert year.balance["total_assets"] == Decimal("78902.75")
    assert year.ufcf["ufcf"] == Decimal("7162.5")
    assert year.income["interest_expense"] not in (year.ufcf["ufcf"],)


def test_second_year_depreciation_uses_vintage_layers():
    result = run_model(northline_model(), include_scenarios=False, include_sensitivities=False)
    year = _year(result, "2026")
    # Existing layer still charges 4,000. The 2025 capex layer charges 550.
    # 2026 capex is 5% of 121,000 = 6,050, and its first full-year charge is 605.
    assert year.income["revenue"] == Decimal("121000")
    assert year.income["depreciation"] == Decimal("5155")


def test_wacc_and_dcf_match_an_independent_formula():
    result = run_model(northline_model(), include_scenarios=False, include_sensitivities=False)
    wacc = Decimal("9.45") / Decimal("110")
    assert result.wacc is not None
    assert result.wacc.cost_of_equity == Decimal("0.095")
    assert result.wacc.after_tax_cost_of_debt == Decimal("0.045")
    assert result.wacc.equity_weight == Decimal("90") / Decimal("110")
    assert result.wacc.wacc == wacc

    forecast = [year for year in result.years if year.is_forecast]
    explicit = Decimal(0)
    for index, year in enumerate(forecast, start=1):
        explicit += year.ufcf["ufcf"] / (Decimal(1) + wacc) ** index
    final = forecast[-1].ufcf["ufcf"]
    growth = Decimal("0.02")
    terminal = final * (Decimal(1) + growth) / (wacc - growth)
    pv_terminal = terminal / (Decimal(1) + wacc) ** len(forecast)
    enterprise = explicit + pv_terminal
    assert result.dcf is not None
    assert result.dcf.pv_explicit == explicit
    assert result.dcf.terminal_value == terminal
    assert result.dcf.enterprise_value == enterprise
    assert result.equity is not None
    assert result.equity.excess_cash == Decimal("6000")
    assert result.equity.interest_bearing_debt == Decimal("20000")
    assert result.equity.equity_value == enterprise - Decimal("14000")
    assert result.equity.value_per_share == (enterprise - Decimal("14000")) / Decimal("10000")
    assert result.dcf.cross_check_enterprise_value is not None
    assert result.dcf.cross_check_enterprise_value != result.dcf.enterprise_value


def test_every_forecast_year_balances_and_cash_ties():
    result = run_model(northline_model(), include_scenarios=False, include_sensitivities=False)
    hard_failures = [
        check
        for check in result.checks
        if check.status == "fail" and check.severity == "fail"
    ]
    assert hard_failures == []
    previous_cash = None
    for year in result.years:
        if year.is_forecast:
            assert year.balance["total_assets"] == year.balance["total_liabilities_and_equity"]
            assert year.balance["cash"] == year.cash_flow["closing_cash"]
            assert previous_cash == year.cash_flow["opening_cash"]
        previous_cash = year.balance["cash"]


def test_growth_changes_the_statements_and_wacc_does_not_change_history():
    base = run_model(northline_model(), include_scenarios=False, include_sensitivities=False)
    higher = northline_model()
    for key in higher.assumptions.growth_rates:
        higher.assumptions.growth_rates[key] = Decimal("0.20")
    grown = run_model(higher, include_scenarios=False, include_sensitivities=False)
    assert _year(grown, "2025").income["revenue"] > _year(base, "2025").income["revenue"]
    assert _year(grown, "2025").income["ebit"] > _year(base, "2025").income["ebit"]
    assert _year(grown, "2025").working_capital["operating_nwc"] != _year(base, "2025").working_capital["operating_nwc"]
    assert _year(grown, "2025").ufcf["ufcf"] != _year(base, "2025").ufcf["ufcf"]
    assert grown.dcf.enterprise_value != base.dcf.enterprise_value
    assert _year(grown, "2024").income["revenue"] == _year(base, "2024").income["revenue"]

    cheaper = northline_model()
    cheaper.assumptions.wacc.risk_free_rate = Decimal("0.03")
    discounted = run_model(cheaper, include_scenarios=False, include_sensitivities=False)
    assert discounted.dcf.enterprise_value > base.dcf.enterprise_value
    assert _year(discounted, "2024").income == _year(base, "2024").income
    assert _year(discounted, "2025").income["revenue"] == _year(base, "2025").income["revenue"]


def test_debt_rate_changes_interest_financing_and_cash_but_not_ufcf_interest_deduction():
    base = run_model(northline_model(), include_scenarios=False, include_sensitivities=False)
    changed = northline_model()
    changed.assumptions.interest_rate = Decimal("0.10")
    changed.assumptions.repayments = {year: Decimal("2000") for year in changed.assumptions.repayments}
    result = run_model(changed, include_scenarios=False, include_sensitivities=False)
    assert _year(result, "2025").income["interest_expense"] == Decimal("2000")
    assert _year(result, "2025").cash_flow["repayments"] == Decimal("2000")
    assert _year(result, "2025").balance["short_term_debt"] == Decimal("2000")
    assert _year(result, "2025").balance["cash"] != _year(base, "2025").balance["cash"]
    # UFCF still excludes interest. A higher interest expense lowers net income, not the UFCF definition.
    assert _year(result, "2025").ufcf["ebit"] == _year(base, "2025").ufcf["ebit"]


def test_scenarios_recalculate_rather_than_scaling_value():
    result = run_model(northline_model(), include_sensitivities=False)
    bull = result.scenarios["Bull"]
    bear = result.scenarios["Bear"]
    assert bull.dcf.enterprise_value > result.dcf.enterprise_value > bear.dcf.enterprise_value
    assert _year(bull, "2025").income["revenue"] > _year(result, "2025").income["revenue"]
    assert _year(bear, "2025").income["revenue"] < _year(result, "2025").income["revenue"]
    ratio = bull.dcf.enterprise_value / result.dcf.enterprise_value
    assert ratio != Decimal("1.1")


def test_sensitivity_centre_matches_the_full_valuation_and_invalid_cells_are_marked():
    model = northline_model()
    result = run_model(model)
    tables = {table.name: table for table in result.sensitivities}
    wacc_growth = tables["WACC versus terminal growth"]
    centre = wacc_growth.values[wacc_growth.base_row][wacc_growth.base_column]
    assert Decimal(centre) == result.dcf.enterprise_value
    assert "invalid" in {status for row in wacc_growth.statuses for status in row} or any(
        Decimal(row) <= Decimal(column)
        for row in wacc_growth.row_keys
        for column in wacc_growth.column_keys
    )
    growth_margin = tables["Revenue growth versus EBITDA margin"]
    centre_margin = growth_margin.values[growth_margin.base_row][growth_margin.base_column]
    assert Decimal(centre_margin) == result.dcf.enterprise_value
    capex = tables["CapEx versus revenue growth"]
    assert Decimal(capex.values[capex.base_row][capex.base_column]) == result.dcf.enterprise_value
    working = tables["Working capital versus valuation"]
    assert Decimal(working.values[working.base_row][working.base_column]) == result.dcf.enterprise_value


def test_wacc_equal_to_growth_does_not_invent_a_terminal_value():
    model = northline_model()
    model.assumptions.valuation.terminal_growth = Decimal("0.50")
    result = run_model(model, include_scenarios=False, include_sensitivities=False)
    assert result.dcf.terminal_value is None
    assert result.dcf.enterprise_value is None
    assert any(check.name == "Terminal growth is below WACC" and check.status == "fail" for check in result.checks)


def test_invalid_share_count_suppresses_per_share_value():
    model = northline_model()
    model.assumptions.valuation.diluted_shares = Decimal(0)
    result = run_model(model, include_scenarios=False, include_sensitivities=False)
    assert result.equity.value_per_share is None
    assert result.dcf.enterprise_value is not None


def test_currency_mismatch_and_missing_cash_block_the_forecast():
    mismatch = northline_model()
    mismatch.historical[0].currency = "EUR"
    result = run_model(mismatch, include_scenarios=False, include_sensitivities=False)
    assert any("currency" in error.lower() for error in result.blocking_errors)
    assert not any(year.is_forecast for year in result.years)

    missing = northline_model()
    missing.historical[-1].balance["cash"] = None
    blocked = run_model(missing, include_scenarios=False, include_sensitivities=False)
    assert any("cash" in error.lower() for error in blocked.blocking_errors)


def test_partial_statement_does_not_treat_a_missing_figure_as_zero():
    model = northline_model()
    model.historical[1].income["revenue"] = None
    model.historical[1].statement_complete = False
    result = run_model(model, include_scenarios=False, include_sensitivities=False)
    year = _year(result, "2023")
    assert year.income["revenue"] is None
    assert year.ratios["revenue_growth"] is None
    assert year.ratios["gross_margin"] is None


def test_period_length_changes_the_receivable_balance():
    model = northline_model()
    model.assumptions.days_by_year["2025"] = 366
    result = run_model(model, include_scenarios=False, include_sensitivities=False)
    expected = Decimal("110000") * Decimal("36.5") / Decimal(366)
    assert _year(result, "2025").working_capital["accounts_receivable"] == expected


def test_negative_ebit_creates_no_tax_and_a_loss_carryforward():
    model = northline_model()
    model.assumptions.forecast_years = [2025]
    model.assumptions.costs["cogs"].flat_pct = Decimal("1.20")
    result = run_model(model, include_scenarios=False, include_sensitivities=False)
    year = _year(result, "2025")
    assert year.income["ebit"] < 0
    assert year.income["tax_expense"] == 0
    assert year.ufcf["unlevered_tax"] == 0
    assert year.balance["total_assets"] == year.balance["total_liabilities_and_equity"]


def test_average_interest_revolver_still_balances():
    model = northline_model()
    model.assumptions.forecast_years = [2025]
    model.assumptions.interest_basis = "average"
    model.assumptions.minimum_cash = Decimal("30000")
    model.assumptions.dividend_payout = Decimal("0.90")
    result = run_model(model, include_scenarios=False, include_sensitivities=False)
    year = _year(result, "2025")
    assert result.converged
    assert year.balance["cash"] >= Decimal("30000")
    assert year.balance["revolver"] > 0
    opening = Decimal("20000")
    closing = year.balance["short_term_debt"] + year.balance["long_term_debt"] + year.balance["revolver"]
    assert year.income["interest_expense"] == Decimal("0.06") * (opening + closing) / Decimal(2)
    assert year.balance["total_assets"] == year.balance["total_liabilities_and_equity"]


def test_zero_debt_uses_the_cost_of_equity_as_wacc():
    model = northline_model()
    model.assumptions.wacc.capital_structure_method = "market"
    model.assumptions.wacc.market_value_debt = Decimal(0)
    model.assumptions.wacc.market_value_equity = Decimal("90000")
    result = run_model(model, include_scenarios=False, include_sensitivities=False)
    assert result.wacc.wacc == result.wacc.cost_of_equity
    assert result.wacc.debt_weight == 0


def test_book_proxy_is_labelled_and_not_described_as_market_value():
    model = northline_model()
    model.assumptions.wacc.capital_structure_method = "book_proxy"
    result = run_model(model, include_scenarios=False, include_sensitivities=False)
    assert result.wacc.capital_structure_method == "book_proxy"
    assert any("not market" in warning.lower() for warning in result.wacc.warnings)
    assert result.wacc.market_value_equity == Decimal("45000")
    assert result.wacc.market_value_debt == Decimal("20000")


def test_suggestions_are_not_copied_into_assumptions():
    model = northline_model()
    result = run_model(model, include_scenarios=False, include_sensitivities=False)
    assert "dso" in result.suggestions
    assert model.assumptions.flat_dso == Decimal("36.5")
    assert "not applied" in result.suggestions["dso"].lower() or "you enter" in result.suggestions["dso"].lower()


def test_mid_year_discounting_is_documented_and_changes_value():
    end_year = run_model(northline_model(), include_scenarios=False, include_sensitivities=False)
    model = northline_model()
    model.assumptions.valuation.discount_convention = "mid"
    mid = run_model(model, include_scenarios=False, include_sensitivities=False)
    assert mid.dcf.convention == "mid"
    assert any("Mid-year" in note for note in mid.dcf.warnings)
    assert mid.dcf.enterprise_value != end_year.dcf.enterprise_value


def test_no_share_price_means_no_invented_upside():
    result = run_model(northline_model(), include_scenarios=False, include_sensitivities=False)
    assert result.equity.share_price is None
    assert result.equity.upside is None


def test_margin_mode_ignores_conflicting_line_item_drivers():
    model = northline_model()
    model.assumptions.forecast_years = [2025]
    model.assumptions.cost_mode = "margin_target"
    model.assumptions.gross_margin = {"2025": Decimal("0.40")}
    model.assumptions.ebitda_margin = {"2025": Decimal("0.20")}
    result = run_model(model, include_scenarios=False, include_sensitivities=False)
    year = _year(result, "2025")
    assert year.income["ebitda"] == Decimal("22000")
    assert any("not applied" in note.lower() for note in result.drivers_ignored)


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("opening", "opening"),
    ],
)
def test_valuation_date_is_the_stated_date(method, expected):
    result = run_model(northline_model(), include_scenarios=False, include_sensitivities=False)
    assert result.currency == "USD"
    assert result.synthetic is True
    assert "SYNTHETIC" in result.synthetic_notice
    assert date(2024, 12, 31).isoformat() == "2024-12-31"
    assert expected == method or method == "opening"
