"""Persistent records. Model inputs are stored apart from valuation outputs."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    currency: Mapped[str] = mapped_column(String(12))
    synthetic: Mapped[int] = mapped_column(Integer, default=0)
    synthetic_notice: Mapped[str] = mapped_column(Text, default="")
    accounting_basis: Mapped[str] = mapped_column(Text, default="")
    display_scale: Mapped[str] = mapped_column(String(20), default="units")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("company_id", "version_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    engine_version: Mapped[str] = mapped_column(String(20))
    snapshot: Mapped[dict] = mapped_column(JSON)
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FinancialPeriod(Base):
    __tablename__ = "financial_periods"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    model_version_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id"), index=True)
    period_id: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(40))
    year: Mapped[int] = mapped_column(Integer)
    period_end: Mapped[str] = mapped_column(String(20))
    days: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(12))
    statement_complete: Mapped[int] = mapped_column(Integer, default=0)
    accounting_basis: Mapped[str] = mapped_column(Text, default="")


class LineItem(Base):
    __tablename__ = "line_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    period_row_id: Mapped[str] = mapped_column(ForeignKey("financial_periods.id"), index=True)
    statement: Mapped[str] = mapped_column(String(20))
    canonical_key: Mapped[str] = mapped_column(String(80))
    original_label: Mapped[str] = mapped_column(String(200), default="")
    amount: Mapped[str | None] = mapped_column(String(80), nullable=True)
    currency: Mapped[str] = mapped_column(String(12))
    unit_scale: Mapped[str] = mapped_column(String(20), default="units")
    source: Mapped[str] = mapped_column(Text, default="")
    adjustment: Mapped[str | None] = mapped_column(Text, nullable=True)
    imported_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    accounting_basis: Mapped[str | None] = mapped_column(Text, nullable=True)


class ScenarioRecord(Base):
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    model_version_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    assumptions: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ValuationRun(Base):
    __tablename__ = "valuation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    model_version_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id"), index=True)
    engine_version: Mapped[str] = mapped_column(String(20))
    input_snapshot: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    valuation_run_id: Mapped[str] = mapped_column(ForeignKey("valuation_runs.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    as_of: Mapped[str] = mapped_column(String(20), default="")
    source_note: Mapped[str] = mapped_column(Text, default="")


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    filename: Mapped[str] = mapped_column(String(260))
    content_type: Mapped[str] = mapped_column(String(120), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    byte_size: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    company_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
