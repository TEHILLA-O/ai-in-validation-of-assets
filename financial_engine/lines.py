"""Canonical statement lines and the calculation dependency graph.

The graph is the contract for the engine, the API and the Excel workbook.
Later stages may only consume outputs of earlier stages.
"""

from __future__ import annotations

ENGINE_VERSION = "1.0.0"

# (key, label, kind) kind is "input", "calc" or "total"
INCOME_LINES: list[tuple[str, str]] = [
    ("revenue", "Revenue"),
    ("cogs", "Cost of goods sold"),
    ("gross_profit", "Gross profit"),
    ("personnel", "Personnel expenses"),
    ("rd", "Research and development"),
    ("sales_marketing", "Sales and marketing"),
    ("ga", "General and administrative"),
    ("other_opex", "Other operating expenses"),
    ("ebitda", "EBITDA"),
    ("depreciation", "Depreciation"),
    ("amortisation", "Amortisation"),
    ("impairment", "Impairments"),
    ("ebit", "EBIT"),
    ("interest_income", "Interest income"),
    ("interest_expense", "Interest expense"),
    ("other_non_operating", "Other non-operating items"),
    ("ebt", "Profit before tax"),
    ("tax_expense", "Income tax expense"),
    ("net_income", "Net income"),
]

BALANCE_LINES: list[tuple[str, str]] = [
    ("cash", "Cash and cash equivalents"),
    ("accounts_receivable", "Accounts receivable"),
    ("inventory", "Inventory"),
    ("other_current_assets", "Other current assets"),
    ("ppe_net", "Property, plant and equipment"),
    ("intangibles", "Intangible assets"),
    ("other_non_current_assets", "Other non-current assets"),
    ("total_assets", "Total assets"),
    ("accounts_payable", "Accounts payable"),
    ("accrued_expenses", "Accrued expenses"),
    ("other_operating_cl", "Other operating current liabilities"),
    ("short_term_debt", "Current debt"),
    ("revolver", "Minimum-cash revolver"),
    ("long_term_debt", "Long-term debt"),
    ("other_liabilities", "Other liabilities"),
    ("total_liabilities", "Total liabilities"),
    ("share_capital", "Share capital"),
    ("apic", "Additional paid-in capital"),
    ("retained_earnings", "Retained earnings"),
    ("other_equity", "Other equity"),
    ("total_equity", "Total equity"),
    ("total_liabilities_and_equity", "Total liabilities and equity"),
]

CASH_FLOW_LINES: list[tuple[str, str]] = [
    ("net_income", "Net income"),
    ("depreciation_amortisation", "Depreciation, amortisation and impairments"),
    ("disposal_gain", "Gain on disposal (deducted)"),
    ("other_non_cash", "Other non-cash adjustments"),
    ("change_in_nwc", "Increase in operating net working capital"),
    ("cash_from_operations", "Cash flow from operations"),
    ("capex", "Capital expenditure"),
    ("intangible_additions", "Intangible asset purchases"),
    ("disposal_proceeds", "Disposal proceeds"),
    ("change_in_other_nca", "Increase in other non-current assets"),
    ("other_investing", "Other investing cash flows"),
    ("cash_from_investing", "Cash flow from investing"),
    ("borrowings", "New borrowings"),
    ("repayments", "Principal repayments"),
    ("revolver_draw", "Revolver draw / (repayment)"),
    ("equity_issued", "Share issuances"),
    ("buybacks", "Share repurchases"),
    ("dividends", "Dividends"),
    ("change_in_other_liabilities", "Increase in other liabilities"),
    ("other_financing", "Other financing cash flows"),
    ("cash_from_financing", "Cash flow from financing"),
    ("fx_effect", "Foreign-exchange effect on cash"),
    ("net_change_in_cash", "Net change in cash"),
    ("opening_cash", "Opening cash"),
    ("closing_cash", "Closing cash"),
]

# Directed dependency graph. Each node lists the nodes that must be known first.
DEPENDENCY_GRAPH: list[tuple[str, list[str]]] = [
    ("Historical statements", []),
    ("Revenue drivers", ["Historical statements"]),
    ("Operating costs", ["Revenue drivers"]),
    ("EBITDA", ["Revenue drivers", "Operating costs"]),
    ("CapEx and depreciation layers", ["Revenue drivers", "Historical statements"]),
    ("EBIT", ["EBITDA", "CapEx and depreciation layers"]),
    ("Debt schedule and interest", ["Historical statements"]),
    ("Taxes and net income", ["EBIT", "Debt schedule and interest"]),
    ("Working capital", ["Revenue drivers", "Operating costs", "Historical statements"]),
    ("Financing and dividends", ["Taxes and net income", "Debt schedule and interest"]),
    ("Cash flow statement", [
        "Taxes and net income",
        "CapEx and depreciation layers",
        "Working capital",
        "Financing and dividends",
    ]),
    ("Balance sheet", ["Cash flow statement", "Working capital", "CapEx and depreciation layers", "Financing and dividends"]),
    ("Unlevered free cash flow", ["EBIT", "CapEx and depreciation layers", "Working capital"]),
    ("WACC", ["Historical statements"]),
    ("DCF valuation", ["Unlevered free cash flow", "WACC"]),
    ("Equity bridge", ["DCF valuation", "Historical statements"]),
]

# Cost-mode precedence, also surfaced on every forecast result.
COST_PRECEDENCE = {
    "line_item": (
        "Each operating cost is forecast from its own driver. "
        "Gross margin and EBITDA margin are outputs."
    ),
    "margin_target": (
        "Gross margin and EBITDA margin targets drive COGS and total cash operating cost. "
        "Line-item cost drivers are retained for reference and are not applied. "
        "Cash operating cost is allocated with the stated mix weights."
    ),
}
