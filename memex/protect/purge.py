"""
Purge scheduler for MEMEX.

Handles raw content TTL purging and periodic maintenance.
Purge values are loaded exclusively from Addendum B.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from ..config.settings import Settings, get_settings, load_retention
from ..db.sqlite import SQLiteDatabase
from ..observability.logging import get_logger

logger = get_logger("protect.purge")


class PurgeScheduler:
    """Scheduled purge jobs for raw content and maintenance."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        sqlite: Optional[SQLiteDatabase] = None,
    ):
        self._settings = settings or get_settings()
        self._sqlite = sqlite
        self._running = False
        self._thread: Optional[threading.Thread] = None

        retention = load_retention()
        self._purge_days = retention.get("raw_content", {}).get("purge_after_days", 7)
        self._run_interval = retention.get("purge_schedule", {}).get("run_interval_minutes", 60)

    def start(self) -> None:
        """Start the purge scheduler."""
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            name="purge-scheduler",
            daemon=True,
        )
        self._thread.start()
        logger.info("purge_scheduler_started", interval_minutes=self._run_interval)

    def stop(self) -> None:
        """Stop the purge scheduler."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("purge_scheduler_stopped")

    def run_purge(self) -> dict[str, int]:
        """Execute a purge cycle.

        Returns:
            Dict with counts of purged items.
        """
        results = {"raw_content_purged": 0}

        if self._sqlite:
            count = self._sqlite.purge_raw_content(self._purge_days)
            results["raw_content_purged"] = count

            if count > 0:
                logger.info(
                    "raw_content_purged",
                    count=count,
                    purge_after_days=self._purge_days,
                )

        return results

    def _run_loop(self) -> None:
        """Main purge loop."""
        while self._running:
            try:
                self.run_purge()
            except Exception as e:
                logger.error("purge_error", error=str(e))

            # Sleep in small increments for responsive shutdown
            sleep_seconds = self._run_interval * 60
            for _ in range(sleep_seconds):
                if not self._running:
                    break
                time.sleep(1)
