"""
Clipboard ingestor for MEMEX.

Polls the system clipboard for new content every 30 seconds (configurable).
Highest-priority source — clipboard captures are marked CRITICAL.
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from ..config.settings import Priority, RawDocument, Settings, get_settings
from ..observability.logging import get_logger

if TYPE_CHECKING:
    from .queue import IngestionQueue

logger = get_logger("ingest.clipboard")


class ClipboardIngestor:
    """Clipboard poller — captures new clipboard content."""

    source_type = "clipboard"

    def __init__(self, queue: "IngestionQueue", settings: Optional[Settings] = None):
        self._settings = settings or get_settings()
        self._queue = queue
        self._running = False
        self._thread: Optional[object] = None
        self._last_checksum: str = ""

    def poll(self) -> list[RawDocument]:
        """Poll the clipboard for new content."""
        documents = []

        try:
            import pyperclip
            content = pyperclip.paste()

            if not content or not content.strip():
                return []

            raw_bytes = content.encode("utf-8")
            checksum = hashlib.sha256(raw_bytes).hexdigest()

            if checksum == self._last_checksum:
                return []

            self._last_checksum = checksum

            doc = RawDocument(
                source_type="clipboard",
                source_path="clipboard://system",
                raw_bytes=raw_bytes,
                encoding="utf-8",
                captured_at=datetime.utcnow(),
                source_metadata={
                    "length": len(content),
                    "preview": content[:200],
                },
                checksum=checksum,
                priority=Priority.CRITICAL,
            )
            documents.append(doc)

        except Exception as e:
            logger.debug("clipboard_poll_error", error=str(e))

        return documents

    def start(self) -> None:
        """Start the clipboard poller."""
        import threading
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="ingest-clipboard"
        )
        self._thread.start()
        logger.info("clipboard_ingestor_started")

    def stop(self) -> None:
        """Stop the clipboard poller."""
        self._running = False
        logger.info("clipboard_ingestor_stopped")

    def _run_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                docs = self.poll()
                for doc in docs:
                    self._queue.put(doc)
                    logger.info(
                        "clipboard_captured",
                        length=len(doc.raw_bytes),
                    )
            except Exception as e:
                logger.error("clipboard_poll_error", error=str(e))
            time.sleep(self._settings.clipboard_poll_interval_seconds)

    @property
    def poll_interval_seconds(self) -> float:
        return float(self._settings.clipboard_poll_interval_seconds)
