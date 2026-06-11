"""
Pydantic models for MEMEX API request/response.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Response envelope
# ---------------------------------------------------------------------------

class ResponseMeta(BaseModel):
    request_id: str = ""
    duration_ms: float = 0
    version: str = "2.0.0"


class APIResponse(BaseModel):
    success: bool = True
    data: Any = None
    meta: ResponseMeta = Field(default_factory=ResponseMeta)
    error: Optional[dict[str, Any]] = None


class APIError(BaseModel):
    code: str
    message: str
    retryable: bool = False


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    session_id: str = Field(default_factory=lambda: str(__import__("uuid").uuid4()))
    query: str = Field(..., min_length=1, max_length=10000)


class CitationCard(BaseModel):
    index: int
    source_type: str
    source_path: str
    captured_at: str
    snippet: str
    score: float


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    citations: list[CitationCard] = Field(default_factory=list)
    sources_count: int = 0


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class SearchResult(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    score: float
    source_type: str
    source_path: str
    captured_at: str


class DocumentDetail(BaseModel):
    id: str
    source_type: str
    source_path: str
    content_type: Optional[str] = None
    word_count: Optional[int] = None
    status: str
    captured_at: str
    chunks: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    daemon_running: bool = True
    queue_depth: int = 0
    queue_max: int = 500
    stores: dict[str, Any] = Field(default_factory=dict)
    ollama: dict[str, Any] = Field(default_factory=dict)


class StatsResponse(BaseModel):
    total_documents: int = 0
    by_source_type: dict[str, int] = Field(default_factory=dict)
    total_chunks: int = 0
    embedding_coverage_pct: float = 0.0
    graph_coverage_pct: float = 0.0
    total_entities: int = 0
    total_relations: int = 0
    conversations: int = 0
    failed_documents: int = 0
