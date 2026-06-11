"""
Browser history ingestor for MEMEX.

Reads the browser's local SQLite history DB to get URL, title, and visit time.
Optionally fetches page content (disabled by default).
Respects excluded domains from Addendum D.
"""

from __future__ import annotations

import hashlib
import os
import platform
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from ..config.settings import Priority, RawDocument, Settings, get_settings
from ..config.settings import load_redaction_patterns
from ..observability.logging import get_logger

if TYPE_CHECKING:
    from .queue import IngestionQueue

logger = get_logger("ingest.browser")


def _chrome_history_path() -> Optional[Path]:
    """Find the Chrome history SQLite database."""
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "Default"
    elif system == "Linux":
        base = Path.home() / ".config" / "google-chrome" / "Default"
    else:
        return None

    history_path = base / "History"
    return history_path if history_path.exists() else None


def _firefox_history_path() -> Optional[Path]:
    """Find the Firefox places.sqlite database."""
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "Firefox" / "Profiles"
    elif system == "Linux":
        base = Path.home() / ".mozilla" / "firefox"
    else:
        return None

    if not base.exists():
        return None

    for profile_dir in base.iterdir():
        places = profile_dir / "places.sqlite"
        if places.exists():
            return places
    return None


def _load_excluded_domains() -> set[str]:
    """Load excluded domains from Addendum D."""
    patterns = load_redaction_patterns()
    return set(patterns.get("browser_excluded_domains", {}).get("domains", []))


def _is_excluded_domain(url: str, excluded_domains: set[str]) -> bool:
    """Check if a URL matches any excluded domain pattern."""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""

        for pattern in excluded_domains:
            if pattern.startswith("*."):
                if hostname.endswith(pattern[2:]) or hostname == pattern[2:]:
                    return True
            elif pattern.endswith(".*"):
                if hostname.startswith(pattern[:-1]):
                    return True
            else:
                if hostname == pattern or hostname.endswith(f".{pattern}"):
                    return True
        return False
    except Exception:
        return False


class BrowserIngestor:
    """Browser history ingestor — reads Chrome/Firefox SQLite history."""

    source_type = "browser"

    def __init__(self, queue: "IngestionQueue", settings: Optional[Settings] = None):
        self._settings = settings or get_settings()
        self._queue = queue
        self._running = False
        self._thread: Optional[object] = None
        self._last_visit_id: int = 0
        self._excluded_domains = _load_excluded_domains()

    def poll(self) -> list[RawDocument]:
        """Poll browser history for new visits."""
        documents = []

        for browser, path_finder in [("chrome", _chrome_history_path), ("firefox", _firefox_history_path)]:
            path = path_finder()
            if not path:
                continue
            try:
                docs = self._read_history(browser, path)
                documents.extend(docs)
            except Exception as e:
                logger.error("browser_history_read_error", browser=browser, error=str(e))

        return documents

    def _read_history(self, browser: str, db_path: Path) -> list[RawDocument]:
        """Read new entries from a browser history DB."""
        documents = []

        # Make a temporary copy to avoid locking issues
        import shutil
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            shutil.copy2(str(db_path), str(tmp_path))

            conn = sqlite3.connect(str(tmp_path))
            conn.row_factory = sqlite3.Row

            if browser == "chrome":
                rows = conn.execute(
                    """SELECT v.id, u.url, u.title, v.visit_time / 1000000 as visit_epoch
                       FROM visits v JOIN urls u ON v.url = u.id
                       WHERE v.id > ? AND u.url LIKE 'http%%'
                       ORDER BY v.id LIMIT 200""",
                    (self._last_visit_id,),
                ).fetchall()
            else:  # firefox
                rows = conn.execute(
                    """SELECT p.id, p.url, p.title, p.last_visit_date / 1000000 as visit_epoch
                       FROM moz_places p
                       WHERE p.id > ? AND p.url LIKE 'http%%'
                       ORDER BY p.id LIMIT 200""",
                    (self._last_visit_id,),
                ).fetchall()

            for row in rows:
                visit_id = row[0]
                url = row[1]
                title = row[2] or ""

                self._last_visit_id = max(self._last_visit_id, visit_id)

                # Skip excluded domains
                if _is_excluded_domain(url, self._excluded_domains):
                    continue

                content = f"{title}\n{url}"
                raw_bytes = content.encode("utf-8")
                checksum = hashlib.sha256(raw_bytes).hexdigest()

                doc = RawDocument(
                    source_type="browser",
                    source_path=url,
                    raw_bytes=raw_bytes,
                    encoding="utf-8",
                    captured_at=datetime.utcnow(),
                    source_metadata={
                        "url": url,
                        "title": title,
                        "browser": browser,
                    },
                    checksum=checksum,
                    priority=Priority.NORMAL,
                )
                documents.append(doc)

            conn.close()
        finally:
            tmp_path.unlink(missing_ok=True)

        return documents

    def fetch_page_content(self, url: str) -> Optional[str]:
        """Optionally fetch live page content (default: disabled)."""
        if not self._settings.browser_fetch_page_content:
            return None

        if _is_excluded_domain(url, self._excluded_domains):
            return None

        try:
            import httpx
            with httpx.Client(timeout=10.0, follow_redirects=True, max_redirects=2) as client:
                response = client.get(
                    url,
                    headers={"User-Agent": "MEMEX/2.0 (local-only)"},
                )

                if response.status_code >= 400:
                    return None

                # Detect login redirects
                if '<form' in response.text.lower() and 'password' in response.text.lower():
                    return None

                return response.text
        except Exception as e:
            logger.debug("page_fetch_error", url=url[:80], error=str(e))
            return None

    def start(self) -> None:
        """Start the browser poller."""
        import threading
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="ingest-browser"
        )
        self._thread.start()
        logger.info("browser_ingestor_started")

    def stop(self) -> None:
        """Stop the browser poller."""
        self._running = False
        logger.info("browser_ingestor_stopped")

    def _run_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                docs = self.poll()
                for doc in docs:
                    self._queue.put(doc)
            except Exception as e:
                logger.error("browser_poll_error", error=str(e))
            time.sleep(self._settings.browser_poll_interval_seconds)

    @property
    def poll_interval_seconds(self) -> float:
        return float(self._settings.browser_poll_interval_seconds)
