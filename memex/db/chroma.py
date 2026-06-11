"""
ChromaDB vector store management for MEMEX.

Handles:
- Collection lifecycle
- Vector upsert / delete
- Similarity search with metadata filtering
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..config.settings import Settings, get_settings
from ..observability.logging import get_logger

logger = get_logger(__name__)


class ChromaStore:
    """ChromaDB persistent vector store wrapper."""

    def __init__(
        self,
        chroma_path: Optional[Path] = None,
        collection_name: Optional[str] = None,
        settings: Optional[Settings] = None,
    ):
        self._settings = settings or get_settings()
        self._chroma_path = chroma_path or self._settings.chroma_path
        self._collection_name = collection_name or self._settings.active_collection
        self._client = None
        self._collection = None

    def initialize(self) -> None:
        """Initialize the ChromaDB client and get/create the collection."""
        import chromadb

        self._chroma_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self._chroma_path))

        # Set cosine distance as default
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("chroma_initialized", collection=self._collection_name)

    @property
    def collection(self):
        if self._collection is None:
            self.initialize()
        return self._collection

    def upsert_vectors(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Upsert vectors into the collection."""
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        logger.debug("vectors_upserted", count=len(ids))

    def delete_vectors_by_document(self, document_id: str) -> int:
        """Delete all vectors for a given document_id."""
        try:
            result = self.collection.get(
                where={"document_id": document_id},
                include=[],
            )
            if result["ids"]:
                self.collection.delete(ids=result["ids"])
                logger.info("vectors_deleted", document_id=document_id, count=len(result["ids"]))
                return len(result["ids"])
            return 0
        except Exception as e:
            logger.error("chroma_delete_failed", document_id=document_id, error=str(e))
            return -1

    def delete_vectors_by_ids(self, chunk_ids: list[str]) -> bool:
        """Delete specific vectors by chunk ID."""
        try:
            self.collection.delete(ids=chunk_ids)
            return True
        except Exception as e:
            logger.error("chroma_delete_by_ids_failed", error=str(e))
            return False

    def query_vectors(
        self,
        query_embedding: list[float],
        n_results: int = 20,
        where: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Query for similar vectors."""
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        return self.collection.query(**kwargs)

    def count_vectors(self) -> int:
        """Total vector count in the active collection."""
        return self.collection.count()

    def verify_no_vectors_for_document(self, document_id: str) -> bool:
        """Verify that no vectors exist for a document (post-forget check)."""
        result = self.collection.get(
            where={"document_id": document_id},
            include=[],
        )
        return len(result["ids"]) == 0

    def get_collection_info(self) -> dict[str, Any]:
        """Get collection metadata for health checks."""
        try:
            count = self.count_vectors()
            return {
                "status": "ok",
                "total_chunks": count,
                "collection": self._collection_name,
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "collection": self._collection_name,
            }

    def health_check(self) -> dict[str, Any]:
        """Quick health check for the Chroma store."""
        try:
            count = self.count_vectors()
            return {"status": "ok", "total_chunks": count}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def create_collection(self, name: str) -> None:
        """Create a new collection (for model migration)."""
        if self._client is None:
            import chromadb
            self._chroma_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self._chroma_path))

        self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("collection_created", name=name)

    def delete_collection(self, name: str) -> None:
        """Delete a collection (old model cleanup)."""
        if self._client is None:
            import chromadb
            self._chroma_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self._chroma_path))

        self._client.delete_collection(name)
        logger.info("collection_deleted", name=name)
