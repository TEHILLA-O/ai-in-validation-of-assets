"""Versioned HTTP API. Routes validate and persist. They do not reimplement formulas."""

from __future__ import annotations

from decimal import InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ai.analysis.explainer import analyse
from ai.document_processing import describe_upload
from ai.providers.openai_compatible import SYSTEM_PROMPT, configured_provider
from backend.app.auth import CurrentUser, authenticate, current_user, hash_password, issue_token
from backend.app.db import get_db
from backend.app.entities import User
from backend.app import service, store
from exports.excel.workbook import build_workbook
from financial_engine.codec import model_from_dict
from financial_engine.engine import run_model

router = APIRouter(prefix="/api/v1")


class LoginBody(BaseModel):
    username: str
    password: str


class RegisterBody(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=200)


class CompanyBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    currency: str = Field(min_length=3, max_length=12)
    accounting_basis: str = ""
    synthetic: bool = False
    synthetic_notice: str = ""


class AssumptionsBody(BaseModel):
    assumptions: dict[str, Any]
    note: str = ""


class ScenarioBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    assumptions: dict[str, Any]


class LineEdit(BaseModel):
    year: int
    statement: str
    key: str
    value: str | None = None
    source: str
    original_label: str | None = None
    adjustment: str | None = None
    days: int | None = None
    period_end: str | None = None


class LinesBody(BaseModel):
    lines: list[LineEdit]


class AnalyseBody(BaseModel):
    topic: str = "enterprise_value"
    question: str = ""
    consent_to_send: bool = False


def perform(action):
    try:
        return action()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (TypeError, InvalidOperation) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _version_or_404(db: Session, user: CurrentUser, model_id: str):
    found = store.get_version(db, model_id, user.id)
    if found is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return found


def _latest_result(db: Session, version) -> dict:
    run = store.latest_run(db, version.id)
    if run is None:
        raise HTTPException(status_code=404, detail="This model version has not been calculated.")
    return run.result


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/auth/register")
def register(body: RegisterBody, db: Session = Depends(get_db)) -> dict:
    if store.user_by_name(db, body.username) is not None:
        raise HTTPException(status_code=409, detail="That username is already registered.")
    user = User(id=store.new_id(), username=body.username, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return {"token": issue_token(user), "username": user.username}


@router.post("/auth/login")
def login(body: LoginBody, db: Session = Depends(get_db)) -> dict:
    user = authenticate(db, body.username, body.password)
    return {"token": issue_token(user), "username": user.username}


@router.get("/companies")
def companies(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    rows, total = store.list_companies(db, user.id, limit, offset)
    items = []
    for company in rows:
        version = store.latest_version(db, company.id)
        run = None if version is None else store.latest_run(db, version.id)
        items.append(store.public_company(company, version, run))
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/companies", status_code=201)
def create_company(body: CompanyBody, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if body.synthetic and not body.synthetic_notice.strip():
        raise HTTPException(status_code=400, detail="A synthetic company needs a notice that the figures are not real.")
    return service.create_company(
        db, user.id, body.name, body.currency, body.accounting_basis, body.synthetic, body.synthetic_notice,
    )


@router.get("/companies/{company_id}")
def company_detail(company_id: str, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    company = store.owned_company(db, user.id, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    version = store.latest_version(db, company.id)
    run = None if version is None else store.latest_run(db, version.id)
    payload = store.public_company(company, version, run)
    payload["snapshot"] = None if version is None else version.snapshot
    return payload


@router.post("/financials/import")
async def import_financials(
    company_id: str = Form(...),
    file: UploadFile = File(...),
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    content = await file.read()
    filename = file.filename or "upload"
    lower = filename.lower()
    if not lower.endswith((".csv", ".xlsx", ".xlsm")):
        company = store.owned_company(db, user.id, company_id)
        if company is None:
            raise HTTPException(status_code=404, detail="Company not found")
        note = describe_upload(filename, content)
        store.add_document(db, company.id, user.id, filename, file.content_type or "", note, len(content))
        store.audit(db, user.id, company.id, "document.stored", {"filename": filename, "imported": False})
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="The file was stored as a source document and was not imported. CSV and Excel statement layouts are the supported imports. PDF text extraction is not implemented.",
        )
    return perform(lambda: service.import_statements(db, user.id, company_id, filename, content))


@router.get("/financials/{company_id}")
def financials(
    company_id: str,
    model_id: str | None = None,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    company = store.owned_company(db, user.id, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if model_id is None:
        version = store.latest_version(db, company.id)
    else:
        version, owner = _version_or_404(db, user, model_id)
        if owner.id != company.id:
            raise HTTPException(status_code=404, detail="Model not found")
    if version is None:
        return {"model_id": None, "periods": []}
    return {"model_id": version.id, "periods": store.line_items_for_version(db, version.id)}


@router.put("/financials/{company_id}")
def edit_financials(
    company_id: str,
    body: LinesBody,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    return perform(lambda: service.update_lines(db, user.id, company_id, [line.model_dump() for line in body.lines]))


@router.put("/assumptions/{model_id}")
def put_assumptions(
    model_id: str,
    body: AssumptionsBody,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    return perform(lambda: service.replace_assumptions(db, user.id, model_id, body.assumptions, body.note))


@router.get("/models/{model_id}")
def model_detail(model_id: str, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    version, company = _version_or_404(db, user, model_id)
    run = store.latest_run(db, version.id)
    result = None if run is None else run.result
    valuation_date = ((version.snapshot.get("assumptions") or {}).get("valuation") or {}).get("valuation_date")
    return {
        "model_id": version.id,
        "version_number": version.version_number,
        "engine_version": version.engine_version,
        "company": store.public_company(company, version, run),
        "snapshot": version.snapshot,
        "run_id": None if run is None else run.id,
        "result": result,
        "dashboard": None if result is None else service.dashboard(result, valuation_date),
    }


@router.post("/models/{model_id}/calculate")
def calculate(model_id: str, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    payload = perform(lambda: service.calculate(db, user.id, model_id))
    valuation_date = ((store.get_version(db, model_id, user.id)[0].snapshot.get("assumptions") or {}).get("valuation") or {}).get("valuation_date")
    payload["dashboard"] = service.dashboard(payload["result"], valuation_date)
    return payload


@router.get("/models/{model_id}/statements")
def statements(model_id: str, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    version, _company = _version_or_404(db, user, model_id)
    result = _latest_result(db, version)
    return {
        "currency": result.get("currency"),
        "display_scale": result.get("display_scale"),
        "years": [
            {
                "period": year.get("label"),
                "year": year.get("year"),
                "is_forecast": year.get("is_forecast"),
                "income": year.get("income"),
                "balance": year.get("balance"),
                "cash_flow": year.get("cash_flow"),
                "ratios": year.get("ratios"),
            }
            for year in result.get("years") or []
        ],
    }


@router.get("/models/{model_id}/wacc")
def wacc(model_id: str, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    version, _company = _version_or_404(db, user, model_id)
    result = _latest_result(db, version)
    return {"wacc": result.get("wacc"), "inputs": (version.snapshot.get("assumptions") or {}).get("wacc")}


@router.get("/models/{model_id}/dcf")
def dcf(model_id: str, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    version, _company = _version_or_404(db, user, model_id)
    result = _latest_result(db, version)
    return {"dcf": result.get("dcf"), "equity": result.get("equity"), "traces": [
        trace for trace in result.get("traces") or [] if str(trace.get("id", "")).startswith("dcf") or trace.get("id") == "wacc.wacc"
    ]}


@router.post("/models/{model_id}/scenarios")
def scenarios(model_id: str, body: ScenarioBody, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return perform(lambda: service.add_scenario(db, user.id, model_id, body.name, body.assumptions))


@router.get("/models/{model_id}/sensitivities")
def sensitivities(model_id: str, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    version, _company = _version_or_404(db, user, model_id)
    result = _latest_result(db, version)
    return {"sensitivities": result.get("sensitivities") or []}


@router.get("/models/{model_id}/checks")
def checks(model_id: str, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    version, _company = _version_or_404(db, user, model_id)
    result = _latest_result(db, version)
    return {
        "checks": result.get("checks") or [],
        "blocking_errors": result.get("blocking_errors") or [],
        "converged": result.get("converged"),
        "circularity_notes": result.get("circularity_notes") or [],
    }


@router.get("/models/{model_id}/runs")
def runs(model_id: str, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    version, _company = _version_or_404(db, user, model_id)
    return {
        "items": [
            {
                "run_id": run.id,
                "engine_version": run.engine_version,
                "created_at": store.iso(run.created_at),
                "enterprise_value": None if not run.result.get("dcf") else run.result["dcf"].get("enterprise_value"),
            }
            for run in store.list_runs(db, version.id)
        ]
    }


@router.get("/runs/{run_id}")
def run_detail(run_id: str, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    found = store.get_run(db, run_id, user.id)
    if found is None:
        raise HTTPException(status_code=404, detail="Valuation run not found")
    run, version = found
    valuation_date = ((version.snapshot.get("assumptions") or {}).get("valuation") or {}).get("valuation_date")
    return {
        "run_id": run.id,
        "model_id": version.id,
        "engine_version": run.engine_version,
        "created_at": store.iso(run.created_at),
        "input_snapshot": run.input_snapshot,
        "result": run.result,
        "dashboard": service.dashboard(run.result, valuation_date),
    }


@router.post("/models/{model_id}/export/excel")
def export_excel(model_id: str, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    version, company = _version_or_404(db, user, model_id)
    model = model_from_dict(version.snapshot)
    result = run_model(model)
    if result.blocking_errors or result.dcf is None or result.dcf.enterprise_value is None:
        raise HTTPException(status_code=409, detail=result.blocking_errors or ["Enterprise value was not calculated."])
    payload = build_workbook(model, result)
    store.audit(db, user.id, company.id, "excel.exported", {"model_id": version.id, "engine_version": version.engine_version})
    db.commit()
    filename = f"{company.name.replace(' ', '_')}_valuation.xlsx"
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/models/{model_id}/analyse")
def analyse_model(
    model_id: str,
    body: AnalyseBody,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    version, company = _version_or_404(db, user, model_id)
    result = _latest_result(db, version)
    brief = analyse(version.snapshot, result, body.topic, body.question)
    external = None
    provider = configured_provider()
    if body.consent_to_send and provider is not None:
        user_brief = "\n".join(brief["facts"] + brief["assumptions"] + brief["interpretation"])
        try:
            external = provider.complete(SYSTEM_PROMPT, user_brief + "\n\nQuestion:\n" + body.question)
        except Exception as exc:
            brief["interpretation"].append(f"The external model was not used. The request failed: {exc.__class__.__name__}.")
    elif body.consent_to_send and provider is None:
        brief["interpretation"].append("No language-model API key is configured. The answer above is from the deterministic explainer.")
    brief["external_interpretation"] = external
    brief["external_model_used"] = external is not None
    store.audit(db, user.id, company.id, "analysis.requested", {
        "model_id": version.id,
        "topic": body.topic,
        "consent": body.consent_to_send,
        "external_model_used": external is not None,
    })
    db.commit()
    return brief


@router.get("/companies/{company_id}/audit")
def audit_log(
    company_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    company = store.owned_company(db, user.id, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    from sqlalchemy import func, select
    from backend.app.entities import AuditEvent
    total = db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.company_id == company.id)) or 0
    rows = db.scalars(
        select(AuditEvent).where(AuditEvent.company_id == company.id).order_by(AuditEvent.created_at.desc()).offset(offset).limit(limit)
    ).all()
    return {
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "items": [
            {"id": row.id, "action": row.action, "detail": row.detail, "created_at": store.iso(row.created_at), "user_id": row.user_id}
            for row in rows
        ],
    }
