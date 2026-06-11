"""
Structured JSON logging for MEMEX.

All daemon logs are written as structured JSON to a rotating log file
at ~/.memex/logs/daemon.log.

Log format:
{
  "timestamp": "...",
  "level": "INFO",
  "pillar": "INGEST",
  "event": "document_ingested",
  "document_id": "abc-123",
  "duration_ms": 42,
  ...
}
"""

from __future__ import annotations

import json
import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "module": record.name,
        }

        # If the message is the event name, extract it
        if hasattr(record, "event"):
            log_entry["event"] = record.event
            log_entry["message"] = record.getMessage()
        else:
            log_entry["event"] = record.getMessage()

        # Extract all extra fields
        skip = {
            "name", "msg", "args", "created", "relativeCreated", "exc_info",
            "exc_text", "stack_info", "lineno", "funcName", "pathname",
            "filename", "module", "thread", "threadName", "process", "processName",
            "levelname", "levelno", "msecs", "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in skip and not key.startswith("_"):
                try:
                    json.dumps(value)
                    log_entry[key] = value
                except (TypeError, ValueError):
                    log_entry[key] = str(value)

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = str(record.exc_info[1])

        return json.dumps(log_entry, default=str)


class StructuredLogger:
    """Logger that supports structured event logging."""

    def __init__(self, name: str):
        self._logger = logging.getLogger(f"memex.{name}")

    def _log(self, level: int, event: str, **kwargs: Any) -> None:
        record = self._logger.makeRecord(
            name=self._logger.name,
            level=level,
            fn="",
            lno=0,
            msg=event,
            args=(),
            exc_info=None,
        )
        record.event = event
        for k, v in kwargs.items():
            setattr(record, k, v)
        self._logger.handle(record)

    def debug(self, event: str, **kwargs: Any) -> None:
        self._log(logging.DEBUG, event, **kwargs)

    def info(self, event: str, **kwargs: Any) -> None:
        self._log(logging.INFO, event, **kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        self._log(logging.WARNING, event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        self._log(logging.ERROR, event, **kwargs)

    def critical(self, event: str, **kwargs: Any) -> None:
        self._log(logging.CRITICAL, event, **kwargs)


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance."""
    return StructuredLogger(name)


def setup_logging(
    log_dir: Optional[Path] = None,
    log_level: str = "INFO",
) -> None:
    """Configure the root logger with JSON formatting and rotation."""
    if log_dir is None:
        log_dir = Path.home() / ".memex" / "logs"

    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "daemon.log"

    # Root memex logger
    root_logger = logging.getLogger("memex")
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers
    root_logger.handlers.clear()

    # File handler with rotation
    file_handler = RotatingFileHandler(
        str(log_file),
        maxBytes=50 * 1024 * 1024,  # 50MB
        backupCount=7,
    )
    file_handler.setFormatter(JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S"))
    root_logger.addHandler(file_handler)

    # Console handler (simpler format)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S"))
    root_logger.addHandler(console_handler)


class Timer:
    """Context manager for timing operations."""

    def __init__(self, logger: StructuredLogger, event: str, **kwargs: Any):
        self._logger = logger
        self._event = event
        self._kwargs = kwargs
        self._start: float = 0

    def __enter__(self) -> "Timer":
        self._start = time.monotonic()
        return self

    def __exit__(self, *args: Any) -> None:
        duration_ms = (time.monotonic() - self._start) * 1000
        self._logger.info(self._event, duration_ms=round(duration_ms, 2), **self._kwargs)
