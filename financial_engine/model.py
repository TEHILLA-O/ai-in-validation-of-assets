"""Input and output structures shared by the engine, API and exports.

Amounts are absolute currency units. A thousand or a million is never implied
by the magnitude of a number. `display_scale` only affects presentation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from financial_engine.lines import ENGINE_VERSION
from financial_engine.precision import D

CostMethod = Literal["pct_revenue", "fixed_growth", "headcount", "per_unit", "custom"]
RevenueMethod = Literal["growth", "price_volume", "segment"]
CostMode = Literal["line_item", "margin_target"]
CapexMethod = Literal["pct_revenue", "growth", "fixed", "custom"]
InterestBasis = Literal["opening", "average", "closing"]
DebtCostMethod = Literal["observed", "implied", "market"]
CapitalMethod = Literal["market", "target", "book_proxy"]
TerminalMethod = Literal["gordon", "exit_multiple"]
DiscountConvention = Literal["end", "mid"]
Severity = Literal["fail", "warning", "info"]


def _dmap(raw: dict[str, Any] | None) -> dict[str, Decimal]:
    return {str(k): D(v) for k, v in (raw or {}).items()}


@dataclass
class SourceRef:
    """Provenance stored with an imported or typed figure."""

    source: str
    reported_label: str | None = None
    unit_scale: str = "units"
    adjustment: str | None = None
    imported_at: str | None = None
    accounting_basis: str | None = None


@dataclass
class CostDriver:
    method: CostMethod = "pct_revenue"
    pct_of_revenue: dict[str, Decimal] = field(default_factory=dict)
    flat_pct: Decimal | None = None
    base_amount: Decimal | None = None
    growth_rate: Decimal | None = None
    growth_by_period: dict[str, Decimal] = field(default_factory=dict)
    headcount: dict[str, Decimal] = field(default_factory=dict)
    compensation: dict[str, Decimal] = field(default_factory=dict)
    cost_per_unit: dict[str, Decimal] = field(default_factory=dict)
    custom_amount: dict[str, Decimal] = field(default_factory=dict)

    def pct_for(self, period_id: str) -> Decimal | None:
        if period_id in self.pct_of_revenue:
            return self.pct_of_revenue[period_id]
        return self.flat_pct


@dataclass
class SegmentDriver:
    name: str
    method: Literal["growth", "price_volume"] = "growth"
    base_revenue: Decimal | None = None
    growth_rates: dict[str, Decimal] = field(default_factory=dict)
    base_units: Decimal | None = None
    base_price: Decimal | None = None
    volume_growth: dict[str, Decimal] = field(default_factory=dict)
    price_growth: dict[str, Decimal] = field(default_factory=dict)
    opening_customers: Decimal | None = None
    retention: dict[str, Decimal] = field(default_factory=dict)
    new_customers: dict[str, Decimal] = field(default_factory=dict)
    arpu: dict[str, Decimal] = field(default_factory=dict)


@dataclass
class HistoricalPeriod:
    period_id: str
    label: str
    year: int
    period_end: date
    days: int
    currency: str
    income: dict[str, Decimal | None]
    balance: dict[str, Decimal | None]
    cash_flow: dict[str, Decimal | None] | None = None
    sources: dict[str, SourceRef] = field(default_factory=dict)
    statement_complete: bool = False
    accounting_basis: str = ""


@dataclass
class WaccInputs:
    risk_free_rate: Decimal
    risk_free_source: str
    risk_free_as_of: date | None
    beta: Decimal
    beta_source: str
    beta_as_of: date | None
    equity_risk_premium: Decimal
    erp_source: str
    erp_as_of: date | None
    country_risk_premium: Decimal = Decimal(0)
    country_risk_source: str = "Not applied"
    other_equity_adjustment: Decimal = Decimal(0)
    other_equity_note: str = "Not applied"
    cost_of_debt_method: DebtCostMethod = "observed"
    pre_tax_cost_of_debt: Decimal | None = None
    cost_of_debt_source: str = ""
    cost_of_debt_as_of: date | None = None
    marginal_tax_rate: Decimal = Decimal("0.25")
    capital_structure_method: CapitalMethod = "market"
    market_value_equity: Decimal | None = None
    market_value_debt: Decimal | None = None
    market_value_source: str = ""
    market_value_as_of: date | None = None
    target_equity_weight: Decimal | None = None
    target_debt_weight: Decimal | None = None


@dataclass
class ValuationSettings:
    valuation_date: date
    discount_convention: DiscountConvention = "end"
    terminal_method: TerminalMethod = "gordon"
    terminal_growth: Decimal = Decimal("0.02")
    exit_ebitda_multiple: Decimal | None = None
    diluted_shares: Decimal = Decimal(0)
    share_count_source: str = ""
    share_price: Decimal | None = None
    share_price_as_of: date | None = None
    share_price_source: str = ""
    operating_cash_requirement: Decimal = Decimal(0)
    minority_interest: Decimal = Decimal(0)
    preferred_securities: Decimal = Decimal(0)
    other_debt_like: Decimal = Decimal(0)
    non_operating_assets: Decimal = Decimal(0)
    # Informational threshold. A larger terminal share is a warning, not a plug.
    terminal_value_warning_share: Decimal = Decimal("0.70")
    growth_warning_threshold: Decimal = Decimal("0.04")


@dataclass
class Assumptions:
    name: str = "Base"
    forecast_years: list[int] = field(default_factory=list)
    days_by_year: dict[str, int] = field(default_factory=dict)
    default_days: int = 365
    revenue_method: RevenueMethod = "growth"
    growth_rates: dict[str, Decimal] = field(default_factory=dict)
    base_units: Decimal | None = None
    base_price: Decimal | None = None
    volume_growth: dict[str, Decimal] = field(default_factory=dict)
    price_growth: dict[str, Decimal] = field(default_factory=dict)
    opening_customers: Decimal | None = None
    retention: dict[str, Decimal] = field(default_factory=dict)
    new_customers: dict[str, Decimal] = field(default_factory=dict)
    arpu: dict[str, Decimal] = field(default_factory=dict)
    segments: list[SegmentDriver] = field(default_factory=list)
    cost_mode: CostMode = "line_item"
    gross_margin: dict[str, Decimal] = field(default_factory=dict)
    ebitda_margin: dict[str, Decimal] = field(default_factory=dict)
    margin_mix: dict[str, Decimal] = field(default_factory=dict)
    costs: dict[str, CostDriver] = field(default_factory=dict)
    dso: dict[str, Decimal] = field(default_factory=dict)
    dio: dict[str, Decimal] = field(default_factory=dict)
    dpo: dict[str, Decimal] = field(default_factory=dict)
    flat_dso: Decimal | None = None
    flat_dio: Decimal | None = None
    flat_dpo: Decimal | None = None
    other_ca_pct_revenue: Decimal = Decimal(0)
    accrued_pct_revenue: Decimal = Decimal(0)
    other_ocl_pct_revenue: Decimal = Decimal(0)
    capex_method: CapexMethod = "pct_revenue"
    capex_pct_revenue: Decimal | None = None
    capex_growth: Decimal | None = None
    capex_fixed: Decimal | None = None
    capex_custom: dict[str, Decimal] = field(default_factory=dict)
    existing_ppe_remaining_life: Decimal = Decimal(10)
    new_ppe_life: Decimal = Decimal(10)
    depreciation_convention: Literal["full_year", "half_year"] = "full_year"
    intangible_remaining_life: Decimal = Decimal(5)
    intangible_additions: dict[str, Decimal] = field(default_factory=dict)
    disposals_nbv: dict[str, Decimal] = field(default_factory=dict)
    disposal_proceeds: dict[str, Decimal] = field(default_factory=dict)
    impairments: dict[str, Decimal] = field(default_factory=dict)
    interest_rate: Decimal = Decimal(0)
    revolver_rate: Decimal | None = None
    interest_basis: InterestBasis = "opening"
    interest_income_rate: Decimal = Decimal(0)
    borrowings: dict[str, Decimal] = field(default_factory=dict)
    repayments: dict[str, Decimal] = field(default_factory=dict)
    minimum_cash: Decimal = Decimal(0)
    revolver_enabled: bool = True
    dividend_payout: Decimal = Decimal(0)
    dividend_custom: dict[str, Decimal] = field(default_factory=dict)
    equity_issued: dict[str, Decimal] = field(default_factory=dict)
    buybacks: dict[str, Decimal] = field(default_factory=dict)
    other_nca_change: dict[str, Decimal] = field(default_factory=dict)
    other_liability_change: dict[str, Decimal] = field(default_factory=dict)
    other_non_cash: dict[str, Decimal] = field(default_factory=dict)
    other_investing: dict[str, Decimal] = field(default_factory=dict)
    other_financing: dict[str, Decimal] = field(default_factory=dict)
    other_non_operating: dict[str, Decimal] = field(default_factory=dict)
    ufcf_adjustments: dict[str, Decimal] = field(default_factory=dict)
    tax_rate: Decimal = Decimal("0.25")
    tax_rate_by_year: dict[str, Decimal] = field(default_factory=dict)
    opening_book_nol: Decimal = Decimal(0)
    opening_unlevered_nol: Decimal = Decimal(0)
    wacc: WaccInputs | None = None
    valuation: ValuationSettings | None = None
    numeric_tolerance: Decimal = Decimal("0.000001")
    notes: str = ""

    def days_for(self, year: int) -> int:
        return int(self.days_by_year.get(str(year), self.default_days))

    def rate_for(self, mapping: dict[str, Decimal], year: str, flat: Decimal | None) -> Decimal | None:
        if year in mapping:
            return mapping[year]
        return flat


@dataclass
class PpeLayer:
    name: str
    net: Decimal
    annual_charge: Decimal
    # Remaining full charges after the current year has been taken.
    charges_left_after_this_year: int


@dataclass
class CompanyModel:
    company_id: str
    name: str
    currency: str
    historical: list[HistoricalPeriod]
    assumptions: Assumptions
    synthetic: bool = False
    synthetic_notice: str = ""
    accounting_basis: str = ""
    display_scale: str = "units"
    scenarios: dict[str, Assumptions] = field(default_factory=dict)
    engine_version: str = ENGINE_VERSION


@dataclass
class Trace:
    id: str
    label: str
    period: str | None
    formula: str
    components: list[tuple[str, str]]
    result: str
    kind: Literal["fact", "assumption", "calculation"]
    note: str = ""


@dataclass
class CheckResult:
    name: str
    period: str | None
    expected: str | None
    actual: str | None
    difference: str | None
    status: Literal["pass", "fail"]
    severity: Severity
    cause: str


@dataclass
class YearBundle:
    period_id: str
    year: int
    label: str
    is_forecast: bool
    days: int
    income: dict[str, Decimal | None]
    balance: dict[str, Decimal | None]
    cash_flow: dict[str, Decimal | None]
    working_capital: dict[str, Decimal | None]
    ppe: dict[str, Decimal | None]
    debt: dict[str, Decimal | None]
    revenue_bridge: dict[str, Decimal | None]
    ufcf: dict[str, Decimal | None]
    ratios: dict[str, Decimal | None]


@dataclass
class DcfResult:
    convention: str
    terminal_method: str
    wacc: Decimal | None
    terminal_growth: Decimal | None
    exit_multiple: Decimal | None
    discount_factors: dict[str, Decimal]
    pv_ufcf: dict[str, Decimal | None]
    pv_explicit: Decimal | None
    terminal_value: Decimal | None
    pv_terminal: Decimal | None
    enterprise_value: Decimal | None
    terminal_share_of_ev: Decimal | None
    implied_exit_multiple: Decimal | None
    implied_growth: Decimal | None
    cross_check_terminal_value: Decimal | None
    cross_check_enterprise_value: Decimal | None
    warnings: list[str] = field(default_factory=list)


@dataclass
class EquityBridge:
    enterprise_value: Decimal | None
    interest_bearing_debt: Decimal | None
    debt_like_claims: Decimal | None
    minority_interest: Decimal | None
    preferred_securities: Decimal | None
    excess_cash: Decimal | None
    operating_cash: Decimal | None
    non_operating_assets: Decimal | None
    equity_value: Decimal | None
    diluted_shares: Decimal | None
    value_per_share: Decimal | None
    share_price: Decimal | None
    upside: Decimal | None
    notes: list[str] = field(default_factory=list)


@dataclass
class WaccResult:
    cost_of_equity: Decimal | None
    pre_tax_cost_of_debt: Decimal | None
    after_tax_cost_of_debt: Decimal | None
    equity_weight: Decimal | None
    debt_weight: Decimal | None
    wacc: Decimal | None
    capital_structure_method: str
    market_value_equity: Decimal | None
    market_value_debt: Decimal | None
    components: dict[str, Decimal | None]
    warnings: list[str] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)


@dataclass
class SensitivityTable:
    name: str
    row_label: str
    column_label: str
    row_keys: list[str]
    column_keys: list[str]
    values: list[list[str | None]]
    statuses: list[list[str]]
    base_row: int | None
    base_column: int | None
    note: str


@dataclass
class ModelResult:
    engine_version: str
    company_id: str
    company_name: str
    currency: str
    display_scale: str
    synthetic: bool
    synthetic_notice: str
    scenario_name: str
    years: list[YearBundle]
    wacc: WaccResult | None
    dcf: DcfResult | None
    equity: EquityBridge | None
    checks: list[CheckResult]
    traces: list[Trace]
    blocking_errors: list[str]
    drivers_applied: list[str]
    drivers_ignored: list[str]
    suggestions: dict[str, str]
    cost_mode: str
    cost_precedence_note: str
    dependency_graph: list[tuple[str, list[str]]]
    scenarios: dict[str, "ModelResult"] = field(default_factory=dict)
    sensitivities: list[SensitivityTable] = field(default_factory=list)
    converged: bool = True
    circularity_notes: list[str] = field(default_factory=list)


class ModelInputError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))
