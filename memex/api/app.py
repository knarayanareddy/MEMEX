"""
FastAPI application factory for MEMEX.

Creates and configures the FastAPI app with:
- Loopback-only middleware
- All route modules
- Static file serving for Web UI
- Application state management
- Lifespan event handling (replaces deprecated on_event)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ..config.settings import Settings, get_settings
from ..db.chroma import ChromaStore
from ..db.kuzu import KuzuGraph
from ..db.sqlite import SQLiteDatabase
from ..protect.forget import ForgetManager
from ..recall.hybrid_retrieval import HybridRetriever
from ..answer.chat import ChatEngine
from ..ingest.queue import IngestionQueue
from ..index.migration import ModelMigrationWorker
from ..observability.slos import SLOMonitor
from ..observability.logging import get_logger
from .middleware import LoopbackOnlyMiddleware, RequestTimingMiddleware
from .routes import chat, graph, memory, system

logger = get_logger("api.app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FIX: Replaces deprecated on_event with proper lifespan handler."""
    settings = getattr(app.state, "settings", None)
    host = settings.api_host if settings else "unknown"
    port = settings.api_port if settings else "unknown"
    logger.info("api_started", host=host, port=port)
    yield
    logger.info("api_shutdown")


def create_app(
    settings: Settings | None = None,
    sqlite: SQLiteDatabase | None = None,
    chroma: ChromaStore | None = None,
    kuzu: KuzuGraph | None = None,
) -> FastAPI:
    """Create and configure the MEMEX FastAPI application."""
    _settings = settings or get_settings()

    app = FastAPI(
        title="MEMEX",
        version="2.0.0",
        description="Local-First Passive Second Brain",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    # Middleware (order matters: outermost first)
    app.add_middleware(RequestTimingMiddleware)
    app.add_middleware(LoopbackOnlyMiddleware)

    # Initialize stores
    _sqlite = sqlite or SQLiteDatabase(settings=_settings)
    _chroma = chroma or ChromaStore(settings=_settings)
    _kuzu = kuzu or KuzuGraph(settings=_settings)

    _queue = IngestionQueue()

    _retriever = HybridRetriever(
        settings=_settings, sqlite=_sqlite, chroma=_chroma, kuzu=_kuzu,
    )

    _chat_engine = ChatEngine(
        settings=_settings, sqlite=_sqlite, retriever=_retriever,
    )

    _forget_manager = ForgetManager(
        settings=_settings, sqlite=_sqlite, chroma=_chroma, kuzu=_kuzu,
    )

    _migration_worker = ModelMigrationWorker(
        settings=_settings, sqlite=_sqlite, chroma=_chroma,
    )

    _slo_monitor = SLOMonitor()

    # Store in app state
    app.state.settings = _settings
    app.state.sqlite = _sqlite
    app.state.chroma = _chroma
    app.state.kuzu = _kuzu
    app.state.queue = _queue
    app.state.retriever = _retriever
    app.state.chat_engine = _chat_engine
    app.state.forget_manager = _forget_manager
    app.state.migration_worker = _migration_worker
    app.state.slo_monitor = _slo_monitor

    # Register routes
    app.include_router(memory.router)
    app.include_router(chat.router)
    app.include_router(graph.router)
    app.include_router(system.router)

    # Static files for Web UI
    web_dir = Path(__file__).parent.parent / "web" / "static"
    if web_dir.exists():
        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")

    return app
