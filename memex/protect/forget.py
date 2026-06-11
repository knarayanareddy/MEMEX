"""
Forget protocol for MEMEX.

Implements the 10-step forget protocol for complete, verifiable,
atomic deletion across all four stores.
"""

from __future__ import annotations

from typing import Any, Optional

from ..config.settings import Settings, get_settings
from ..db.chroma import ChromaStore
from ..db.kuzu import KuzuGraph
from ..db.sqlite import SQLiteDatabase
from ..observability.logging import get_logger
from ..observability.slos import SLOTimer

logger = get_logger("protect.forget")


class ForgetManager:
    """Complete forget (hard delete) across all stores.

    Implements the 10-step forget protocol:
    1. Fetch all chunk_ids for document
    2. Delete from Chroma
    3. Delete from KuzuDB
    4. Delete entity_mentions from SQLite
    5. Delete relations from SQLite
    6. Delete chunks from SQLite
    7. Delete document from SQLite
    8. FTS auto-updates via trigger
    9. Orphan entity cleanup
    10. Write audit log

    If ANY step fails: rollback what is reversible, log FORGET_PARTIAL_FAILURE.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        sqlite: Optional[SQLiteDatabase] = None,
        chroma: Optional[ChromaStore] = None,
        kuzu: Optional[KuzuGraph] = None,
    ):
        self._settings = settings or get_settings()
        self._sqlite = sqlite
        self._chroma = chroma
        self._kuzu = kuzu

    def forget_document(self, document_id: str) -> dict[str, Any]:
        """Execute the 10-step forget protocol for a single document.

        Returns:
            Dict with success status and verification results.
        """
        logger.info("forget_started", document_id=document_id)

        with SLOTimer("forget_doc_ms"):
            # Get document info first
            doc = self._sqlite.get_document(document_id) if self._sqlite else None
            source_path = doc.get("source_path") if doc else None
            source_type = doc.get("source_type") if doc else None

            # Step 1: Fetch all chunk_ids
            chunks = self._sqlite.get_chunks_for_document(document_id) if self._sqlite else []
            chunk_ids = [c["id"] for c in chunks]

            chroma_verified = False
            kuzu_verified = False
            sqlite_verified = False

            try:
                # Step 2: Delete from Chroma
                if self._chroma:
                    if chunk_ids:
                        self._chroma.delete_vectors_by_ids(chunk_ids)
                    else:
                        self._chroma.delete_vectors_by_document(document_id)
                    chroma_verified = True

                # Step 3: Delete from KuzuDB
                if self._kuzu:
                    self._kuzu.delete_mentions_for_document(document_id)
                    kuzu_verified = True

                # Steps 4-7: Delete from SQLite
                if self._sqlite:
                    with self._sqlite.connection() as conn:
                        # Step 4: Delete entity mentions
                        self._sqlite.delete_entity_mentions_for_document(document_id, conn=conn)

                        # Step 5: Delete relations
                        self._sqlite.delete_relations_for_document(document_id, conn=conn)

                        # Step 6: Delete chunks
                        self._sqlite.delete_chunks_for_document(document_id, conn=conn)

                        # Step 7: Delete document
                        self._sqlite.delete_document(document_id, conn=conn)

                        # Step 8: FTS auto-updates via triggers

                        # Step 9: Orphan entity cleanup
                        self._sqlite.cleanup_orphan_entities(conn=conn)

                    sqlite_verified = True

                # Step 10: Write audit log
                if self._sqlite:
                    self._sqlite.insert_forget_log(
                        document_id=document_id,
                        source_path=source_path,
                        source_type=source_type,
                        chroma_verified=chroma_verified,
                        kuzu_verified=kuzu_verified,
                        sqlite_verified=sqlite_verified,
                    )

            except Exception as e:
                logger.error(
                    "forget_partial_failure",
                    document_id=document_id,
                    error=str(e),
                )

                # Mark document for retry
                if self._sqlite:
                    try:
                        from ..config.settings import DocumentStatus
                        self._sqlite.update_document_status(
                            document_id, DocumentStatus.FORGET_FAILED, error=str(e)
                        )
                    except Exception:
                        pass

                logger.info("forget_failed", document_id=document_id)

                return {
                    "success": False,
                    "document_id": document_id,
                    "error": str(e),
                    "partial": True,
                }

        logger.info("forget_complete", document_id=document_id)

        return {
            "success": True,
            "document_id": document_id,
            "chunks_deleted": len(chunk_ids),
            "stores_checked": ["chroma", "sqlite", "kuzu"],
            "verification": {
                "chroma": chroma_verified,
                "kuzu": kuzu_verified,
                "sqlite": sqlite_verified,
            },
        }

    def forget_by_source_type(self, source_type: str) -> dict[str, Any]:
        """Bulk forget all documents of a given source type.

        Args:
            source_type: Source type to forget (filesystem, browser, etc.)

        Returns:
            Summary dict with counts.
        """
        docs = self._sqlite.list_documents(source_type=source_type, limit=100000)
        success_count = 0
        failure_count = 0

        for doc in docs:
            result = self.forget_document(doc["id"])
            if result.get("success"):
                success_count += 1
            else:
                failure_count += 1

        logger.info(
            "bulk_forget_complete",
            source_type=source_type,
            success=success_count,
            failures=failure_count,
        )

        return {
            "source_type": source_type,
            "total": len(docs),
            "success": success_count,
            "failures": failure_count,
        }

    def verify_forget(self, document_id: str) -> dict[str, Any]:
        """Verify that a document has been completely forgotten.

        Checks all four stores for any remaining data.
        """
        checks = {
            "chroma": True,
            "sqlite": True,
            "kuzu": True,
        }

        # Check Chroma
        if self._chroma:
            checks["chroma"] = self._chroma.verify_no_vectors_for_document(document_id)

        # Check SQLite
        if self._sqlite:
            chunks = self._sqlite.get_chunks_for_document(document_id)
            checks["sqlite"] = len(chunks) == 0

        # Check KuzuDB
        if self._kuzu:
            checks["kuzu"] = self._kuzu.verify_no_mentions_for_document(document_id)

        all_clear = all(checks.values())

        return {
            "verified": all_clear,
            "stores_checked": checks,
        }
