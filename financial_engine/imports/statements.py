"""CSV and Excel historical imports.

Blank cells stay blank. They are not converted to zero. Scale factors are
applied only when the file states them, and mixed currencies are rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO

import pandas as pd

from financial_engine.precision import D

SCALE = {
    "units": Decimal(1),
    "unit": Decimal(1),
    "ones": Decimal(1),
    "thousands": Decimal(1000),
    "thousand": Decimal(1000),
    "millions": Decimal(1_000_000),
    "million": Decimal(1_000_000),
    "billions": Decimal(1_000_000_000),
    "billion": Decimal(1_000_000_000),
}

ALIASES = {
    "revenue": "revenue",
    "sales": "revenue",
    "net sales": "revenue",
    "turnover": "revenue",
    "cogs": "cogs",
    "cost of goods sold": "cogs",
    "cost of sales": "cogs",
    "gross profit": "gross_profit",
    "personnel": "personnel",
    "personnel expenses": "personnel",
    "research and development": "rd",
    "r&d": "rd",
    "rd": "rd",
    "sales and marketing": "sales_marketing",
    "selling and marketing": "sales_marketing",
    "general and administrative": "ga",
    "g&a": "ga",
    "other operating expenses": "other_opex",
    "depreciation": "depreciation",
    "amortisation": "amortisation",
    "amortization": "amortisation",
    "impairment": "impairment",
    "impairments": "impairment",
    "interest income": "interest_income",
    "interest expense": "interest_expense",
    "other non-operating": "other_non_operating",
    "other non-operating items": "other_non_operating",
    "tax": "tax_expense",
    "income tax expense": "tax_expense",
    "tax expense": "tax_expense",
    "net income": "net_income",
    "ebitda": "ebitda",
    "ebit": "ebit",
    "profit before tax": "ebt",
    "cash": "cash",
    "cash and cash equivalents": "cash",
    "accounts receivable": "accounts_receivable",
    "inventory": "inventory",
    "other current assets": "other_current_assets",
    "ppe": "ppe_net",
    "property, plant and equipment": "ppe_net",
    "intangibles": "intangibles",
    "intangible assets": "intangibles",
    "other non-current assets": "other_non_current_assets",
    "accounts payable": "accounts_payable",
    "accrued expenses": "accrued_expenses",
    "other operating current liabilities": "other_operating_cl",
    "current debt": "short_term_debt",
    "short-term debt": "short_term_debt",
    "short term debt": "short_term_debt",
    "revolver": "revolver",
    "long-term debt": "long_term_debt",
    "long term debt": "long_term_debt",
    "other liabilities": "other_liabilities",
    "share capital": "share_capital",
    "additional paid-in capital": "apic",
    "retained earnings": "retained_earnings",
    "other equity": "other_equity",
    "capex": "capex",
    "capital expenditure": "capex",
    "dividends": "dividends",
}

STATEMENT_FOR = {
    "revenue": "income",
    "cogs": "income",
    "gross_profit": "income",
    "personnel": "income",
    "rd": "income",
    "sales_marketing": "income",
    "ga": "income",
    "other_opex": "income",
    "depreciation": "income",
    "amortisation": "income",
    "impairment": "income",
    "interest_income": "income",
    "interest_expense": "income",
    "other_non_operating": "income",
    "tax_expense": "income",
    "net_income": "income",
    "ebitda": "income",
    "ebit": "income",
    "ebt": "income",
    "cash": "balance",
    "accounts_receivable": "balance",
    "inventory": "balance",
    "other_current_assets": "balance",
    "ppe_net": "balance",
    "intangibles": "balance",
    "other_non_current_assets": "balance",
    "accounts_payable": "balance",
    "accrued_expenses": "balance",
    "other_operating_cl": "balance",
    "short_term_debt": "balance",
    "revolver": "balance",
    "long_term_debt": "balance",
    "other_liabilities": "balance",
    "share_capital": "balance",
    "apic": "balance",
    "retained_earnings": "balance",
    "other_equity": "balance",
    "capex": "cash_flow",
    "dividends": "cash_flow",
}


@dataclass
class ImportIssue:
    severity: str
    message: str
    row: int | None = None


@dataclass
class ImportedFigure:
    period: str
    year: int
    statement: str
    canonical_key: str
    original_label: str
    value: Decimal | None
    currency: str
    source_scale: str
    source: str
    accounting_basis: str | None = None


@dataclass
class ImportResult:
    figures: list[ImportedFigure] = field(default_factory=list)
    issues: list[ImportIssue] = field(default_factory=list)

    @property
    def blocking(self) -> list[ImportIssue]:
        return [issue for issue in self.issues if issue.severity == "fail"]


def _blank(value) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except TypeError:
        pass
    return str(value).strip() == ""


def _parse_value(raw) -> Decimal | None:
    if _blank(raw):
        return None
    text = str(raw).strip().replace(",", "").replace("(", "-").replace(")", "")
    if text.endswith("%"):
        return D(text[:-1]) / Decimal(100)
    return D(text)


def import_frame(frame: pd.DataFrame, source_name: str) -> ImportResult:
    result = ImportResult()
    required = {"period", "line_item", "value", "currency", "unit_scale"}
    missing = required - {column.strip().lower() for column in frame.columns}
    if missing:
        result.issues.append(ImportIssue("fail", f"Missing columns: {', '.join(sorted(missing))}"))
        return result
    renamed = {column: column.strip().lower() for column in frame.columns}
    frame = frame.rename(columns=renamed)
    currencies = set()
    for index, row in frame.iterrows():
        row_number = int(index) + 2
        label = "" if _blank(row.get("line_item")) else str(row.get("line_item")).strip()
        canonical = ALIASES.get(label.lower())
        if canonical is None:
            result.issues.append(ImportIssue(
                "warning",
                f"Line item '{label}' is not mapped. It was not imported and was not set to zero.",
                row_number,
            ))
            continue
        try:
            value = _parse_value(row.get("value"))
        except (InvalidOperation, TypeError, ValueError):
            result.issues.append(ImportIssue("fail", f"Value for '{label}' is not a number.", row_number))
            continue
        scale_name = str(row.get("unit_scale")).strip().lower()
        if scale_name not in SCALE:
            result.issues.append(ImportIssue("fail", f"Unknown unit scale '{scale_name}'.", row_number))
            continue
        if _blank(row.get("currency")):
            result.issues.append(ImportIssue("fail", "Currency is missing.", row_number))
            continue
        currency = str(row.get("currency")).strip().upper()
        currencies.add(currency)
        if _blank(row.get("period")):
            result.issues.append(ImportIssue("fail", "Period is missing.", row_number))
            continue
        period_text = str(row.get("period")).strip()
        year_text = period_text[:4]
        if not year_text.isdigit():
            result.issues.append(ImportIssue("fail", f"Period '{period_text}' does not start with a year.", row_number))
            continue
        normalized = None if value is None else value * SCALE[scale_name]
        basis = None if _blank(row.get("accounting_basis")) else str(row.get("accounting_basis"))
        result.figures.append(ImportedFigure(
            period=year_text,
            year=int(year_text),
            statement=STATEMENT_FOR[canonical],
            canonical_key=canonical,
            original_label=label,
            value=normalized,
            currency=currency,
            source_scale=scale_name,
            source=source_name,
            accounting_basis=basis,
        ))
    if len(currencies) > 1:
        result.issues.append(ImportIssue(
            "fail",
            "The file mixes currencies: " + ", ".join(sorted(currencies)) + ". Nothing was silently converted.",
        ))
    return result


def import_csv(payload: bytes, source_name: str) -> ImportResult:
    frame = pd.read_csv(BytesIO(payload))
    return import_frame(frame, source_name)


def import_excel(payload: bytes, source_name: str) -> ImportResult:
    frame = pd.read_excel(BytesIO(payload))
    return import_frame(frame, source_name)


def figures_as_of(result: ImportResult) -> str:
    return date.today().isoformat()


def apply_figures(model, imported: ImportResult, imported_at: str) -> list[str]:
    """Write imported figures onto a company model.

    Only cells present in the file change. A blank cell is stored as missing,
    not as zero. Unmapped labels never reach this function.
    """
    from financial_engine.model import HistoricalPeriod, SourceRef

    if imported.blocking:
        raise ValueError("; ".join(issue.message for issue in imported.blocking))
    currencies = {figure.currency for figure in imported.figures}
    if len(currencies) > 1:
        raise ValueError("Import was refused because it mixes currencies.")
    if currencies and model.historical and model.currency not in currencies:
        raise ValueError(
            f"Import currency {next(iter(currencies))} does not match the company currency {model.currency}."
        )
    if currencies and not model.historical:
        model.currency = next(iter(currencies))
    existing = {period.year: period for period in model.historical}
    grouped: dict[int, list[ImportedFigure]] = {}
    for figure in imported.figures:
        grouped.setdefault(figure.year, []).append(figure)
    for year, figures in grouped.items():
        period = existing.get(year)
        if period is None:
            basis = next((figure.accounting_basis for figure in figures if figure.accounting_basis), "") or ""
            period = HistoricalPeriod(
                period_id=str(year),
                label=f"FY{year}A",
                year=year,
                period_end=date(year, 12, 31),
                days=365,
                currency=figures[0].currency,
                income={},
                balance={},
                cash_flow={},
                statement_complete=False,
                accounting_basis=basis,
            )
            model.historical.append(period)
            existing[year] = period
        elif period.currency != figures[0].currency:
            raise ValueError(
                f"FY{year} is already stored in {period.currency}. "
                f"The import is in {figures[0].currency} and was not converted."
            )
        for figure in figures:
            if figure.statement == "income":
                target = period.income
            elif figure.statement == "balance":
                target = period.balance
            else:
                if period.cash_flow is None:
                    period.cash_flow = {}
                target = period.cash_flow
            target[figure.canonical_key] = figure.value
            period.sources[figure.canonical_key] = SourceRef(
                source=figure.source,
                reported_label=figure.original_label,
                unit_scale=figure.source_scale,
                imported_at=imported_at,
                accounting_basis=figure.accounting_basis,
            )
    model.historical.sort(key=lambda period: period.year)
    return [issue.message for issue in imported.issues if issue.severity != "fail"]
