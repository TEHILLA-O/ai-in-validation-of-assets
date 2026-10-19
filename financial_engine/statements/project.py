"""Integrated three-statement projection.

Cash is the closing balance produced by the cash flow statement. It is not a
plug used to force the balance sheet to agree. If assets do not equal
liabilities and equity, the difference remains visible in the checks.

The minimum-cash revolver is the only balancing mechanism, and only when it is
switched on. Draws and repayments are posted to the revolver line, to financing
cash flow and to interest when the selected interest basis includes them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from financial_engine.forecasts.costs import forecast_costs
from financial_engine.forecasts.revenue import forecast_revenue_year, seed_segment_state
from financial_engine.model import (
    Assumptions,
    CompanyModel,
    HistoricalPeriod,
    PpeLayer,
    Trace,
    YearBundle,
)
from financial_engine.precision import D
from financial_engine.schedules.debt import build_debt
from financial_engine.schedules.ppe import capex_amount, opening_layer, roll_asset
from financial_engine.schedules.tax import tax_and_nol
from financial_engine.schedules.working_capital import (
    historical_days,
    nwc_from_balance,
    project_working_capital,
)

REQUIRED_BALANCE = (
    "cash",
    "accounts_receivable",
    "inventory",
    "other_current_assets",
    "ppe_net",
    "intangibles",
    "other_non_current_assets",
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
REQUIRED_INCOME = (
    "revenue",
    "cogs",
    "personnel",
    "rd",
    "sales_marketing",
    "ga",
    "other_opex",
    "depreciation",
    "amortisation",
    "impairment",
    "interest_income",
    "interest_expense",
    "other_non_operating",
    "tax_expense",
)


@dataclass
class Projection:
    years: list[YearBundle]
    traces: list[Trace]
    blocking_errors: list[str]
    drivers_applied: list[str]
    drivers_ignored: list[str]
    converged: bool = True
    circularity_notes: list[str] = field(default_factory=list)


def _req(values: dict[str, Decimal | None], key: str, where: str) -> Decimal:
    value = values.get(key)
    if value is None:
        raise ValueError(f"{where} is missing {key}. It has not been treated as zero.")
    return value


def _opt_zero_complete(period: HistoricalPeriod, statement: dict[str, Decimal | None], key: str) -> Decimal | None:
    if key in statement and statement[key] is not None:
        return statement[key]
    if period.statement_complete and key not in statement:
        return None
    return statement.get(key)


def compute_income_totals(
    income: dict[str, Decimal | None],
    complete: bool,
) -> tuple[dict[str, Decimal | None], list[str]]:
    """Fill calculated income lines. Missing components stay missing.

    On a statement the user has marked complete, an optional cash-cost line that
    was not reported is set to zero and named in the returned list. The check
    report repeats that list. An incomplete statement is never filled in.
    """
    out = dict(income)
    disclosed_zero: list[str] = []
    revenue = out.get("revenue")
    cogs = out.get("cogs")
    if revenue is not None and cogs is not None and out.get("gross_profit") is None:
        out["gross_profit"] = revenue - cogs
    cash_keys = ("personnel", "rd", "sales_marketing", "ga", "other_opex")
    if complete:
        for key in cash_keys:
            if out.get(key) is None:
                out[key] = Decimal(0)
                disclosed_zero.append(key)
    if revenue is not None and cogs is not None and all(out.get(key) is not None for key in cash_keys):
        calculated_ebitda = revenue - cogs - sum((out[key] for key in cash_keys), Decimal(0))
        # A reported EBITDA is a fact. It is kept and reconciled by the checks.
        if out.get("ebitda") is None:
            out["ebitda"] = calculated_ebitda
    ebitda = out.get("ebitda")
    if (
        out.get("ebit") is None
        and ebitda is not None
        and all(out.get(key) is not None for key in ("depreciation", "amortisation", "impairment"))
    ):
        out["ebit"] = ebitda - out["depreciation"] - out["amortisation"] - out["impairment"]
    if out.get("ebt") is None and all(
        out.get(key) is not None for key in ("ebit", "interest_income", "interest_expense", "other_non_operating")
    ):
        out["ebt"] = out["ebit"] + out["interest_income"] - out["interest_expense"] + out["other_non_operating"]
    if out.get("net_income") is None and out.get("ebt") is not None and out.get("tax_expense") is not None:
        out["net_income"] = out["ebt"] - out["tax_expense"]
    return out, disclosed_zero


def compute_balance_totals(balance: dict[str, Decimal | None]) -> dict[str, Decimal | None]:
    out = dict(balance)
    asset_keys = (
        "cash",
        "accounts_receivable",
        "inventory",
        "other_current_assets",
        "ppe_net",
        "intangibles",
        "other_non_current_assets",
    )
    liability_keys = (
        "accounts_payable",
        "accrued_expenses",
        "other_operating_cl",
        "short_term_debt",
        "revolver",
        "long_term_debt",
        "other_liabilities",
    )
    equity_keys = ("share_capital", "apic", "retained_earnings", "other_equity")
    if all(out.get(key) is not None for key in asset_keys) and out.get("total_assets") is None:
        out["total_assets"] = sum((out[key] for key in asset_keys), Decimal(0))
    if all(out.get(key) is not None for key in liability_keys) and out.get("total_liabilities") is None:
        out["total_liabilities"] = sum((out[key] for key in liability_keys), Decimal(0))
    if all(out.get(key) is not None for key in equity_keys) and out.get("total_equity") is None:
        out["total_equity"] = sum((out[key] for key in equity_keys), Decimal(0))
    if (
        out.get("total_liabilities_and_equity") is None
        and out.get("total_liabilities") is not None
        and out.get("total_equity") is not None
    ):
        out["total_liabilities_and_equity"] = out["total_liabilities"] + out["total_equity"]
    return out


def _ratio(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _ratios(income: dict[str, Decimal | None], prior_revenue: Decimal | None) -> dict[str, Decimal | None]:
    revenue = income.get("revenue")
    return {
        "revenue_growth": _ratio(None if revenue is None or prior_revenue is None else revenue - prior_revenue, prior_revenue),
        "gross_margin": _ratio(income.get("gross_profit"), revenue),
        "ebitda_margin": _ratio(income.get("ebitda"), revenue),
        "operating_margin": _ratio(income.get("ebit"), revenue),
        "net_margin": _ratio(income.get("net_income"), revenue),
        "effective_tax_rate": _ratio(income.get("tax_expense"), income.get("ebt")),
        "interest_coverage": _ratio(income.get("ebit"), income.get("interest_expense")),
    }


def _trace(traces: list[Trace], **kwargs) -> None:
    traces.append(Trace(**kwargs))


def _fmt(value: Decimal | None) -> str:
    if value is None:
        return "missing"
    return format(value, "f")


def readiness_errors(model: CompanyModel) -> list[str]:
    errors: list[str] = []
    if not model.historical:
        errors.append("At least one historical period is required before a forecast can be built.")
        return errors
    currencies = {period.currency for period in model.historical}
    if len(currencies) > 1:
        errors.append(
            "Historical periods use more than one currency ("
            + ", ".join(sorted(currencies))
            + "). Convert them to a single currency before forecasting."
        )
    years = [period.year for period in model.historical]
    if years != sorted(years) or len(years) != len(set(years)):
        errors.append("Historical periods must be unique annual years in chronological order.")
    assumptions = model.assumptions
    if not assumptions.forecast_years:
        errors.append("No forecast years are configured.")
    if assumptions.forecast_years != sorted(assumptions.forecast_years):
        errors.append("Forecast years must be in chronological order.")
    if assumptions.forecast_years and assumptions.forecast_years[0] != model.historical[-1].year + 1:
        errors.append(
            "The first forecast year must be the year immediately after the last historical year. "
            "Stub periods and gaps are not modelled."
        )
    if any(year <= model.historical[-1].year for year in assumptions.forecast_years):
        errors.append("Forecast years overlap the historical periods.")
    last = model.historical[-1]
    for key in REQUIRED_BALANCE:
        if last.balance.get(key) is None:
            errors.append(f"The last historical balance sheet is missing {key}.")
    for key in ("revenue", "cogs"):
        if last.income.get(key) is None:
            errors.append(f"The last historical income statement is missing {key}.")
    if assumptions.valuation is None or assumptions.wacc is None:
        errors.append("WACC inputs and valuation settings are required.")
    return errors


@dataclass
class _Draft:
    income: dict[str, Decimal]
    balance: dict[str, Decimal]
    cash_flow: dict[str, Decimal]
    working_capital: dict[str, Decimal]
    ppe: dict[str, Decimal]
    debt: dict[str, Decimal]
    revenue_bridge: dict[str, Decimal | None]
    ufcf: dict[str, Decimal]
    closing_cash: Decimal
    book_nol: Decimal
    notes: list[str]


def _build_year(
    assumptions: Assumptions,
    period_id: str,
    year: int,
    days: int,
    revenue: Decimal,
    units: Decimal | None,
    revenue_bridge: dict[str, Decimal | None],
    revenue_notes: list[str],
    prior_income: dict[str, Decimal | None],
    prior_balance: dict[str, Decimal],
    ppe_layers: list[PpeLayer],
    intang_layers: list[PpeLayer],
    book_nol: Decimal,
    unlevered_nol: Decimal,
    prior_capex: Decimal | None,
    revolver_flow: Decimal,
    cost_applied: list[str],
    cost_ignored: list[str],
) -> tuple[_Draft, list[PpeLayer], list[PpeLayer], Decimal]:
    costs = forecast_costs(assumptions, period_id, revenue, units, prior_income)
    cost_applied.extend(costs.applied)
    cost_ignored.extend(costs.ignored)
    capex = capex_amount(assumptions, period_id, revenue, prior_capex)
    half = assumptions.depreciation_convention == "half_year"
    disposals = assumptions.disposals_nbv.get(period_id, Decimal(0))
    proceeds = assumptions.disposal_proceeds.get(period_id, Decimal(0))
    impairment = assumptions.impairments.get(period_id, Decimal(0))
    opening_ppe = prior_balance["ppe_net"]
    ppe_layers, ppe_roll = roll_asset(
        ppe_layers,
        capex,
        assumptions.new_ppe_life,
        disposals,
        impairment,
        half,
        f"capex-{period_id}",
    )
    intang_add = assumptions.intangible_additions.get(period_id, Decimal(0))
    opening_intang = prior_balance["intangibles"]
    intang_layers, intang_roll = roll_asset(
        intang_layers,
        intang_add,
        assumptions.intangible_remaining_life,
        Decimal(0),
        Decimal(0),
        False,
        f"intangible-{period_id}",
    )
    depreciation = ppe_roll["depreciation"]
    amortisation = intang_roll["depreciation"]
    wc = project_working_capital(assumptions, period_id, revenue, costs.cogs, days)
    prior_nwc = nwc_from_balance(prior_balance)
    if prior_nwc is None:
        raise ValueError("Opening operating net working capital cannot be calculated from the prior balance sheet.")
    change_nwc = wc["operating_nwc"] - prior_nwc
    debt = build_debt(
        assumptions,
        period_id,
        prior_balance["short_term_debt"],
        prior_balance["long_term_debt"],
        prior_balance["revolver"],
        revolver_flow,
    )
    interest_income = assumptions.interest_income_rate * prior_balance["cash"]
    gain = proceeds - disposals
    other_non_op = assumptions.other_non_operating.get(period_id, Decimal(0)) + gain
    ebit = costs.ebitda - depreciation - amortisation - impairment
    ebt = ebit + interest_income - debt.interest_expense + other_non_op
    tax_rate = assumptions.tax_rate_by_year.get(period_id, assumptions.tax_rate)
    tax, _, book_nol_close = tax_and_nol(ebt, book_nol, tax_rate)
    net_income = ebt - tax
    unlevered_tax, _, unlevered_nol_close = tax_and_nol(ebit, unlevered_nol, tax_rate)
    if period_id in assumptions.dividend_custom:
        dividends = assumptions.dividend_custom[period_id]
    else:
        dividends = assumptions.dividend_payout * net_income if net_income > 0 else Decimal(0)
    issued = assumptions.equity_issued.get(period_id, Decimal(0))
    buybacks = assumptions.buybacks.get(period_id, Decimal(0))
    apic = prior_balance["apic"] + issued
    if buybacks <= apic:
        apic -= buybacks
        retained_buyback = Decimal(0)
    else:
        retained_buyback = buybacks - max(apic, Decimal(0))
        apic = Decimal(0)
    retained = prior_balance["retained_earnings"] + net_income - dividends - retained_buyback
    other_nca_change = assumptions.other_nca_change.get(period_id, Decimal(0))
    other_liab_change = assumptions.other_liability_change.get(period_id, Decimal(0))
    other_non_cash = assumptions.other_non_cash.get(period_id, Decimal(0))
    da_addback = depreciation + amortisation + impairment
    cfo = net_income + da_addback - gain + other_non_cash - change_nwc
    cfi = -capex - intang_add - other_nca_change + proceeds + assumptions.other_investing.get(period_id, Decimal(0))
    cff = (
        debt.borrowings_short
        + debt.borrowings_long
        - debt.repayment_short
        - debt.repayment_long
        + revolver_flow
        + issued
        - buybacks
        - dividends
        + other_liab_change
        + assumptions.other_financing.get(period_id, Decimal(0))
    )
    fx = Decimal(0)
    net_change = cfo + cfi + cff + fx
    closing_cash = prior_balance["cash"] + net_change
    balance = {
        "cash": closing_cash,
        "accounts_receivable": wc["accounts_receivable"],
        "inventory": wc["inventory"],
        "other_current_assets": wc["other_current_assets"],
        "ppe_net": ppe_roll["closing_net"],
        "intangibles": intang_roll["closing_net"],
        "other_non_current_assets": prior_balance["other_non_current_assets"] + other_nca_change,
        "accounts_payable": wc["accounts_payable"],
        "accrued_expenses": wc["accrued_expenses"],
        "other_operating_cl": wc["other_operating_cl"],
        "short_term_debt": debt.closing_short,
        "revolver": debt.closing_revolver,
        "long_term_debt": debt.closing_long,
        "other_liabilities": prior_balance["other_liabilities"] + other_liab_change,
        "share_capital": prior_balance["share_capital"],
        "apic": apic,
        "retained_earnings": retained,
        "other_equity": prior_balance["other_equity"],
    }
    balance = {key: value for key, value in compute_balance_totals(balance).items() if value is not None}
    income = {
        "revenue": revenue,
        "cogs": costs.cogs,
        "gross_profit": costs.gross_profit,
        "personnel": costs.cash_costs["personnel"],
        "rd": costs.cash_costs["rd"],
        "sales_marketing": costs.cash_costs["sales_marketing"],
        "ga": costs.cash_costs["ga"],
        "other_opex": costs.cash_costs["other_opex"],
        "ebitda": costs.ebitda,
        "depreciation": depreciation,
        "amortisation": amortisation,
        "impairment": impairment,
        "ebit": ebit,
        "interest_income": interest_income,
        "interest_expense": debt.interest_expense,
        "other_non_operating": other_non_op,
        "ebt": ebt,
        "tax_expense": tax,
        "net_income": net_income,
    }
    cash_flow = {
        "net_income": net_income,
        "depreciation_amortisation": da_addback,
        "disposal_gain": gain,
        "other_non_cash": other_non_cash,
        "change_in_nwc": change_nwc,
        "cash_from_operations": cfo,
        "capex": capex,
        "intangible_additions": intang_add,
        "disposal_proceeds": proceeds,
        "change_in_other_nca": other_nca_change,
        "other_investing": assumptions.other_investing.get(period_id, Decimal(0)),
        "cash_from_investing": cfi,
        "borrowings": debt.borrowings_short + debt.borrowings_long,
        "repayments": debt.repayment_short + debt.repayment_long,
        "revolver_draw": revolver_flow,
        "equity_issued": issued,
        "buybacks": buybacks,
        "dividends": dividends,
        "change_in_other_liabilities": other_liab_change,
        "other_financing": assumptions.other_financing.get(period_id, Decimal(0)),
        "cash_from_financing": cff,
        "fx_effect": fx,
        "net_change_in_cash": net_change,
        "opening_cash": prior_balance["cash"],
        "closing_cash": closing_cash,
    }
    ufcf_adj = assumptions.ufcf_adjustments.get(period_id, Decimal(0))
    nopat = ebit - unlevered_tax
    ufcf = nopat + da_addback - capex + proceeds - change_nwc + ufcf_adj
    ufcf_lines = {
        "ebit": ebit,
        "unlevered_tax": unlevered_tax,
        "nopat": nopat,
        "depreciation_amortisation": da_addback,
        "capex": capex,
        "disposal_proceeds": proceeds,
        "change_in_nwc": change_nwc,
        "other_adjustments": ufcf_adj,
        "ufcf": ufcf,
    }
    ppe_lines = {
        "opening": opening_ppe,
        "capex": capex,
        "depreciation": depreciation,
        "disposals_nbv": disposals,
        "impairment": impairment,
        "closing": ppe_roll["closing_net"],
        "unallocated_disposal": ppe_roll["unallocated_disposal"],
        "unallocated_impairment": ppe_roll["unallocated_impairment"],
    }
    debt_lines = {
        "opening_short_term": debt.opening_short,
        "opening_long_term": debt.opening_long,
        "opening_revolver": debt.opening_revolver,
        "borrowings": debt.borrowings_short + debt.borrowings_long,
        "repayments": debt.repayment_short + debt.repayment_long,
        "revolver_flow": revolver_flow,
        "closing_short_term": debt.closing_short,
        "closing_long_term": debt.closing_long,
        "closing_revolver": debt.closing_revolver,
        "closing_debt": debt.closing_total,
        "interest_rate": debt.interest_rate,
        "interest_base": debt.interest_base,
        "interest_expense": debt.interest_expense,
        "interest_income": interest_income,
    }
    wc_lines = dict(wc)
    wc_lines["opening_nwc"] = prior_nwc
    wc_lines["change_in_nwc"] = change_nwc
    notes = list(revenue_notes) + list(costs.notes)
    if revolver_flow > 0 and dividends > 0 and closing_cash <= assumptions.minimum_cash + Decimal("0.000001"):
        notes.append("The revolver draw is supporting cash after dividends. This is an explicit financing outcome.")
    draft = _Draft(
        income=income,
        balance=balance,
        cash_flow=cash_flow,
        working_capital=wc_lines,
        ppe=ppe_lines,
        debt=debt_lines,
        revenue_bridge=revenue_bridge,
        ufcf=ufcf_lines,
        closing_cash=closing_cash,
        book_nol=book_nol_close,
        notes=notes,
    )
    return draft, ppe_layers, intang_layers, unlevered_nol_close


def _solve_revolver(
    build,
    assumptions: Assumptions,
    opening_revolver: Decimal,
    opening_cash: Decimal,
) -> tuple[_Draft, list[PpeLayer], list[PpeLayer], Decimal, bool, str]:
    """Find the revolver flow. `build(flow)` returns draft and rolled layers.

    Layers are recomputed inside build, so each trial starts from the same opening
    layers. The caller passes a lambda that copies the opening layers.
    """
    minimum = assumptions.minimum_cash
    if not assumptions.revolver_enabled:
        draft, ppe_layers, intang_layers, unlev = build(Decimal(0))
        note = "Revolver is off. Cash is whatever the cash flow statement produces."
        return draft, ppe_layers, intang_layers, unlev, True, note

    if assumptions.interest_basis == "opening":
        draft0, _, _, _ = build(Decimal(0))
        cash0 = draft0.closing_cash
        full_repay = -opening_revolver
        if cash0 + full_repay >= minimum:
            flow = full_repay
        else:
            flow = minimum - cash0
        draft, ppe_layers, intang_layers, unlev = build(flow)
        return draft, ppe_layers, intang_layers, unlev, True, (
            "Interest is charged on opening debt, so the revolver draw does not change "
            "this year's interest. The draw is solved in one step."
        )

    def cash_at(flow: Decimal) -> Decimal:
        draft, _, _, _ = build(flow)
        return draft.closing_cash

    low = -opening_revolver
    if cash_at(low) >= minimum:
        draft, ppe_layers, intang_layers, unlev = build(low)
        return draft, ppe_layers, intang_layers, unlev, True, (
            "Opening revolver can be repaid in full while cash remains at or above the minimum."
        )
    high = max(minimum - opening_cash, Decimal(0)) + Decimal(1)
    reached = False
    for _ in range(40):
        if cash_at(high) >= minimum:
            reached = True
            break
        high = high * 2 + Decimal(1000)
    if not reached:
        draft, ppe_layers, intang_layers, unlev = build(Decimal(0))
        return draft, ppe_layers, intang_layers, unlev, False, (
            "The revolver could not restore minimum cash within the search bound. "
            "No balancing figure was inserted."
        )
    for _ in range(60):
        mid = (low + high) / 2
        if cash_at(mid) >= minimum:
            high = mid
        else:
            low = mid
    draft, ppe_layers, intang_layers, unlev = build(high)
    if draft.closing_cash + Decimal("0.000001") < minimum:
        return draft, ppe_layers, intang_layers, unlev, False, "Revolver search did not reach minimum cash."
    return draft, ppe_layers, intang_layers, unlev, True, (
        f"Interest basis is {assumptions.interest_basis}. The revolver was solved by a bounded "
        "bisection so interest and cash are consistent. Iteration stops at 60 steps."
    )


def project(model: CompanyModel) -> Projection:
    errors = readiness_errors(model)
    if errors:
        return Projection([], [], errors, [], [], False, [])
    assumptions = model.assumptions
    traces: list[Trace] = []
    applied: list[str] = [f"revenue method: {assumptions.revenue_method}"]
    ignored: list[str] = []
    years: list[YearBundle] = []
    prior_revenue: Decimal | None = None
    prior_balance_for_days: dict[str, Decimal | None] | None = None
    for index, period in enumerate(model.historical):
        income, disclosed_zero = compute_income_totals(dict(period.income), period.statement_complete)
        if disclosed_zero:
            _trace(
                traces,
                id=f"historical.{period.period_id}.disclosed_zero",
                label="Lines set to zero because the statement was marked complete",
                period=period.period_id,
                formula="Optional cash-cost line absent on a complete statement",
                components=[(key, "0") for key in disclosed_zero],
                result="0",
                kind="assumption",
                note="These lines were not reported. Zero is an explicit completeness assumption, not a missing-value fill.",
            )
        if period.statement_complete:
            for key in ("personnel", "rd", "sales_marketing", "ga", "other_opex", "impairment", "other_operating_cl", "revolver", "other_equity"):
                if period.income.get(key) is None and period.balance.get(key) is None:
                    pass
        balance = compute_balance_totals(dict(period.balance))
        cash_flow = dict(period.cash_flow) if period.cash_flow else {key: None for key in ()}
        if period.cash_flow is None:
            cash_flow = {}
        nwc = nwc_from_balance(balance)
        days_info = historical_days(balance, prior_balance_for_days, income, period.days)
        wc = {
            "operating_nwc": nwc,
            "dso": days_info["dso"][0],
            "dio": days_info["dio"][0],
            "dpo": days_info["dpo"][0],
        }
        ratios = _ratios(income, prior_revenue)
        years.append(
            YearBundle(
                period_id=period.period_id,
                year=period.year,
                label=period.label,
                is_forecast=False,
                days=period.days,
                income=income,
                balance=balance,
                cash_flow=cash_flow,
                working_capital=wc,
                ppe={},
                debt={},
                revenue_bridge={},
                ufcf={},
                ratios=ratios,
            )
        )
        for metric, (value, note) in days_info.items():
            _trace(
                traces,
                id=f"historical.{period.period_id}.{metric}",
                label=metric.upper(),
                period=period.period_id,
                formula=note,
                components=[],
                result=_fmt(value),
                kind="fact",
                note=note,
            )
        prior_revenue = income.get("revenue")
        prior_balance_for_days = balance

    last = model.historical[-1]
    prior_balance = {key: _req(last.balance, key, "last historical balance sheet") for key in REQUIRED_BALANCE}
    prior_income, _ = compute_income_totals(dict(last.income), last.statement_complete)
    try:
        ppe_layers = opening_layer("opening-ppe", prior_balance["ppe_net"], assumptions.existing_ppe_remaining_life)
        intang_layers = opening_layer(
            "opening-intangibles",
            prior_balance["intangibles"],
            assumptions.intangible_remaining_life,
        )
    except ValueError as exc:
        return Projection(years, traces, [str(exc)], applied, ignored, False, [])

    book_nol = assumptions.opening_book_nol
    unlevered_nol = assumptions.opening_unlevered_nol
    segment_state = seed_segment_state(assumptions)
    prior_revenue_value = _req(prior_income, "revenue", "last historical income statement")
    prior_units = assumptions.base_units
    prior_price = assumptions.base_price
    prior_customers = None
    prior_capex = None
    if last.cash_flow and last.cash_flow.get("capex") is not None:
        prior_capex = last.cash_flow["capex"]
    converged = True
    circularity: list[str] = []

    for year in assumptions.forecast_years:
        period_id = str(year)
        days = assumptions.days_for(year)
        try:
            revenue_year, segment_state, revenue_ignored = forecast_revenue_year(
                assumptions,
                period_id,
                prior_revenue_value,
                prior_units,
                prior_price,
                segment_state,
                prior_customers,
            )
        except ValueError as exc:
            return Projection(years, traces, [str(exc)], applied, ignored, False, circularity)
        ignored.extend(revenue_ignored)
        opening_ppe = list(ppe_layers)
        opening_intang = list(intang_layers)
        opening_book = book_nol
        opening_unlev = unlevered_nol
        opening_balance = dict(prior_balance)
        opening_income = dict(prior_income)
        capex_seed = prior_capex

        def build(flow: Decimal, _ppe=opening_ppe, _intang=opening_intang, _book=opening_book, _unlev=opening_unlev):
            return _build_year(
                assumptions,
                period_id,
                year,
                days,
                revenue_year.revenue,
                revenue_year.units,
                revenue_year.bridge,
                revenue_year.notes,
                opening_income,
                opening_balance,
                list(_ppe),
                list(_intang),
                _book,
                _unlev,
                capex_seed,
                flow,
                [],
                [],
            )

        try:
            draft, ppe_layers, intang_layers, unlevered_nol, ok, note = _solve_revolver(
                build,
                assumptions,
                opening_balance["revolver"],
                opening_balance["cash"],
            )
        except ValueError as exc:
            return Projection(years, traces, [str(exc)], applied, ignored, False, circularity)
        # Cost notes were collected inside trials and discarded. Rebuild once for the applied list.
        try:
            costs_probe = forecast_costs(
                assumptions, period_id, revenue_year.revenue, revenue_year.units, opening_income
            )
        except ValueError as exc:
            return Projection(years, traces, [str(exc)], applied, ignored, False, circularity)
        applied.extend(f"{period_id}: {item}" for item in costs_probe.applied)
        ignored.extend(f"{period_id}: {item}" for item in costs_probe.ignored)
        circularity.append(f"{period_id}: {note}")
        converged = converged and ok
        ratios = _ratios(draft.income, prior_revenue_value)
        years.append(
            YearBundle(
                period_id=period_id,
                year=year,
                label=f"FY{year}E",
                is_forecast=True,
                days=days,
                income=draft.income,
                balance=draft.balance,
                cash_flow=draft.cash_flow,
                working_capital=draft.working_capital,
                ppe=draft.ppe,
                debt=draft.debt,
                revenue_bridge=draft.revenue_bridge,
                ufcf=draft.ufcf,
                ratios=ratios,
            )
        )
        _trace(
            traces,
            id=f"income.{period_id}.revenue",
            label="Revenue",
            period=period_id,
            formula=revenue_year.notes[0] if revenue_year.notes else "Revenue forecast",
            components=[(key, _fmt(value)) for key, value in revenue_year.bridge.items()],
            result=_fmt(revenue_year.revenue),
            kind="calculation",
        )
        _trace(
            traces,
            id=f"income.{period_id}.ebitda",
            label="EBITDA",
            period=period_id,
            formula="Revenue − COGS − cash operating costs",
            components=[
                ("revenue", _fmt(draft.income["revenue"])),
                ("cogs", _fmt(draft.income["cogs"])),
                ("personnel", _fmt(draft.income["personnel"])),
                ("rd", _fmt(draft.income["rd"])),
                ("sales and marketing", _fmt(draft.income["sales_marketing"])),
                ("general and administrative", _fmt(draft.income["ga"])),
                ("other operating", _fmt(draft.income["other_opex"])),
            ],
            result=_fmt(draft.income["ebitda"]),
            kind="calculation",
        )
        _trace(
            traces,
            id=f"ufcf.{period_id}.ufcf",
            label="Unlevered free cash flow",
            period=period_id,
            formula="EBIT × (1 − tax) via the loss schedule + D&A − CapEx + disposal proceeds − increase in operating NWC",
            components=[(key, _fmt(value)) for key, value in draft.ufcf.items()],
            result=_fmt(draft.ufcf["ufcf"]),
            kind="calculation",
            note="Interest expense is not deducted. Unlevered tax uses EBIT, not profit after interest.",
        )
        book_nol = draft.book_nol
        prior_balance = {key: draft.balance[key] for key in REQUIRED_BALANCE}
        prior_income = draft.income
        prior_revenue_value = draft.income["revenue"]
        prior_units = revenue_year.units if revenue_year.units is not None else prior_units
        prior_price = revenue_year.price if revenue_year.price is not None else prior_price
        prior_customers = revenue_year.customers
        prior_capex = draft.cash_flow["capex"]
        _ = prior_customers

    return Projection(years, traces, [], applied, ignored, converged, circularity)


def historical_capex(period: HistoricalPeriod) -> Decimal | None:
    if period.cash_flow and period.cash_flow.get("capex") is not None:
        return D(period.cash_flow["capex"])
    return None
