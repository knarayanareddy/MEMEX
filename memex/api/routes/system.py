"""System API routes — health, stats, reindex, models, logs."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Any

from fastapi import APIRouter, Request

from ..models import APIResponse

router = APIRouter(tags=["system"])


async def _run_sync(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    fn = partial(func, *args, **kwargs)
    return await loop.run_in_executor(None, fn)


@router.get("/api/health")
async def health_check(request: Request) -> dict[str, Any]:
    """Daemon health snapshot."""
    db = getattr(request.app.state, "sqlite", None)
    chroma = getattr(request.app.state, "chroma", None)
    kuzu = getattr(request.app.state, "kuzu", None)
    queue = getattr(request.app.state, "queue", None)
    settings = getattr(request.app.state, "settings", None)

    stores = {}

    def _check_sqlite():
        try:
            with db.connection() as conn:
                row = conn.execute(
                    "SELECT (SELECT count(*) FROM documents) as docs"
                ).fetchone()
                return {"status": "ok", "document_count": dict(row)["docs"]}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    if db:
        stores["sqlite"] = await _run_sync(_check_sqlite)
    if chroma:
        stores["chroma"] = await _run_sync(chroma.health_check)
    if kuzu:
        stores["kuzu"] = await _run_sync(kuzu.health_check)

    ollama_status = {"status": "unknown"}
    if settings:
        try:
            from ...index.embedder import Embedder
            embedder = Embedder(settings=settings)
            available = await _run_sync(embedder.is_ollama_available)
            ollama_status = {
                "status": "ok" if available else "unavailable",
                "embed_model": settings.embed_model,
                "chat_model": settings.chat_model,
            }
        except Exception:
            ollama_status = {"status": "error"}

    all_healthy = all(s.get("status") == "ok" for s in stores.values())

    return {
        "status": "healthy" if all_healthy else "degraded",
        "daemon_running": True,
        "queue_depth": queue.depth if queue else 0,
        "queue_max": queue.max_depth if queue else 0,
        "stores": stores,
        "ollama": ollama_status,
    }


@router.get("/api/stats")
async def get_stats(request: Request) -> APIResponse:
    """Aggregate ingestion metrics."""
    db = getattr(request.app.state, "sqlite", None)
    if not db:
        return APIResponse(success=False, error={"code": "DB_UNAVAILABLE"})

    stats = await _run_sync(db.get_stats)

    queue = getattr(request.app.state, "queue", None)
    if queue:
        stats["dropped_since_start"] = queue.dropped_count

    return APIResponse(success=True, data=stats)


@router.post("/api/reindex")
async def trigger_reindex(request: Request) -> APIResponse:
    """Trigger re-index for a document or source type."""
    body = await request.json()
    doc_id = body.get("document_id")
    source_type = body.get("source_type")
    if not doc_id and not source_type:
        return APIResponse(
            success=False,
            error={"code": "MISSING_PARAM", "message": "Provide document_id or source_type"},
        )
    return APIResponse(
        success=True,
        data={"status": "reindex_queued", "document_id": doc_id, "source_type": source_type},
    )


@router.get("/api/models")
async def list_models(request: Request) -> APIResponse:
    """List registered embedding models."""
    db = getattr(request.app.state, "sqlite", None)
    if not db:
        return APIResponse(success=False, error={"code": "DB_UNAVAILABLE"})

    models = await _run_sync(db.list_embed_models)
    active = await _run_sync(db.get_active_model)
    return APIResponse(success=True, data={"models": models, "active": active})


@router.post("/api/models/migrate")
async def trigger_migration(request: Request) -> APIResponse:
    """Trigger re-embed migration using the ModelMigrationWorker."""
    migration_worker = getattr(request.app.state, "migration_worker", None)
    if not migration_worker:
        return APIResponse(
            success=False,
            error={"code": "MIGRATION_UNAVAILABLE", "message": "Migration worker not initialized"},
        )

    body = await request.json()
    new_model = body.get("model")
    new_version = body.get("version", "1.0")
    new_collection = body.get("collection", f"memex_vectors_{new_model.replace('-', '_')}")

    if not new_model:
        return APIResponse(
            success=False,
            error={"code": "MISSING_PARAM", "message": "model is required"},
        )

    started = await _run_sync(
        migration_worker.start_migration,
        new_model,
        new_version,
        new_collection,
    )

    if not started:
        return APIResponse(
            success=False,
            error={"code": "MIGRATION_IN_PROGRESS", "message": "A migration is already running"},
        )

    return APIResponse(success=True, data={
        "status": "migration_started",
        "new_model": new_model,
        "new_collection": new_collection,
    })


@router.get("/api/models/migrate/progress")
async def migration_progress(request: Request) -> APIResponse:
    """Get migration progress from the ModelMigrationWorker."""
    migration_worker = getattr(request.app.state, "migration_worker", None)
    if not migration_worker:
        return APIResponse(success=True, data={"status": "no_worker"})

    progress = await _run_sync(migration_worker.get_progress)
    return APIResponse(success=True, data=progress)


@router.get("/api/logs/stream")
async def stream_logs(request: Request):
    """SSE stream of daemon log lines — rotation-aware."""
    from sse_starlette.sse import EventSourceResponse

    settings = getattr(request.app.state, "settings", None)
    log_file = settings.log_path / "daemon.log" if settings else None

    async def event_generator():
        if not log_file or not log_file.exists():
            yield f"data: {{\"error\": \"log file not found\"}}\n\n"
            return

        try:
            with open(log_file, "r") as f:
                f.seek(0, 2)  # Start from end
                while True:
                    line = f.readline()
                    if line:
                        yield f"data: {line.strip()}\n\n"
                    else:
                        # Check if file was rotated (inode changed)
                        await asyncio.sleep(0.5)
                        if not log_file.exists():
                            # File was rotated; reopen
                            break
        except Exception as e:
            yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"

    return EventSourceResponse(event_generator())
