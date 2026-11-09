"""
FastAPI Main Application Entrypoint for Government Schemes Discovery & RAG Platform.
Production-hardened with:
- Centralized Settings (pydantic-settings)
- OWASP Security Headers & Distributed Request-ID Tracing
- RFC 7807 Problem Details Global Exception Handlers
- Kubernetes-ready Liveness and Readiness Probes
- Prometheus & OpenTelemetry-compatible Metrics Registry
- High-concurrency SQLite WAL storage
"""

from __future__ import annotations
import os
import sys
import logging
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi.errors import RateLimitExceeded

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.config import settings
from api.routes import upload, schemes, reasoner, chat, stats
from api.dependencies import get_knowledge_store, get_vector_store
from api.middleware import RequestTimingAndTracingMiddleware, SecurityHeadersMiddleware, limiter
from api.metrics import metrics
from api.exceptions import (
    http_exception_handler,
    validation_exception_handler,
    rate_limit_exceeded_handler,
    unhandled_exception_handler,
)

# Configure Root Logger
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("GovSchemesAPI")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application Lifespan Events:
    - Pre-warms and verifies SQLite Knowledge Store and Dense Vector Index on startup.
    - Gracefully closes connections on shutdown.
    """
    logger.info(f"Initializing {settings.PROJECT_NAME} v{settings.VERSION} [{settings.ENVIRONMENT}]...")
    try:
        store = get_knowledge_store()
        stats_info = store.get_statistics()
        logger.info(
            f"Connected to SQLite Knowledge Store: {stats_info.get('total_schemes', 0)} schemes, "
            f"{stats_info.get('total_guideline_chunks', 0)} document chunks active."
        )
        vs = get_vector_store()
        logger.info(f"Loaded Dense Vector Index: {len(vs.index_entries)} indexed items.")
    except Exception as exc:
        logger.warning(f"Startup pre-warming notice: {exc}")

    yield

    logger.info(f"Shutting down {settings.PROJECT_NAME}.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Enterprise-grade RAG backend matching Indian businesses with central and state government schemes, subsidies, and credit facilities.",
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Attach Slowapi Rate Limiter to app state
app.state.limiter = limiter

# Register RFC 7807 Global Exception Handlers
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
if settings.is_production:
    app.add_exception_handler(Exception, unhandled_exception_handler)

# Register Middlewares (Order of execution: Security -> Timing -> CORS)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestTimingAndTracingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(upload.router)
app.include_router(schemes.router)
app.include_router(reasoner.router)
app.include_router(chat.router)
app.include_router(stats.router)

# Mount Static Files & Web Dashboard
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def serve_dashboard():
    """
    Serves the modern, interactive Single-Page Matching Dashboard.
    """
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return JSONResponse({
        "message": f"{settings.PROJECT_NAME} is operational.",
        "version": settings.VERSION,
        "docs_url": "/docs",
    })


# -----------------------------------------------------------------------------
# Observability & Kubernetes Probes
# -----------------------------------------------------------------------------

@app.get("/health", tags=["Observability"])
async def health_check():
    """
    Comprehensive System Health Check reporting DB connectivity and vector store readiness.
    """
    store = get_knowledge_store()
    stats_data = store.get_statistics()
    vs = get_vector_store()

    return {
        "status": "healthy",
        "service": "government-schemes-rag-backend",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "knowledge_base": {
            "total_schemes": stats_data.get("total_schemes", 0),
            "total_guideline_chunks": stats_data.get("total_guideline_chunks", 0),
            "vector_index_entries": len(vs.index_entries),
        },
    }


@app.get("/health/live", tags=["Observability"])
async def liveness_probe():
    """
    Kubernetes Liveness Probe: Quick check ensuring the process is alive.
    """
    return {"status": "alive", "service": "gov-schemes-backend"}


@app.get("/health/ready", tags=["Observability"])
async def readiness_probe():
    """
    Kubernetes Readiness Probe: Verifies dependencies (SQLite knowledge store & vector index)
    are responsive before accepting ingress traffic.
    """
    try:
        store = get_knowledge_store()
        stats_data = store.get_statistics()
        if stats_data.get("total_schemes", 0) == 0:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "not_ready", "detail": "Knowledge base has 0 indexed schemes."},
            )
        return {
            "status": "ready",
            "schemes_ready": stats_data.get("total_schemes", 0),
        }
    except Exception as exc:
        logger.error(f"Readiness probe failure: {exc}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "error": str(exc)},
        )


@app.get("/metrics", tags=["Observability"])
async def get_metrics(request: Request, format: Optional[str] = None):
    """
    Exposes real-time system metrics.
    Returns Prometheus standard plaintext by default or JSON when requested.
    """
    accept = request.headers.get("accept", "")
    if format == "json" or "application/json" in accept:
        return JSONResponse(content=metrics.get_summary_json())
    return PlainTextResponse(content=metrics.export_prometheus_text(), media_type="text/plain; version=0.0.4")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
