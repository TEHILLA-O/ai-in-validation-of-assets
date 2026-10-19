"""Application services. Every valuation number comes from financial_engine.run_model."""

from __future__ import annotations

import copy
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app import store
from backend.app.entities import Company, ModelVersion
from financial_engine.codec import model_from_dict
from financial_engine.engine import run_model
from financial_engine.imports.statements import apply_figures, import_csv, import_excel
from financial_engine.model import Assumptions, CompanyModel, SourceRef
from financial_engine.precision import D, cagr
from financial_engine.serialize import to_jsonable

_MONEY_KEYS = {
    "income": {
        "revenue", "cogs", "gross_profit", "personnel", "rd", "sales_marketing", "ga", "other_opex",
        "ebitda", "depreciation", "amortisation", "impairment", "ebit", "interest_income",
        "interest_expense", "other_non_operating", "ebt", "tax_expense", "net_income",
    },
    "balance": {
        "cash", "accounts_receivable", "inventory", "other_current_assets", "ppe_net", "intangibles",
        "other_non_current_assets", "total_assets", "accounts_payable", "accrued_expenses",
        "other_operating_cl", "short_term_debt", "revolver", "long_term_debt", "other_liabilities",
        "total_liabilities", "share_capital", "apic", "retained_earnings", "other_equity",
        "total_equity", "total_liabilities_and_equity",
    },
    "cash_flow": {
        "net_income", "depreciation_amortisation", "disposal_gain", "other_non_cash", "change_in_nwc",
        "cash_from_operations", "capex", "intangible_additions", "disposal_proceeds", "change_in_other_nca",
        "other_investing", "cash_from_investing", "borrowings", "repayments", "revolver_draw",
        "equity_issued", "buybacks", "dividends", "change_in_other_liabilities", "other_financing",
        "cash_from_financing", "fx_effect", "net_change_in_cash", "opening_cash", "closing_cash",
    },
}


def empty_model(company_id: str, name: str, currency: str, synthetic: bool, notice: str, basis: str) -> CompanyModel:
    return CompanyModel(
        company_id=company_id,
        name=name,
        currency=currency.upper(),
        historical=[],
        assumptions=Assumptions(name="Base", notes="No forecast years have been set."),
        synthetic=synthetic,
        synthetic_notice=notice,
        accounting_basis=basis,
    )


def create_company(db: Session, user_id: str, name: str, currency: str, basis: str, synthetic: bool, notice: str) -> dict:
    company = Company(
        id=store.new_id(),
        owner_id=user_id,
        name=name.strip(),
        currency=currency.upper(),
        synthetic=1 if synthetic else 0,
        synthetic_notice=notice,
        accounting_basis=basis,
    )
    db.add(company)
    db.flush()
    model = empty_model(company.id, company.name, company.currency, synthetic, notice, basis)
    version = store.save_version(db, company, user_id, store.snapshot_json(model), "Company created")
    store.audit(db, user_id, company.id, "company.created", {"model_id": version.id, "name": company.name})
    db.commit()
    return store.public_company(company, version, None)


def load_owned_version(db: Session, user_id: str, model_id: str) -> tuple[ModelVersion, Company]:
    found = store.get_version(db, model_id, user_id)
    if found is None:
        raise LookupError("Model not found")
    return found


def replace_assumptions(db: Session, user_id: str, model_id: str, assumptions: dict, note: str) -> dict:
    version, company = load_owned_version(db, user_id, model_id)
    snapshot = copy.deepcopy(version.snapshot)
    previous = snapshot.get("assumptions")
    snapshot["assumptions"] = assumptions
    model_from_dict(snapshot)
    saved = store.save_version(db, company, user_id, snapshot, note or "Assumptions updated")
    store.audit(db, user_id, company.id, "assumptions.updated", {
        "from_model_id": version.id,
        "model_id": saved.id,
        "note": note,
        "previous_name": None if not isinstance(previous, dict) else previous.get("name"),
        "new_name": assumptions.get("name"),
    })
    db.commit()
    return {"model_id": saved.id, "version_number": saved.version_number, "engine_version": saved.engine_version}


def add_scenario(db: Session, user_id: str, model_id: str, name: str, assumptions: dict) -> dict:
    if name.strip().lower() == "base":
        raise ValueError("The base case is the model's assumption set. Edit it with the assumptions endpoint.")
    version, company = load_owned_version(db, user_id, model_id)
    snapshot = copy.deepcopy(version.snapshot)
    snapshot.setdefault("scenarios", {})[name] = assumptions
    model_from_dict(snapshot)
    saved = store.save_version(db, company, user_id, snapshot, f"Scenario {name} saved")
    store.audit(db, user_id, company.id, "scenario.saved", {
        "from_model_id": version.id,
        "model_id": saved.id,
        "name": name,
    })
    db.commit()
    return {"model_id": saved.id, "version_number": saved.version_number, "scenario": name}


def calculate(db: Session, user_id: str, model_id: str) -> dict:
    version, company = load_owned_version(db, user_id, model_id)
    model = model_from_dict(version.snapshot)
    result = to_jsonable(run_model(model))
    run = store.save_run(db, version, user_id, result)
    store.audit(db, user_id, company.id, "valuation.calculated", {
        "model_id": version.id,
        "run_id": run.id,
        "engine_version": version.engine_version,
        "enterprise_value": None if not result.get("dcf") else result["dcf"].get("enterprise_value"),
    })
    db.commit()
    return {"run_id": run.id, "model_id": version.id, "calculated_at": store.iso(run.created_at), "result": result}


def import_statements(db: Session, user_id: str, company_id: str, filename: str, payload: bytes) -> dict:
    company = store.owned_company(db, user_id, company_id)
    if company is None:
        raise LookupError("Company not found")
    version = store.latest_version(db, company.id)
    if version is None:
        raise LookupError("Company has no model version")
    lower = filename.lower()
    if lower.endswith(".csv"):
        imported = import_csv(payload, filename)
    elif lower.endswith(".xlsx") or lower.endswith(".xlsm"):
        imported = import_excel(payload, filename)
    else:
        raise ValueError("Upload a .csv or .xlsx file. Other formats are stored only as source documents.")
    model = model_from_dict(version.snapshot)
    warnings = apply_figures(model, imported, datetime.now(timezone.utc).isoformat())
    saved = store.save_version(db, company, user_id, store.snapshot_json(model), f"Imported {filename}")
    note = "Imported into the historical statements. Blank cells were stored as missing, not zero."
    if warnings:
        note += " Warnings: " + " ".join(warnings)
    store.add_document(db, company.id, user_id, filename, "spreadsheet", note, len(payload))
    store.audit(db, user_id, company.id, "financials.imported", {
        "model_id": saved.id,
        "filename": filename,
        "warnings": warnings,
        "rows": len(imported.figures),
    })
    db.commit()
    return {"model_id": saved.id, "version_number": saved.version_number, "warnings": warnings, "rows": len(imported.figures)}


def update_lines(db: Session, user_id: str, company_id: str, edits: list[dict]) -> dict:
    company = store.owned_company(db, user_id, company_id)
    if company is None:
        raise LookupError("Company not found")
    version = store.latest_version(db, company.id)
    if version is None:
        raise LookupError("Company has no model version")
    model = model_from_dict(version.snapshot)
    touched = []
    for edit in edits:
        statement = edit["statement"]
        key = edit["key"]
        if key not in _MONEY_KEYS[statement]:
            raise ValueError(f"{key} is not a {statement} line. It was not stored.")
        source = (edit.get("source") or "").strip()
        if not source:
            raise ValueError(f"{key} needs a source. A figure was not saved without one.")
        year = int(edit["year"])
        period = next((item for item in model.historical if item.year == year), None)
        if period is None:
            period_end = edit.get("period_end") or f"{year}-12-31"
            from datetime import date

            from financial_engine.model import HistoricalPeriod
            period = HistoricalPeriod(
                period_id=str(year),
                label=f"FY{year}A",
                year=year,
                period_end=date.fromisoformat(period_end),
                days=int(edit.get("days") or 365),
                currency=company.currency,
                income={},
                balance={},
                cash_flow={},
                statement_complete=False,
                accounting_basis=company.accounting_basis,
            )
            model.historical.append(period)
            model.historical.sort(key=lambda item: item.year)
        raw = edit.get("value")
        amount = None if raw is None or str(raw).strip() == "" else D(str(raw).strip())
        target = {"income": period.income, "balance": period.balance, "cash_flow": period.cash_flow}[statement]
        if statement == "cash_flow" and period.cash_flow is None:
            period.cash_flow = {}
            target = period.cash_flow
        target[key] = amount
        period.sources[key] = SourceRef(
            source=source,
            reported_label=edit.get("original_label") or key,
            unit_scale="units",
            adjustment=edit.get("adjustment"),
            imported_at=datetime.now(timezone.utc).isoformat(),
            accounting_basis=company.accounting_basis,
        )
        touched.append({"year": year, "statement": statement, "key": key, "amount": None if amount is None else format(amount, "f")})
    saved = store.save_version(db, company, user_id, store.snapshot_json(model), "Historical lines updated")
    store.audit(db, user_id, company.id, "financials.edited", {"model_id": saved.id, "lines": touched})
    db.commit()
    return {"model_id": saved.id, "version_number": saved.version_number, "lines": touched}


def dashboard(result: dict, valuation_date: str | None) -> dict:
    years = result.get("years") or []
    historical = [year for year in years if not year.get("is_forecast")]
    forecast = [year for year in years if year.get("is_forecast")]
    revenue_cagr = None
    if historical and forecast:
        start = (historical[-1].get("income") or {}).get("revenue")
        end = (forecast[-1].get("income") or {}).get("revenue")
        if start is not None and end is not None:
            rate = cagr(D(start), D(end), len(forecast))
            revenue_cagr = None if rate is None else format(rate, "f")
    last = forecast[-1] if forecast else None
    ebitda_margin = None if last is None else (last.get("ratios") or {}).get("ebitda_margin")
    dcf = result.get("dcf") or {}
    equity = result.get("equity") or {}
    wacc = result.get("wacc") or {}
    checks = result.get("checks") or []
    return {
        "currency": result.get("currency"),
        "display_scale": result.get("display_scale"),
        "scenario": result.get("scenario_name"),
        "synthetic": result.get("synthetic"),
        "synthetic_notice": result.get("synthetic_notice"),
        "valuation_date": valuation_date,
        "enterprise_value": dcf.get("enterprise_value"),
        "equity_value": equity.get("equity_value"),
        "value_per_share": equity.get("value_per_share"),
        "wacc": wacc.get("wacc"),
        "terminal_growth": dcf.get("terminal_growth"),
        "terminal_method": dcf.get("terminal_method"),
        "discount_convention": dcf.get("convention"),
        "projected_revenue_cagr": revenue_cagr,
        "ebitda_margin": ebitda_margin,
        "terminal_share": dcf.get("terminal_share_of_ev"),
        "pv_explicit": dcf.get("pv_explicit"),
        "pv_terminal": dcf.get("pv_terminal"),
        "share_price": equity.get("share_price"),
        "upside": equity.get("upside"),
        "passed_checks": sum(1 for check in checks if check.get("status") == "pass"),
        "failed_checks": sum(1 for check in checks if check.get("status") == "fail"),
        "series": [
            {
                "period": year.get("label"),
                "year": year.get("year"),
                "is_forecast": year.get("is_forecast"),
                "revenue": (year.get("income") or {}).get("revenue"),
                "ebitda": (year.get("income") or {}).get("ebitda"),
                "ebitda_margin": (year.get("ratios") or {}).get("ebitda_margin"),
                "ufcf": (year.get("ufcf") or {}).get("ufcf"),
            }
            for year in years
        ],
    }
