"""Graph API routes — entity and relation queries."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Optional

from fastapi import APIRouter, Query, Request

from ...db.sqlite import SQLiteDatabase
from ..models import APIResponse

router = APIRouter(prefix="/api/graph", tags=["graph"])


async def _run_sync(func, *args, **kwargs):
    """Run synchronous code in executor."""
    loop = asyncio.get_running_loop()
    fn = partial(func, *args, **kwargs)
    return await loop.run_in_executor(None, fn)


@router.get("/entities")
async def list_entities(
    request: Request,
    q: Optional[str] = None,
    type: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
) -> APIResponse:
    """List entities with optional search."""
    db: SQLiteDatabase = request.app.state.sqlite
    if q:
        entities = await _run_sync(db.search_entities, q, type, limit)
    else:
        def _list_all(db=db, limit=limit):
            with db.connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM entities ORDER BY mention_count DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]
        entities = await _run_sync(_list_all)
    return APIResponse(success=True, data={"entities": entities})


@router.get("/entity/{entity_id}")
async def get_entity(request: Request, entity_id: str) -> APIResponse:
    """Get entity with neighbors."""
    kuzu = request.app.state.kuzu
    if not kuzu:
        return APIResponse(success=False, error={"code": "GRAPH_UNAVAILABLE"})

    result = await _run_sync(kuzu.get_entity_with_neighbors, entity_id)
    if not result:
        return APIResponse(success=False, error={"code": "ENTITY_NOT_FOUND"})
    return APIResponse(success=True, data=result)


@router.get("/relations")
async def list_relations(
    request: Request,
    subject_id: Optional[str] = None,
    object_id: Optional[str] = None,
    predicate: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
) -> APIResponse:
    """List relations with optional filters."""
    db: SQLiteDatabase = request.app.state.sqlite

    def _query_relations():
        with db.connection() as conn:
            query = "SELECT * FROM relations WHERE 1=1"
            params = []
            if subject_id:
                query += " AND subject_id = ?"
                params.append(subject_id)
            if object_id:
                query += " AND object_id = ?"
                params.append(object_id)
            if predicate:
                query += " AND predicate = ?"
                params.append(predicate)
            query += " ORDER BY confidence DESC LIMIT ?"
            params.append(limit)
            return [dict(r) for r in conn.execute(query, params).fetchall()]

    relations = await _run_sync(_query_relations)
    return APIResponse(success=True, data={"relations": relations})
