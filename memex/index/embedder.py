"""
Embedding pipeline for MEMEX.

Generates embeddings via Ollama and upserts to ChromaDB.
Handles retry logic for Ollama unavailability.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from ..config.settings import Settings, get_settings
from ..db.chroma import ChromaStore
from ..observability.logging import get_logger
from ..observability.metrics import get_metrics

logger = get_logger("index.embedder")
metrics = get_metrics()


class Embedder:
    """Generates embeddings via Ollama and stores in ChromaDB."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        chroma: Optional[ChromaStore] = None,
    ):
        self._settings = settings or get_settings()
        self._chroma = chroma or ChromaStore(settings=self._settings)
        self._client = httpx.Client(
            base_url=self._settings.ollama_base_url,
            timeout=60.0,
        )

    def initialize(self) -> None:
        """Initialize the ChromaDB collection."""
        self._chroma.initialize()

    def embed_text(self, text: str) -> Optional[list[float]]:
        """Generate embedding for a single text string."""
        try:
            response = self._client.post(
                "/api/embed",
                json={
                    "model": self._settings.embed_model,
                    "input": text,
                },
            )
            response.raise_for_status()
            data = response.json()
            embeddings = data.get("embeddings", [])
            if embeddings:
                return embeddings[0]
            return None
        except Exception as e:
            logger.error("embed_error", error=str(e))
            return None

    def embed_batch(self, texts: list[str]) -> list[Optional[list[float]]]:
        """Generate embeddings for a batch of texts."""
        try:
            response = self._client.post(
                "/api/embed",
                json={
                    "model": self._settings.embed_model,
                    "input": texts,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("embeddings", [])
        except Exception as e:
            logger.error("embed_batch_error", error=str(e))
            return [None] * len(texts)

    def embed_and_store(
        self,
        chunk_id: str,
        document_id: str,
        content: str,
        source_type: str,
        source_path: str,
        captured_at: str,
        content_type: str,
        chunk_index: int,
        retry_count: int = 3,
    ) -> bool:
        """Embed a chunk and store in ChromaDB.

        Returns True on success, False on failure.
        Implements retry with exponential backoff (ADR-004).
        """
        backoff = [1, 2, 4]

        for attempt in range(retry_count):
            try:
                vector = self.embed_text(content)
                if vector is None:
                    raise RuntimeError("Embedding returned None")

                metadata = {
                    "document_id": document_id,
                    "source_type": source_type,
                    "source_path": source_path,
                    "captured_at": captured_at,
                    "content_type": content_type,
                    "chunk_index": chunk_index,
                    "embed_model": self._settings.embed_model,
                    "embed_model_version": self._settings.embed_model_version,
                }

                self._chroma.upsert_vectors(
                    ids=[chunk_id],
                    embeddings=[vector],
                    documents=[content],
                    metadatas=[metadata],
                )

                metrics.observe("embedding_latency_ms", 0)  # Placeholder
                logger.info(
                    "embed_complete",
                    chunk_id=chunk_id[:16],
                    document_id=document_id[:16],
                )
                return True

            except Exception as e:
                wait = backoff[min(attempt, len(backoff) - 1)]
                logger.warning(
                    "embed_retry",
                    chunk_id=chunk_id[:16],
                    attempt=attempt + 1,
                    wait_seconds=wait,
                    error=str(e),
                )
                time.sleep(wait)

        logger.error(
            "embed_failed",
            chunk_id=chunk_id[:16],
            document_id=document_id[:16],
            attempts=retry_count,
        )
        return False

    def is_ollama_available(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            response = self._client.get("/api/tags", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False

    def get_available_models(self) -> list[str]:
        """List available Ollama models."""
        try:
            response = self._client.get("/api/tags", timeout=5.0)
            response.raise_for_status()
            data = response.json()
            return [m.get("name", "") for m in data.get("models", [])]
        except Exception:
            return []
