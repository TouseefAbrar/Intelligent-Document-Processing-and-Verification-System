"""EEF — Intelligent Document Processing & Verification Engine.

FastAPI application entry point. Run with:
    uvicorn app.main:app --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, documents, health, submissions
from app.config import settings
from app.core.logging import get_logger, setup_logging
from app.database import ensure_schema, engine
import app.models  # noqa: F401  (register ORM models)

setup_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_schema()
    logger.info("%s v%s started", settings.APP_NAME, settings.APP_VERSION)
    logger.info("OCR provider=%s | Groq=%s", settings.OCR_PROVIDER, settings.groq_available)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered document extraction, classification, verification and reporting engine for the Ezitech internship portal.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_prefix = settings.API_PREFIX
app.include_router(auth.router, prefix=api_prefix)
app.include_router(health.router, prefix=api_prefix)
app.include_router(documents.router, prefix=api_prefix)
app.include_router(submissions.router, prefix=api_prefix)


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": f"{api_prefix}/health",
    }
