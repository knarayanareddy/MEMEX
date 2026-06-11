"""
Priority queue with bounded depth for MEMEX ingestion.

ADR-006: A PriorityQueue with configurable max_depth.
Priority tiers: CRITICAL > HIGH > NORMAL > LOW.
When full, new items are DROPPED with a structured log entry.
"""

from __future__ import annotations

import queue
import threading
from typing import Optional

from ..config.settings import Priority, RawDocument
from ..config.settings import load_retention
from ..observability.logging import get_logger
from ..observability.metrics import get_metrics

logger = get_logger("ingest.queue")
metrics = get_metrics()


class IngestionQueue:
    """Bounded priority queue for raw documents.

    Implements ADR-006:
    - Configurable max_depth from Addendum B
    - Priority tiers: CRITICAL > HIGH > NORMAL > LOW
    - DROP with structured log when full (never silent)
    - Queue depth surfaced in metrics and /health
    """

    def __init__(
        self,
        max_depth: Optional[int] = None,
        warn_threshold: Optional[int] = None,
    ):
        retention = load_retention()
        queue_config = retention.get("queue", {})

        self._max_depth = max_depth or queue_config.get("max_depth", 500)
        self._warn_threshold = warn_threshold or queue_config.get("warn_threshold", 400)

        self._queue: queue.PriorityQueue[RawDocument] = queue.PriorityQueue(
            maxsize=self._max_depth
        )
        self._dropped_count = 0
        self._lock = threading.Lock()

    def put(self, doc: RawDocument) -> bool:
        """Add a document to the queue.

        Returns True if accepted, False if dropped.
        """
        current_depth = self._queue.qsize()

        # Check warn threshold
        if current_depth >= self._warn_threshold:
            logger.warning(
                "queue_high_water",
                depth=current_depth,
                max_depth=self._max_depth,
                source_type=doc.source_type,
            )

        # Try to put (non-blocking)
        try:
            self._queue.put_nowait(doc)
            metrics.gauge("queue_depth", self._queue.qsize())
            return True
        except queue.Full:
            # DROP with structured log
            with self._lock:
                self._dropped_count += 1
            metrics.increment("queue_dropped")

            logger.warning(
                "queue_item_dropped",
                source_type=doc.source_type,
                source_path=doc.source_path[:100],
                checksum=doc.checksum[:16],
                reason="queue_full",
                depth=self._max_depth,
            )
            return False

    def get(self, timeout: float = 1.0) -> Optional[RawDocument]:
        """Get the highest-priority document from the queue."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def task_done(self) -> None:
        """Mark a queued item as processed."""
        self._queue.task_done()

    @property
    def depth(self) -> int:
        """Current queue depth."""
        return self._queue.qsize()

    @property
    def max_depth(self) -> int:
        """Maximum queue depth."""
        return self._max_depth

    @property
    def dropped_count(self) -> int:
        """Total items dropped since start."""
        with self._lock:
            return self._dropped_count

    def join(self, timeout: Optional[float] = None) -> None:
        """Block until all items are processed."""
        self._queue.join()
