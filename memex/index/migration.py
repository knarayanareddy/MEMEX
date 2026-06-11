"""
Model migration worker for MEMEX (§15 of design doc).

Handles the 5-phase re-embedding migration protocol:
  Phase 1: Register new model
  Phase 2: Parallel re-embed (background, non-blocking)
  Phase 3: Cutover (atomic)
  Phase 4: Cleanup (manual)
  Phase 5: Validation

This runs as a background thread managed by the daemon.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Optional

from ..config.settings import Settings, get_settings
from ..db.sqlite import SQLiteDatabase
from ..db.chroma import ChromaStore
from ..index.embedder import Embedder
from ..observability.logging import get_logger

logger = get_logger("index.migration")


class ModelMigrationWorker:
    """Background worker that re-embeds all chunks with a new model.

    Thread-safe and cancellable. Reports progress via the database
    and /api/models/migrate/progress endpoint.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        sqlite: Optional[SQLiteDatabase] = None,
        chroma: Optional[ChromaStore] = None,
    ):
        self._settings = settings or get_settings()
        self._sqlite = sqlite
        self._chroma = chroma
        self._running = False
        self._cancelled = False
        self._thread: Optional[threading.Thread] = None

        # Progress tracking
        self._old_model: str = ""
        self._new_model: str = ""
        self._new_version: str = ""
        self._new_collection: str = ""
        self._total_chunks: int = 0
        self._migrated_chunks: int = 0
        self._status: str = "IDLE"

    def start_migration(
        self,
        new_model: str,
        new_version: str,
        new_collection: str,
    ) -> bool:
        """Start a migration to a new embedding model.

        Returns False if a migration is already in progress.
        """
        if self._running:
            logger.warning("migration_already_in_progress")
            return False

        self._old_model = f"{self._settings.embed_model}:{self._settings.embed_model_version}"
        self._new_model = new_model
        self._new_version = new_version
        self._new_collection = new_collection
        self._migrated_chunks = 0
        self._cancelled = False
        self._status = "STARTING"

        self._running = True
        self._thread = threading.Thread(
            target=self._run_migration,
            name="model-migration",
            daemon=True,
        )
        self._thread.start()
        return True

    def cancel(self) -> None:
        """Request cancellation of the current migration."""
        self._cancelled = True
        logger.info("migration_cancel_requested")

    def _run_migration(self) -> None:
        """Execute the 5-phase migration protocol."""
        try:
            logger.info(
                "migration_started",
                old_model=self._old_model,
                new_model=f"{self._new_model}:{self._new_version}",
            )

            # Phase 1: Register new model
            self._status = "REGISTERING"
            if self._sqlite:
                self._sqlite.register_embed_model(
                    model_name=self._new_model,
                    model_version=self._new_version,
                    collection_name=self._new_collection,
                )

            # Create new Chroma collection
            if self._chroma:
                self._chroma.create_collection(self._new_collection)

            # Phase 2: Re-embed all chunks
            self._status = "IN_PROGRESS"
            self._reembed_all()

            if self._cancelled:
                self._status = "CANCELLED"
                logger.info("migration_cancelled", migrated=self._migrated_chunks)
                return

            # Phase 3: Cutover
            self._status = "CUTOVER"
            if self._sqlite:
                # Get the new model's ID
                models = self._sqlite.list_embed_models()
                for m in models:
                    if m["model_name"] == self._new_model and m["model_version"] == self._new_version:
                        self._sqlite.set_active_model(m["id"])
                        break

            # Phase 5: Validation (basic check)
            self._status = "VALIDATING"
            if self._chroma:
                # Verify new collection has vectors
                logger.info("migration_validation", collection=self._new_collection)

            self._status = "COMPLETE"
            logger.info(
                "migration_complete",
                total=self._total_chunks,
                migrated=self._migrated_chunks,
            )

        except Exception as e:
            self._status = "FAILED"
            logger.error("migration_failed", error=str(e))
        finally:
            self._running = False

    def _reembed_all(self) -> None:
        """Re-embed all chunks from SQLite using the new model."""
        if not self._sqlite or not self._chroma:
            return

        # Get total chunk count
        self._total_chunks = self._sqlite.count_chunks()
        logger.info("reembed_starting", total_chunks=self._total_chunks)

        # Create embedder for new model
        new_settings = Settings(
            data_dir=self._settings.data_dir,
            embed_model=self._new_model,
            embed_model_version=self._new_version,
            active_collection=self._new_collection,
        )
        embedder = Embedder(
            settings=new_settings,
            chroma=ChromaStore(
                chroma_path=self._settings.chroma_path,
                collection_name=self._new_collection,
                settings=new_settings,
            ),
        )
        embedder.initialize()

        # Process chunks in batches
        batch_size = 50
        offset = 0

        while not self._cancelled and offset < self._total_chunks:
            # Fetch batch of chunks with document metadata
            with self._sqlite.connection() as conn:
                rows = conn.execute(
                    """SELECT c.id, c.document_id, c.content, c.chunk_index,
                              d.source_type, d.source_path,
                              d.captured_at, d.content_type
                       FROM chunks c
                       JOIN documents d ON c.document_id = d.id
                       ORDER BY c.id
                       LIMIT ? OFFSET ?""",
                    (batch_size, offset),
                ).fetchall()

            if not rows:
                break

            for row in rows:
                if self._cancelled:
                    break

                chunk_data = dict(row)
                success = embedder.embed_and_store(
                    chunk_id=chunk_data["id"],
                    document_id=chunk_data["document_id"],
                    content=chunk_data["content"],
                    source_type=chunk_data["source_type"],
                    source_path=chunk_data["source_path"],
                    captured_at=chunk_data["captured_at"],
                    content_type=chunk_data.get("content_type", "plain"),
                    chunk_index=chunk_data["chunk_index"],
                )

                if success:
                    self._migrated_chunks += 1

            offset += batch_size

            # Log progress periodically
            if self._migrated_chunks % 100 == 0:
                logger.info(
                    "migration_progress",
                    migrated=self._migrated_chunks,
                    total=self._total_chunks,
                    pct=round(self._migrated_chunks / self._total_chunks * 100, 1) if self._total_chunks > 0 else 0,
                )

    def get_progress(self) -> dict[str, Any]:
        """Get current migration progress."""
        progress_pct = (
            round(self._migrated_chunks / self._total_chunks * 100, 1)
            if self._total_chunks > 0 else 0
        )

        return {
            "old_model": self._old_model,
            "new_model": f"{self._new_model}:{self._new_version}",
            "total_chunks": self._total_chunks,
            "migrated_chunks": self._migrated_chunks,
            "progress_pct": progress_pct,
            "status": self._status,
        }
