"""
Central configuration loader for MEMEX.

Reads from:
  1. Addenda TOML files (retrieval_weights, retention, chunking, redaction, SLOs)
  2. User config.toml (~/.memex/config.toml)
  3. Environment variable overrides (MEMEX_*)
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import toml


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DEFAULT_DATA_DIR = Path.home() / ".memex"
_ADDENDA_DIR = Path(__file__).parent  # config/ package directory


def _data_dir() -> Path:
    return Path(os.environ.get("MEMEX_DATA_DIR", str(_DEFAULT_DATA_DIR)))


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Priority(Enum):
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


class ContentType(Enum):
    PDF = "pdf"
    HTML = "html"
    CODE = "code"
    EMAIL = "email"
    MARKDOWN = "markdown"
    IMAGE = "image"
    PLAIN = "plain"


class DocumentStatus(Enum):
    PENDING = "PENDING"
    PARSED = "PARSED"
    EMBEDDED = "EMBEDDED"
    GRAPHED = "GRAPHED"
    INDEXED = "INDEXED"
    FAILED = "FAILED"
    PARSE_FAILED = "PARSE_FAILED"
    OCR_EMPTY = "OCR_EMPTY"
    EMPTY = "EMPTY"
    FORGET_FAILED = "FORGET_FAILED"
    ABANDONED = "ABANDONED"


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

@dataclass
class RawDocument:
    """Canonical interface between INGEST and PARSE."""
    source_type: str
    source_path: str
    raw_bytes: bytes
    encoding: str
    captured_at: datetime
    source_metadata: dict[str, Any] = field(default_factory=dict)
    checksum: str = ""
    priority: Priority = Priority.NORMAL

    def __post_init__(self) -> None:
        if not self.checksum:
            import hashlib
            self.checksum = hashlib.sha256(self.raw_bytes).hexdigest()

    def __lt__(self, other: "RawDocument") -> bool:
        """Priority queue comparison — lower priority value = higher priority."""
        if not isinstance(other, RawDocument):
            return NotImplemented
        return self.priority.value < other.priority.value


@dataclass
class ParsedDocument:
    """Canonical interface between PARSE and INDEX."""
    document_id: str
    clean_content: str
    content_type: ContentType
    language: Optional[str] = None
    word_count: int = 0
    char_count: int = 0
    parse_metadata: dict[str, Any] = field(default_factory=dict)
    parsed_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        if not self.word_count:
            self.word_count = len(self.clean_content.split())
        if not self.char_count:
            self.char_count = len(self.clean_content)


@dataclass
class Chunk:
    """Atomic retrieval unit."""
    chunk_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str = ""
    content: str = ""
    token_count: int = 0
    chunk_index: int = 0
    total_chunks: int = 0
    start_char: int = 0
    end_char: int = 0
    chroma_id: Optional[str] = None


@dataclass
class RetrievalResult:
    """Result from hybrid retrieval."""
    chunk_id: str
    document_id: str
    content: str
    combined_score: float
    vector_score: float
    keyword_score: float
    graph_score: float
    temporal_score: float
    source_type: str
    source_path: str
    captured_at: datetime
    citation_index: int = 0


@dataclass
class ConversationTurn:
    """Single turn in a chat conversation."""
    turn_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    role: str = "user"
    content: str = ""
    sources_cited: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Addenda loaders
# ---------------------------------------------------------------------------

def _load_toml(filename: str) -> dict[str, Any]:
    """Load a TOML file from the addenda directory."""
    path = _ADDENDA_DIR / filename
    if not path.exists():
        return {}
    return toml.load(str(path))


def load_retrieval_weights() -> dict[str, Any]:
    """Addendum A — Retrieval weight constants."""
    return _load_toml("retrieval_weights.toml")


def load_retention() -> dict[str, Any]:
    """Addendum B — Retention & purge day values."""
    return _load_toml("retention.toml")


def load_chunking() -> dict[str, Any]:
    """Addendum C — Chunk token budget constants."""
    return _load_toml("chunking.toml")


def load_redaction_patterns() -> dict[str, Any]:
    """Addendum D — Secret redaction pattern registry."""
    return _load_toml("redaction_patterns.toml")


def load_slos() -> dict[str, Any]:
    """Addendum F — SLO definitions & alert thresholds."""
    return _load_toml("slos.toml")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@dataclass
class Settings:
    """Merged application settings from config.toml + addenda."""

    # Daemon
    data_dir: Path = field(default_factory=_data_dir)
    log_level: str = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = 7700

    # Ollama
    ollama_base_url: str = "http://127.0.0.1:11434"

    # Embedding
    embed_model: str = "nomic-embed-text"
    embed_model_version: str = "1.5"
    active_collection: str = "memex_vectors_v1"

    # Chat
    chat_model: str = "llama3:8b"

    # Watcher
    watch_paths: list[str] = field(default_factory=lambda: ["~/Documents", "~/Projects"])
    excluded_extensions: list[str] = field(default_factory=lambda: [".git", ".svn", ".hg"])

    # Browser
    browser_fetch_page_content: bool = False
    browser_poll_interval_seconds: int = 300

    # Terminal
    terminal_poll_interval_seconds: int = 120

    # Clipboard
    clipboard_poll_interval_seconds: int = 30

    # Worker pool
    worker_count: int = 4

    # Graph
    extract_relations: bool = False

    # Addenda (lazy-loaded)
    _retrieval_weights: Optional[dict] = None
    _retention: Optional[dict] = None
    _chunking: Optional[dict] = None
    _redaction: Optional[dict] = None
    _slos: Optional[dict] = None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "data" / "memex.db"

    @property
    def chroma_path(self) -> Path:
        return self.data_dir / "data" / "chroma"

    @property
    def kuzu_path(self) -> Path:
        return self.data_dir / "data" / "kuzu"

    @property
    def log_path(self) -> Path:
        return self.data_dir / "logs"

    @property
    def retrieval_weights(self) -> dict[str, Any]:
        if self._retrieval_weights is None:
            self._retrieval_weights = load_retrieval_weights()
        return self._retrieval_weights

    @property
    def retention(self) -> dict[str, Any]:
        if self._retention is None:
            self._retention = load_retention()
        return self._retention

    @property
    def chunking(self) -> dict[str, Any]:
        if self._chunking is None:
            self._chunking = load_chunking()
        return self._chunking

    @property
    def redaction(self) -> dict[str, Any]:
        if self._redaction is None:
            self._redaction = load_redaction_patterns()
        return self._redaction

    @property
    def slos(self) -> dict[str, Any]:
        if self._slos is None:
            self._slos = load_slos()
        return self._slos

    def ensure_directories(self) -> None:
        """Create all required directories."""
        for p in [self.db_path.parent, self.chroma_path, self.kuzu_path, self.log_path]:
            p.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_config(cls) -> "Settings":
        """Load settings from config.toml with environment overrides."""
        config_path = _data_dir() / "config.toml"
        user_config: dict[str, Any] = {}
        if config_path.exists():
            user_config = toml.load(str(config_path))

        daemon_cfg = user_config.get("daemon", {})
        embed_cfg = user_config.get("embedding", {})
        chat_cfg = user_config.get("chat", {})
        watcher_cfg = user_config.get("watcher", {})
        browser_cfg = user_config.get("browser", {})
        terminal_cfg = user_config.get("terminal", {})
        clipboard_cfg = user_config.get("clipboard", {})
        worker_cfg = user_config.get("workers", {})
        graph_cfg = user_config.get("graph", {})

        return cls(
            data_dir=Path(os.environ.get("MEMEX_DATA_DIR", daemon_cfg.get("data_dir", str(_data_dir())))),
            log_level=os.environ.get("MEMEX_LOG_LEVEL", daemon_cfg.get("log_level", "INFO")),
            api_host=daemon_cfg.get("api_host", "127.0.0.1"),
            api_port=int(os.environ.get("MEMEX_API_PORT", daemon_cfg.get("api_port", 7700))),
            ollama_base_url=os.environ.get("MEMEX_OLLAMA_URL", daemon_cfg.get("ollama_base_url", "http://127.0.0.1:11434")),
            embed_model=embed_cfg.get("model", "nomic-embed-text"),
            embed_model_version=embed_cfg.get("model_version", "1.5"),
            active_collection=embed_cfg.get("active_collection", "memex_vectors_v1"),
            chat_model=chat_cfg.get("model", "llama3:8b"),
            watch_paths=watcher_cfg.get("paths", ["~/Documents", "~/Projects"]),
            excluded_extensions=watcher_cfg.get("excluded_extensions", [".git", ".svn", ".hg"]),
            browser_fetch_page_content=browser_cfg.get("fetch_page_content", False),
            browser_poll_interval_seconds=browser_cfg.get("poll_interval_seconds", 300),
            terminal_poll_interval_seconds=terminal_cfg.get("poll_interval_seconds", 120),
            clipboard_poll_interval_seconds=clipboard_cfg.get("poll_interval_seconds", 30),
            worker_count=worker_cfg.get("count", 4),
            extract_relations=graph_cfg.get("extract_relations", False),
        )


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the singleton Settings instance."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings.from_config()
    return _settings_instance


def reset_settings() -> None:
    """Reset the singleton — useful for testing."""
    global _settings_instance
    _settings_instance = None
