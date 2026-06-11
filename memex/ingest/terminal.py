"""
Terminal history ingestor for MEMEX.

Polls ~/.zsh_history and ~/.bash_history for new commands.
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from ..config.settings import Priority, RawDocument, Settings, get_settings
from ..observability.logging import get_logger

if TYPE_CHECKING:
    from .queue import IngestionQueue

logger = get_logger("ingest.terminal")

_HISTORY_FILES = [
    Path.home() / ".bash_history",
    Path.home() / ".zsh_history",
]


class TerminalIngestor:
    """Terminal history poller — reads shell history files."""

    source_type = "terminal"

    def __init__(self, queue: "IngestionQueue", settings: Optional[Settings] = None):
        self._settings = settings or get_settings()
        self._queue = queue
        self._running = False
        self._thread: Optional[object] = None
        self._last_positions: dict[Path, int] = {}
        self._seen_checksums: set[str] = set()

    def poll(self) -> list[RawDocument]:
        """Poll history files for new commands."""
        documents = []

        for history_path in _HISTORY_FILES:
            if not history_path.exists():
                continue
            try:
                docs = self._read_new_commands(history_path)
                documents.extend(docs)
            except Exception as e:
                logger.error("terminal_history_error", path=str(history_path), error=str(e))

        return documents

    def _read_new_commands(self, path: Path) -> list[RawDocument]:
        """Read new commands from a history file."""
        documents = []

        try:
            file_size = path.stat().st_size
            last_pos = self._last_positions.get(path, 0)

            if file_size < last_pos:
                # File was truncated (history rotation)
                last_pos = 0

            with open(path, "rb") as f:
                f.seek(last_pos)
                new_bytes = f.read()
                new_pos = f.tell()

            self._last_positions[path] = new_pos

            if not new_bytes:
                return []

            # Parse commands (handle both bash and zsh formats)
            text = new_bytes.decode("utf-8", errors="replace")
            commands = self._parse_commands(text)

            for cmd in commands:
                cmd = cmd.strip()
                if not cmd or len(cmd) < 3:
                    continue

                raw_bytes = cmd.encode("utf-8")
                checksum = hashlib.sha256(raw_bytes).hexdigest()

                if checksum in self._seen_checksums:
                    continue
                self._seen_checksums.add(checksum)

                if len(self._seen_checksums) > 50_000:
                    self._seen_checksums = set(list(self._seen_checksums)[-25_000:])

                doc = RawDocument(
                    source_type="terminal",
                    source_path=str(path),
                    raw_bytes=raw_bytes,
                    encoding="utf-8",
                    captured_at=datetime.utcnow(),
                    source_metadata={
                        "shell": "bash" if ".bash" in path.name else "zsh",
                        "command_preview": cmd[:200],
                    },
                    checksum=checksum,
                    priority=Priority.HIGH,
                )
                documents.append(doc)

        except (OSError, PermissionError) as e:
            logger.debug("terminal_file_error", path=str(path), error=str(e))

        return documents

    @staticmethod
    def _parse_commands(text: str) -> list[str]:
        """Parse commands from history text, handling zsh timestamp format."""
        commands: list[str] = []
        current_cmd: list[str] = []

        for line in text.split("\n"):
            # Skip zsh timestamp lines: ": 1234567890:0;cmd"
            if line.startswith(": ") and ";" in line:
                parts = line.split(";", 1)
                if len(parts) == 2:
                    line = parts[1]

            if line.strip():
                current_cmd.append(line)
            else:
                if current_cmd:
                    commands.append("\n".join(current_cmd))
                    current_cmd = []

        if current_cmd:
            commands.append("\n".join(current_cmd))

        return commands

    def start(self) -> None:
        """Start the terminal poller."""
        import threading
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="ingest-terminal"
        )
        self._thread.start()
        logger.info("terminal_ingestor_started")

    def stop(self) -> None:
        """Stop the terminal poller."""
        self._running = False
        logger.info("terminal_ingestor_stopped")

    def _run_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                docs = self.poll()
                for doc in docs:
                    self._queue.put(doc)
            except Exception as e:
                logger.error("terminal_poll_error", error=str(e))
            time.sleep(self._settings.terminal_poll_interval_seconds)

    @property
    def poll_interval_seconds(self) -> float:
        return float(self._settings.terminal_poll_interval_seconds)
