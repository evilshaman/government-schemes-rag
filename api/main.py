"""
FastAPI Main Application Entrypoint for Government Schemes Discovery & RAG Platform (Phase 4).
Mounts all REST API endpoints, CORS middleware, and serves the interactive web matching dashboard.
"""

from __future__ import annotations
import os
import sys
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from api.routes import upload, schemes, reasoner, chat, stats
from api.dependencies import get_knowledge_store, get_vector_store

logger = logging.getLogger("GovSchemesAPI")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan events: initialize and pre-warm knowledge store and vector store on startup.
    """
    logger.info("Starting up Government Schemes Discovery & RAG API...")
    try:
        store = get_knowledge_store()
        stats_info = store.get_statistics()
        logger.info(f"Connected to SQLite Knowledge Store: {stats_info.get('total_schemes', 0)} schemes active.")
        vs = get_vector_store()
        logger.info(f"Vector Store loaded with {len(vs.index_entries)} dense indexed documents.")
    except Exception as exc:
        logger.warning(f"Startup pre-warming notice: {exc}")
    yield
    logger.info("Shutting down Government Schemes Discovery API.")


app = FastAPI(
    title="Government Schemes Discovery & RAG Platform API",
    description="Enterprise-grade RAG backend matching businesses with central and state government schemes, subsidies, and credit facilities.",
    version="4.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware (supports Next.js frontend on localhost:3000 / other origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
        "message": "Government Schemes Discovery & RAG API is operational.",
        "docs_url": "/docs",
    })


@app.get("/health", tags=["Health"])
async def health_check():
    """
    System health check reporting database and vector store availability.
    """
    store = get_knowledge_store()
    stats_data = store.get_statistics()
    vs = get_vector_store()

    return {
        "status": "healthy",
        "service": "government-schemes-rag-backend",
        "version": "4.0.0",
        "knowledge_base": {
            "total_schemes": stats_data.get("total_schemes", 0),
            "total_guideline_chunks": stats_data.get("total_guideline_chunks", 0),
            "vector_index_entries": len(vs.index_entries),
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", credentials=None, host="0.0.0.0", port=8000, reload=True)
