"""
SentinelID FastAPI Application Entry Point.
Configures CORS, routes, database initialization, and exception handlers.
"""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.db.init_db import init_db, seed_db
from app.api import auth, screenings, dashboard

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize DB on startup."""
    logger.info("Starting SentinelID API v%s", settings.APP_VERSION)
    init_db()
    seed_db()
    # Ensure upload directory exists
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    yield
    logger.info("SentinelID API shutting down")


app = FastAPI(
    title="SentinelID API",
    description=(
        "AI-Based Fake Identity & Document Screening System — PROTOTYPE\n\n"
        "⚠️ This is a prototype system for demonstration purposes only. "
        "It does not connect to real government or law enforcement databases."
    ),
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routes ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(screenings.router)
app.include_router(dashboard.router)

# ─── Static files for uploads ─────────────────────────────────────────────────
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")


# ─── Health Check ─────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["System"])
async def health_check():
    """System health check endpoint."""
    from app.services.ocr.ocr_engine import ocr_engine
    return {
        "status": "healthy",
        "service": "SentinelID API",
        "version": settings.APP_VERSION,
        "ocr_engine": ocr_engine.engine_name,
        "prototype": True,
        "disclaimer": "This is a prototype system. Not for production use.",
    }


# ─── Global Exception Handler ─────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions gracefully."""
    logger.error("Unhandled exception: %s %s — %s", request.method, request.url, exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.DEBUG else "An unexpected error occurred",
            "status_code": 500,
        },
    )


# ─── App init ─────────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": "SentinelID API",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/api/health",
    }
