"""Seed the documented demo user and the synthetic Northline reference company."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app import store
from backend.app.auth import hash_password
from backend.app.entities import Company, User
from backend.app.service import calculate
from financial_engine.reference.northline import NOTICE, northline_model
from financial_engine.serialize import to_jsonable

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo-valuationlab"
DEMO_USER_ID = "user-demo"
NORTHLINE_ID = "northline"


def seed(db: Session) -> None:
    if store.user_by_name(db, DEMO_USERNAME) is not None:
        return
    db.add(User(
        id=DEMO_USER_ID,
        username=DEMO_USERNAME,
        password_hash=hash_password(DEMO_PASSWORD, "valuationlab-demo"),
    ))
    model = northline_model()
    model.company_id = NORTHLINE_ID
    company = Company(
        id=NORTHLINE_ID,
        owner_id=DEMO_USER_ID,
        name=model.name,
        currency=model.currency,
        synthetic=1,
        synthetic_notice=NOTICE,
        accounting_basis=model.accounting_basis,
        display_scale=model.display_scale,
    )
    db.add(company)
    db.flush()
    version = store.save_version(
        db,
        company,
        DEMO_USER_ID,
        to_jsonable(model),
        "Synthetic Northline reference model. Not a filing.",
    )
    store.audit(db, DEMO_USER_ID, company.id, "company.seeded", {
        "model_id": version.id,
        "notice": NOTICE,
    })
    db.commit()
    calculate(db, DEMO_USER_ID, version.id)
