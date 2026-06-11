"""
Chat engine for MEMEX.

Handles:
- Context window budgeting
- Prompt construction
- Ollama chat completion
- Citation extraction and rendering
- Streaming support
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

import httpx

from ..config.settings import (
    ConversationTurn,
    Settings,
    get_settings,
    load_chunking,
)
from ..db.sqlite import SQLiteDatabase
from ..observability.logging import get_logger
from ..recall.hybrid_retrieval import HybridRetriever
from .prompt import build_prompt, build_context

logger = get_logger("answer.chat")


class ChatEngine:
    """Chat engine with retrieval-augmented generation."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        sqlite: Optional[SQLiteDatabase] = None,
        retriever: Optional[HybridRetriever] = None,
    ):
        self._settings = settings or get_settings()
        self._sqlite = sqlite
        self._retriever = retriever
        self._client = httpx.Client(
            base_url=self._settings.ollama_base_url,
            timeout=120.0,
        )
        self._async_client: Optional[httpx.AsyncClient] = None

        chunking_config = load_chunking()
        self._max_context_tokens = chunking_config.get("context_window", {}).get(
            "max_context_tokens", 6000
        )
        self._history_turns = chunking_config.get("context_window", {}).get(
            "conversation_history_turns", 6
        )

    async def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                base_url=self._settings.ollama_base_url,
                timeout=120.0,
            )
        return self._async_client

    def chat(self, session_id: str, query: str) -> dict[str, Any]:
        """Execute a single-turn chat.

        Args:
            session_id: Conversation session ID.
            query: User's question.

        Returns:
            Dict with answer, sources, session_id.
        """
        # Ensure session exists
        if self._sqlite:
            session = self._get_or_create_session(session_id)

        # Retrieve relevant context
        retrieval_results = []
        if self._retriever:
            retrieval_results = self._retriever.retrieve(query)

        # Budget context window
        budgeted_results = self._budget_context(retrieval_results)

        # Get conversation history
        history = []
        if self._sqlite:
            history = self._sqlite.get_conversation_history(session_id, self._history_turns)

        # Build prompt
        prompt = build_prompt(query, budgeted_results, history, self._history_turns)

        # Call Ollama
        answer = self._call_llm(prompt)

        # Extract cited source indices
        cited_sources = self._extract_citations(answer)

        # Get chunk IDs for cited sources
        cited_chunk_ids = []
        for result in budgeted_results:
            if result.citation_index in cited_sources:
                cited_chunk_ids.append(result.chunk_id)

        # Save turns to database
        if self._sqlite:
            self._sqlite.add_conversation_turn(
                session_id=session_id,
                role="user",
                content=query,
            )
            self._sqlite.add_conversation_turn(
                session_id=session_id,
                role="assistant",
                content=answer,
                sources_cited=cited_chunk_ids,
            )

            # Auto-generate title from first turn
            if len(history) == 0:
                title = query[:100]
                with self._sqlite.connection() as conn:
                    conn.execute(
                        "UPDATE conversations SET title = ? WHERE id = ?",
                        (title, session_id),
                    )

        # Format citations for response
        citations = self._format_citations(budgeted_results, cited_sources)

        logger.info(
            "answer_generated",
            session_id=session_id[:16],
            query_length=len(query),
            answer_length=len(answer),
            sources_cited=len(cited_chunk_ids),
        )

        return {
            "session_id": session_id,
            "answer": answer,
            "citations": citations,
            "sources_count": len(budgeted_results),
        }

    async def chat_stream(self, session_id: str, query: str) -> AsyncGenerator[str, None]:
        """Stream chat response via SSE.

        Args:
            session_id: Conversation session ID.
            query: User's question.

        Yields:
            SSE-formatted data chunks.
        """
        # Retrieve context
        retrieval_results = []
        if self._retriever:
            retrieval_results = self._retriever.retrieve(query)

        budgeted_results = self._budget_context(retrieval_results)

        # Get history
        history = []
        if self._sqlite:
            history = self._sqlite.get_conversation_history(session_id, self._history_turns)

        prompt = build_prompt(query, budgeted_results, history, self._history_turns)

        # Stream from Ollama
        client = await self._get_async_client()

        full_answer = ""
        try:
            async with client.stream(
                "POST",
                "/api/chat",
                json={
                    "model": self._settings.chat_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True,
                },
            ) as response:
                async for line in response.aiter_lines():
                    if line.strip():
                        try:
                            data = json.loads(line)
                            content = data.get("message", {}).get("content", "")
                            if content:
                                full_answer += content
                                yield f"data: {json.dumps({'token': content})}\n\n"
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            logger.error("stream_error", error=str(e))
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        # Save to database
        if self._sqlite:
            self._sqlite.add_conversation_turn(session_id, "user", query)
            cited = self._extract_citations(full_answer)
            cited_chunk_ids = [
                r.chunk_id for r in budgeted_results if r.citation_index in cited
            ]
            self._sqlite.add_conversation_turn(
                session_id, "assistant", full_answer, cited_chunk_ids
            )

        yield f"data: {json.dumps({'done': True})}\n\n"

    def _call_llm(self, prompt: str) -> str:
        """Call Ollama for chat completion."""
        try:
            response = self._client.post(
                "/api/chat",
                json={
                    "model": self._settings.chat_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")
        except Exception as e:
            logger.error("llm_call_error", error=str(e))
            return f"I'm unable to generate a response right now. Error: {str(e)}"

    def _budget_context(self, results: list) -> list:
        """Budget context window — include chunks until token limit."""
        budgeted = []
        accumulated = 0

        for result in results:
            # Rough token count estimate
            token_count = max(1, len(result.content) // 4)
            if accumulated + token_count <= self._max_context_tokens:
                budgeted.append(result)
                accumulated += token_count
            else:
                break

        return budgeted

    @staticmethod
    def _extract_citations(answer: str) -> set[int]:
        """Extract [Source N] citation indices from LLM response."""
        return {int(m) for m in re.findall(r'\[Source (\d+)\]', answer)}

    @staticmethod
    def _format_citations(results: list, cited_indices: set[int]) -> list[dict]:
        """Format citation cards for UI rendering."""
        citations = []
        for result in results:
            if result.citation_index in cited_indices:
                citations.append({
                    "index": result.citation_index,
                    "source_type": result.source_type,
                    "source_path": result.source_path,
                    "captured_at": result.captured_at.isoformat() if hasattr(result.captured_at, "isoformat") else str(result.captured_at),
                    "snippet": result.content[:200] + "..." if len(result.content) > 200 else result.content,
                    "score": round(result.combined_score, 4),
                })
        return citations

    def _get_or_create_session(self, session_id: str) -> str:
        """Get or create a conversation session."""
        if self._sqlite:
            existing = self._sqlite.get_conversation_history(session_id, limit=1)
            if not existing:
                # Check if session exists
                with self._sqlite.connection() as conn:
                    row = conn.execute(
                        "SELECT id FROM conversations WHERE id = ?", (session_id,)
                    ).fetchone()
                    if not row:
                        self._sqlite.create_conversation()
        return session_id
