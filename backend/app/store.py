"""Read and write persisted model inputs. Calculation stays outside this module."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.entities import (
    AuditEvent,
    Company,
    FinancialPeriod,
    LineItem,
    MarketSnapshot,
    ModelVersion,
    ScenarioRecord,
    SourceDocument,
    User,
    ValuationRun,
)
from financial_engine.lines import ENGINE_VERSION
from financial_engine.serialize import to_jsonable


def new_id() -> str:
    return uuid.uuid4().hex


def audit(db: Session, user_id: str, company_id: str | None, action: str, detail: dict) -> None:
    db.add(AuditEvent(
        id=new_id(),
        user_id=user_id,
        company_id=company_id,
        action=action,
        detail=detail,
    ))


def owned_company(db: Session, owner_id: str, company_id: str) -> Company | None:
    company = db.get(Company, company_id)
    if company is None or company.owner_id != owner_id:
        return None
    return company


def list_companies(db: Session, owner_id: str, limit: int, offset: int) -> tuple[list[Company], int]:
    total = db.scalar(select(func.count()).select_from(Company).where(Company.owner_id == owner_id)) or 0
    rows = db.scalars(
        select(Company).where(Company.owner_id == owner_id).order_by(Company.created_at).offset(offset).limit(limit)
    ).all()
    return list(rows), int(total)


def latest_version(db: Session, company_id: str) -> ModelVersion | None:
    return db.scalar(
        select(ModelVersion).where(ModelVersion.company_id == company_id).order_by(ModelVersion.version_number.desc())
    )


def get_version(db: Session, model_id: str, owner_id: str) -> tuple[ModelVersion, Company] | None:
    version = db.get(ModelVersion, model_id)
    if version is None:
        return None
    company = owned_company(db, owner_id, version.company_id)
    if company is None:
        return None
    return version, company


def save_version(
    db: Session,
    company: Company,
    user_id: str,
    snapshot: dict,
    note: str,
) -> ModelVersion:
    current = latest_version(db, company.id)
    number = 1 if current is None else current.version_number + 1
    version = ModelVersion(
        id=new_id(),
        company_id=company.id,
        version_number=number,
        engine_version=ENGINE_VERSION,
        snapshot=snapshot,
        note=note,
        created_by=user_id,
    )
    db.add(version)
    db.flush()
    for name, assumptions in (snapshot.get("scenarios") or {}).items():
        db.add(ScenarioRecord(
            id=new_id(),
            model_version_id=version.id,
            name=str(name),
            assumptions=assumptions,
        ))
    write_line_items(db, version.id, snapshot)
    return version


def write_line_items(db: Session, model_version_id: str, snapshot: dict) -> None:
    for period in snapshot.get("historical") or []:
        row = FinancialPeriod(
            id=new_id(),
            model_version_id=model_version_id,
            period_id=str(period.get("period_id")),
            label=str(period.get("label") or period.get("period_id")),
            year=int(period.get("year")),
            period_end=str(period.get("period_end")),
            days=int(period.get("days") or 365),
            currency=str(period.get("currency")),
            statement_complete=1 if period.get("statement_complete") else 0,
            accounting_basis=str(period.get("accounting_basis") or ""),
        )
        db.add(row)
        db.flush()
        sources = period.get("sources") or {}
        for statement, key in (("income", "income"), ("balance", "balance"), ("cash_flow", "cash_flow")):
            figures = period.get(key) or {}
            for canonical, amount in figures.items():
                source = sources.get(canonical) or {}
                db.add(LineItem(
                    id=new_id(),
                    period_row_id=row.id,
                    statement=statement,
                    canonical_key=str(canonical),
                    original_label=str(source.get("reported_label") or canonical),
                    amount=None if amount is None else str(amount),
                    currency=str(period.get("currency")),
                    unit_scale=str(source.get("unit_scale") or "units"),
                    source=str(source.get("source") or ""),
                    adjustment=source.get("adjustment"),
                    imported_at=source.get("imported_at"),
                    accounting_basis=source.get("accounting_basis"),
                ))


def line_items_for_version(db: Session, model_version_id: str) -> list[dict]:
    periods = db.scalars(
        select(FinancialPeriod).where(FinancialPeriod.model_version_id == model_version_id).order_by(FinancialPeriod.year)
    ).all()
    payload = []
    for period in periods:
        items = db.scalars(select(LineItem).where(LineItem.period_row_id == period.id)).all()
        payload.append({
            "period_id": period.period_id,
            "label": period.label,
            "year": period.year,
            "period_end": period.period_end,
            "days": period.days,
            "currency": period.currency,
            "statement_complete": bool(period.statement_complete),
            "accounting_basis": period.accounting_basis,
            "lines": [
                {
                    "statement": item.statement,
                    "canonical_key": item.canonical_key,
                    "original_label": item.original_label,
                    "amount": item.amount,
                    "currency": item.currency,
                    "unit_scale": item.unit_scale,
                    "source": item.source,
                    "adjustment": item.adjustment,
                    "imported_at": item.imported_at,
                    "accounting_basis": item.accounting_basis,
                }
                for item in items
            ],
        })
    return payload


def save_run(db: Session, version: ModelVersion, user_id: str, result: dict) -> ValuationRun:
    run = ValuationRun(
        id=new_id(),
        model_version_id=version.id,
        engine_version=version.engine_version,
        input_snapshot=version.snapshot,
        result=result,
        created_by=user_id,
    )
    db.add(run)
    db.flush()
    assumptions = version.snapshot.get("assumptions") or {}
    wacc = assumptions.get("wacc") or {}
    valuation = assumptions.get("valuation") or {}
    db.add(MarketSnapshot(
        id=new_id(),
        valuation_run_id=run.id,
        payload={
            "wacc_inputs": wacc,
            "share_price": valuation.get("share_price"),
            "share_price_as_of": valuation.get("share_price_as_of"),
            "share_price_source": valuation.get("share_price_source"),
            "label": "Manual market inputs stored with this valuation run. Not a live market feed.",
        },
        as_of=str(valuation.get("valuation_date") or ""),
        source_note=str(wacc.get("market_value_source") or "No market-value source recorded."),
    ))
    return run


def latest_run(db: Session, model_version_id: str) -> ValuationRun | None:
    return db.scalar(
        select(ValuationRun).where(ValuationRun.model_version_id == model_version_id).order_by(ValuationRun.created_at.desc())
    )


def list_runs(db: Session, model_version_id: str) -> list[ValuationRun]:
    return list(db.scalars(
        select(ValuationRun).where(ValuationRun.model_version_id == model_version_id).order_by(ValuationRun.created_at.desc())
    ).all())


def get_run(db: Session, run_id: str, owner_id: str) -> tuple[ValuationRun, ModelVersion] | None:
    run = db.get(ValuationRun, run_id)
    if run is None:
        return None
    found = get_version(db, run.model_version_id, owner_id)
    if found is None:
        return None
    version, _company = found
    return run, version


def add_document(
    db: Session,
    company_id: str,
    user_id: str,
    filename: str,
    content_type: str,
    note: str,
    byte_size: int,
) -> SourceDocument:
    document = SourceDocument(
        id=new_id(),
        company_id=company_id,
        filename=filename,
        content_type=content_type,
        note=note,
        byte_size=byte_size,
        uploaded_by=user_id,
    )
    db.add(document)
    return document


def user_by_name(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def public_company(company: Company, version: ModelVersion | None, run: ValuationRun | None) -> dict:
    return {
        "id": company.id,
        "name": company.name,
        "currency": company.currency,
        "synthetic": bool(company.synthetic),
        "synthetic_notice": company.synthetic_notice,
        "accounting_basis": company.accounting_basis,
        "display_scale": company.display_scale,
        "model_id": None if version is None else version.id,
        "model_version": None if version is None else version.version_number,
        "engine_version": None if version is None else version.engine_version,
        "latest_run_id": None if run is None else run.id,
        "created_at": iso(company.created_at),
    }


def snapshot_json(model) -> dict:
    return to_jsonable(model)
