"""
Filesystem ingestor for MEMEX.

Uses watchdog to monitor configured directories for file changes.
Emits RawDocument objects for new or modified files.
"""

from __future__ import annotations

import hashlib
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent
from watchdog.observers import Observer

from ..config.settings import Priority, RawDocument, Settings, get_settings
from ..observability.logging import get_logger

if TYPE_CHECKING:
    from .queue import IngestionQueue

logger = get_logger("ingest.filesystem")

# File extensions to skip
_SKIP_EXTENSIONS = {
    ".git", ".svn", ".hg", "__pycache__", ".tox", ".venv",
    ".cache", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".node_modules", ".DS_Store", ".tmp", ".swp",
}

# Max file size to ingest (50MB)
_MAX_FILE_SIZE = 50 * 1024 * 1024


class _WatchdogHandler(FileSystemEventHandler):
    """Watchdog event handler that converts FS events to RawDocuments."""

    def __init__(self, queue: "IngestionQueue", excluded_exts: set[str]):
        self._queue = queue
        self._excluded_exts = excluded_exts
        self._seen_checksums: set[str] = set()

    def on_created(self, event: FileCreatedEvent) -> None:
        if not event.is_directory:
            self._process_file(event.src_path)

    def on_modified(self, event: FileModifiedEvent) -> None:
        if not event.is_directory:
            self._process_file(event.src_path)

    def _process_file(self, path: str) -> None:
        """Process a file change event."""
        p = Path(path)

        # Skip excluded extensions
        if any(part.startswith(".") and part in self._excluded_exts for part in p.parts):
            return
        if p.suffix in self._excluded_exts:
            return

        # Skip very large files
        try:
            size = p.stat().st_size
            if size > _MAX_FILE_SIZE:
                return
            if size == 0:
                return
        except OSError:
            return

        try:
            raw_bytes = p.read_bytes()
            checksum = hashlib.sha256(raw_bytes).hexdigest()

            # Skip if we've already seen this exact checksum
            if checksum in self._seen_checksums:
                return
            self._seen_checksums.add(checksum)

            # Limit cache size
            if len(self._seen_checksums) > 10_000:
                self._seen_checksums = set(list(self._seen_checksums)[-5_000:])

            doc = RawDocument(
                source_type="filesystem",
                source_path=str(p),
                raw_bytes=raw_bytes,
                encoding="utf-8",
                captured_at=datetime.utcnow(),
                source_metadata={
                    "filename": p.name,
                    "extension": p.suffix,
                    "size": size,
                },
                checksum=checksum,
                priority=Priority.NORMAL,
            )
            self._queue.put(doc)
        except (OSError, PermissionError) as e:
            logger.debug("file_read_error", path=str(p), error=str(e))


class FilesystemIngestor:
    """Filesystem watcher using watchdog."""

    source_type = "filesystem"

    def __init__(self, queue: "IngestionQueue", settings: Optional[Settings] = None):
        self._settings = settings or get_settings()
        self._queue = queue
        self._observer = Observer()
        self._running = False

    def start(self) -> None:
        """Start watching configured directories."""
        excluded = set(self._settings.excluded_extensions)
        handler = _WatchdogHandler(self._queue, excluded)

        for path_str in self._settings.watch_paths:
            path = Path(path_str).expanduser().resolve()
            if path.exists() and path.is_dir():
                self._observer.schedule(handler, str(path), recursive=True)
                logger.info("watching_directory", path=str(path))

        self._observer.start()
        self._running = True
        logger.info("filesystem_ingestor_started")

    def stop(self) -> None:
        """Stop the filesystem watcher."""
        self._observer.stop()
        self._observer.join(timeout=5.0)
        self._running = False
        logger.info("filesystem_ingestor_stopped")

    @property
    def poll_interval_seconds(self) -> float:
        return 0  # Event-driven, no polling
