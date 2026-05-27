"""FastAPI app entry point.

Espone:
- /api/papers       Ingest e selezione paper scientifici
- /api/content      CRUD draft, approve/reject
- /api/generation   Generazione AI multi-provider
- /api/validation   Validazione contenuti + fonti
- /api/schedule     Calendario editoriale
- /api/analytics    Performance Instagram
- /                 Dashboard web statica
"""
from __future__ import annotations

import logging
import pathlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .core.config import settings
from .core.logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Dental AI Content System",
        description="Pipeline scientifica per contenuti Instagram su AI in odontoiatria",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.APP_ENV != "production" else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers (lazy import per evitare cicli)
    from .api import (
        papers, content as content_api, generation, validation, schedule,
        analytics, render, wizard, publish,
    )

    app.include_router(papers.router, prefix="/api/papers", tags=["papers"])
    app.include_router(content_api.router, prefix="/api/content", tags=["content"])
    app.include_router(generation.router, prefix="/api/generation", tags=["generation"])
    app.include_router(validation.router, prefix="/api/validation", tags=["validation"])
    app.include_router(schedule.router, prefix="/api/schedule", tags=["schedule"])
    app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
    app.include_router(render.router, prefix="/api/render", tags=["render"])
    app.include_router(wizard.router, prefix="/api/wizard", tags=["wizard"])
    app.include_router(publish.router, prefix="/api/publish", tags=["publish"])

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "env": settings.APP_ENV,
            "providers_configured": settings.configured_providers,
            "default_provider": settings.DEFAULT_AI_PROVIDER,
        }

    @app.exception_handler(ValueError)
    async def value_error_handler(_, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    # Frontend statico (dashboard)
    frontend_dir = pathlib.Path(__file__).resolve().parents[2] / "frontend"
    if frontend_dir.is_dir():
        app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

        @app.get("/", include_in_schema=False)
        def root() -> FileResponse:
            return FileResponse(frontend_dir / "index.html")

    # PNG renderizzati (immagini delle slide pronte per Instagram)
    renders_dir = pathlib.Path("/app/renders")
    renders_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/renders", StaticFiles(directory=renders_dir), name="renders")

    return app


app = create_app()
