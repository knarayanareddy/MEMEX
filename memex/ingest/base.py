"""
Base ingestor interface for MEMEX.

All ingestors inherit from BaseIngestor and emit RawDocument objects.
"""

from __future__ import annotations

import abc
import threading
from typing import TYPE_CHECKING

from ..config.settings import Priority, RawDocument
from ..observability.logging import get_logger

if TYPE_CHECKING:
    from .queue import IngestionQueue

logger = get_logger("ingest.base")


class BaseIngestor(abc.ABC):
    """Abstract base class for all ingestors."""

    source_type: str = "base"

    def __init__(self, queue: "IngestionQueue"):
        self._queue = queue
        self._running = False
        self._thread: threading.Thread | None = None

    @abc.abstractmethod
    def poll(self) -> list[RawDocument]:
        """Poll the source and return new RawDocument objects.

        This method is called on each poll cycle. It should be non-blocking
        and return an empty list if no new items are found.
        """
        ...

    def start(self) -> None:
        """Start the ingestor in a background thread."""
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"ingest-{self.source_type}",
            daemon=True,
        )
        self._thread.start()
        logger.info("ingestor_started", source_type=self.source_type)

    def stop(self) -> None:
        """Stop the ingestor."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("ingestor_stopped", source_type=self.source_type)

    def _run_loop(self) -> None:
        """Main ingestor loop: poll, emit, sleep, repeat."""
        import time

        while self._running:
            try:
                documents = self.poll()
                for doc in documents:
                    self._queue.put(doc)
                    logger.info(
                        "document_ingested",
                        source_type=doc.source_type,
                        source_path=doc.source_path[:100],
                        checksum=doc.checksum[:16],
                        priority=doc.priority.name,
                    )
            except Exception as e:
                logger.error(
                    "ingestor_poll_error",
                    source_type=self.source_type,
                    error=str(e),
                )
            time.sleep(self.poll_interval_seconds)

    @property
    def poll_interval_seconds(self) -> float:
        """Override in subclasses for different poll intervals."""
        return 60.0
