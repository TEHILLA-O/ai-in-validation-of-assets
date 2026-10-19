"""FastAPI application entry point."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.db import configure
from backend.app import db as database
from backend.app.routes import router
from backend.app.seed import seed


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure()
    assert database.SessionLocal is not None
    session = database.SessionLocal()
    try:
        seed(session)
    finally:
        session.close()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="ValuationLab",
        version="1.0.0",
        summary="Three-statement forecasting and discounted cash flow valuation.",
        lifespan=lifespan,
    )
    origins = [item.strip() for item in os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if item.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
