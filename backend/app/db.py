"""Database engine. SQLite is the local default. Postgres is selected with DATABASE_URL."""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

engine = None
SessionLocal: sessionmaker[Session] | None = None


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "sqlite:///./valuationlab.db")


def configure(url: str | None = None) -> None:
    global engine, SessionLocal
    chosen = url or database_url()
    kwargs: dict = {}
    if chosen.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if chosen in {"sqlite://", "sqlite:///:memory:"}:
            kwargs["poolclass"] = StaticPool
    engine = create_engine(chosen, **kwargs)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    from backend.app import entities  # noqa: F401

    Base.metadata.create_all(engine)


def get_db() -> Iterator[Session]:
    if SessionLocal is None:
        configure()
    assert SessionLocal is not None
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
