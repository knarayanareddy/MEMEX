"""INGEST pillar — Passive capture from digital sources."""

from .base import BaseIngestor
from .queue import IngestionQueue
from .filesystem import FilesystemIngestor
from .browser import BrowserIngestor
from .terminal import TerminalIngestor
from .clipboard import ClipboardIngestor

__all__ = [
    "BaseIngestor",
    "IngestionQueue",
    "FilesystemIngestor",
    "BrowserIngestor",
    "TerminalIngestor",
    "ClipboardIngestor",
]
