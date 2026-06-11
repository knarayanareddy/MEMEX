"""
Alembic-style migration runner for MEMEX.

Tracks applied migrations in a _migrations table.
Runs pending migrations in order.
Supports dry-run mode and rollback tracking.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from ...observability.logging import get_logger

logger = get_logger("db.migrations")

_MIGRATIONS_DIR = Path(__file__).parent

# Pattern: 001_initial.sql, 002_add_retry_columns.sql, etc.
_MIGRATION_PATTERN = re.compile(r"^(\d+)_(\w+)\.sql$")


def ensure_migrations_table(conn: sqlite3.Connection) -> None:
    """Create the _migrations tracking table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            version     INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            applied_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            checksum    TEXT
        )
    """)


def get_applied_versions(conn: sqlite3.Connection) -> set[int]:
    """Get all migration versions that have been applied."""
    ensure_migrations_table(conn)
    rows = conn.execute("SELECT version FROM _migrations").fetchall()
    return {row[0] for row in rows}


def discover_migrations() -> list[tuple[int, str, Path]]:
    """Discover all migration files in order.

    Returns:
        List of (version, name, path) tuples sorted by version.
    """
    migrations = []
    for f in _MIGRATIONS_DIR.iterdir():
        if not f.is_file() or not f.name.endswith(".sql"):
            continue
        if f.name == "runner.py":
            continue
        match = _MIGRATION_PATTERN.match(f.name)
        if match:
            version = int(match.group(1))
            name = match.group(2)
            migrations.append((version, name, f))

    migrations.sort(key=lambda x: x[0])
    return migrations


def run_pending_migrations(conn: sqlite3.Connection, dry_run: bool = False) -> list[str]:
    """Run all pending migrations.

    Args:
        conn: SQLite connection.
        dry_run: If True, log what would be run without executing.

    Returns:
        List of applied migration names.
    """
    applied = get_applied_versions(conn)
    discovered = discover_migrations()

    pending = [(v, n, p) for v, n, p in discovered if v not in applied]

    if not pending:
        logger.info("migrations_up_to_date", applied=len(applied))
        return []

    applied_names = []

    for version, name, path in pending:
        import hashlib

        sql = path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode()).hexdigest()[:16]

        logger.info(
            "running_migration",
            version=version,
            name=name,
            dry_run=dry_run,
        )

        if dry_run:
            applied_names.append(f"{version}_{name} (DRY RUN)")
            continue

        try:
            conn.executescript(sql)

            # Record migration
            conn.execute(
                """INSERT INTO _migrations (version, name, applied_at, checksum)
                   VALUES (?, ?, ?, ?)""",
                (version, name, datetime.utcnow().isoformat(), checksum),
            )
            conn.commit()

            applied_names.append(f"{version}_{name}")
            logger.info("migration_applied", version=version, name=name)

        except Exception as e:
            logger.error("migration_failed", version=version, name=name, error=str(e))
            conn.rollback()
            raise RuntimeError(f"Migration {version}_{name} failed: {e}") from e

    return applied_names
