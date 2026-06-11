"""Memory API routes — search, timeline, document CRUD, forget."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Any, Optional

from fastapi import APIRouter, Query, Request

from ..models import APIResponse

router = APIRouter(prefix="/api/memory", tags=["memory"])


def _get_db(request: Request):
    return request.app.state.sqlite


def _get_retriever(request: Request):
    return request.app.state.retriever


def _get_forget_manager(request: Request):
    return request.app.state.forget_manager


async def _run_sync(func, *args, **kwargs):
    """Run a synchronous function in the default executor to avoid blocking the event loop."""
    loop = asyncio.get_running_loop()
    fn = partial(func, *args, **kwargs)
    return await loop.run_in_executor(None, fn)


@router.get("/search")
async def search_memory(
    request: Request,
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=50),
    after: Optional[str] = None,
    before: Optional[str] = None,
    source_type: Optional[str] = None,
) -> APIResponse:
    """Hybrid search across indexed memory."""
    retriever = _get_retriever(request)
    results = await _run_sync(
        retriever.search, q, limit=limit, after=after, before=before, source_type=source_type
    )
    return APIResponse(success=True, data={"results": results, "count": len(results)})


@router.get("/timeline")
async def timeline(
    request: Request,
    source_type: Optional[str] = None,
    after: Optional[str] = None,
    before: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> APIResponse:
    """Chronological document listing."""
    db = _get_db(request)
    docs = await _run_sync(
        db.list_documents,
        source_type=source_type, after=after, before=before, limit=limit, offset=offset,
    )
    for doc in docs:
        doc.pop("raw_content", None)
    return APIResponse(success=True, data={"documents": docs, "count": len(docs)})


@router.get("/{document_id}")
async def get_document(request: Request, document_id: str) -> APIResponse:
    """Fetch a single document with all chunks."""
    db = _get_db(request)
    doc = await _run_sync(db.get_document, document_id)
    if not doc:
        return APIResponse(
            success=False,
            error={"code": "DOCUMENT_NOT_FOUND", "message": f"No document with id {document_id}"},
        )
    doc.pop("raw_content", None)
    chunks = await _run_sync(db.get_chunks_for_document, document_id)
    doc["chunks"] = chunks
    return APIResponse(success=True, data=doc)


@router.delete("/{document_id}")
async def forget_document(request: Request, document_id: str) -> APIResponse:
    """Hard forget — 10-step protocol across all stores."""
    forget_mgr = _get_forget_manager(request)
    result = await _run_sync(forget_mgr.forget_document, document_id)
    if result.get("success"):
        return APIResponse(success=True, data=result)
    return APIResponse(
        success=False, data=result,
        error={"code": "FORGET_FAILED", "message": result.get("error", "Unknown error")},
    )


@router.delete("/source/{source_type}")
async def forget_by_source(request: Request, source_type: str) -> APIResponse:
    """Bulk forget all documents of a source type."""
    forget_mgr = _get_forget_manager(request)
    result = await _run_sync(forget_mgr.forget_by_source_type, source_type)
    return APIResponse(success=True, data=result)


@router.get("/forget/verify/{document_id}")
async def verify_forget(request: Request, document_id: str) -> APIResponse:
    """Verify forget completion across all stores."""
    forget_mgr = _get_forget_manager(request)
    result = await _run_sync(forget_mgr.verify_forget, document_id)
    return APIResponse(success=True, data=result)
