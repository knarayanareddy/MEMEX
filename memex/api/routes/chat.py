"""Chat API routes — conversation management and streaming."""

from __future__ import annotations

import asyncio
from functools import partial

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from ...answer.chat import ChatEngine
from ..models import APIResponse, ChatRequest

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _get_chat_engine(request: Request) -> ChatEngine:
    return request.app.state.chat_engine


async def _run_sync(func, *args, **kwargs):
    """Run synchronous code in executor to avoid blocking the event loop."""
    loop = asyncio.get_running_loop()
    fn = partial(func, *args, **kwargs)
    return await loop.run_in_executor(None, fn)


@router.post("")
async def chat(request: Request, body: ChatRequest) -> APIResponse:
    """Single-turn chat with retrieval-augmented generation."""
    engine = _get_chat_engine(request)
    result = await _run_sync(engine.chat, body.session_id, body.query)
    return APIResponse(success=True, data=result)


@router.get("/stream")
async def chat_stream(request: Request, session_id: str, query: str):
    """SSE streaming chat."""
    engine = _get_chat_engine(request)

    async def event_generator():
        async for chunk in engine.chat_stream(session_id, query):
            yield chunk

    return EventSourceResponse(event_generator())


@router.get("/sessions")
async def list_sessions(request: Request) -> APIResponse:
    """List all chat sessions."""
    db = request.app.state.sqlite
    sessions = await _run_sync(db.list_conversations)
    return APIResponse(success=True, data={"sessions": sessions})


@router.get("/sessions/{session_id}")
async def get_session(request: Request, session_id: str) -> APIResponse:
    """Get session history."""
    db = request.app.state.sqlite
    history = await _run_sync(db.get_conversation_history, session_id, 100)
    return APIResponse(success=True, data={"session_id": session_id, "turns": history})


@router.delete("/sessions/{session_id}")
async def delete_session(request: Request, session_id: str) -> APIResponse:
    """Delete a chat session and all turns."""
    db = request.app.state.sqlite
    success = await _run_sync(db.delete_conversation, session_id)
    if success:
        return APIResponse(success=True, data={"deleted": session_id})
    return APIResponse(
        success=False,
        error={"code": "SESSION_NOT_FOUND", "message": f"No session with id {session_id}"},
    )
