"""
Shared test fixtures for MEMEX test suite.
"""

import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Generator

import pytest

# Force test data directories
os.environ["MEMEX_DATA_DIR"] = tempfile.mkdtemp(prefix="memex_test_")
os.environ["MEMEX_OLLAMA_URL"] = "http://127.0.0.1:11434"


@pytest.fixture
def temp_dir(tmp_path) -> Path:
    """Create a temporary directory for test data."""
    return tmp_path


@pytest.fixture
def test_db(tmp_path) -> sqlite3.Connection:
    """Create a test SQLite database with schema."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Run initial migration
    migration_path = Path(__file__).parent.parent / "memex" / "db" / "migrations" / "001_initial.sql"
    if migration_path.exists():
        conn.executescript(migration_path.read_text())

    return conn


@pytest.fixture
def sqlite_db(tmp_path):
    """Create a SQLiteDatabase instance with test path."""
    from memex.config.settings import Settings

    settings = Settings(data_dir=tmp_path)
    settings.ensure_directories()

    from memex.db.sqlite import SQLiteDatabase
    db = SQLiteDatabase(db_path=tmp_path / "data" / "test.db", settings=settings)
    db.run_migrations()
    return db


@pytest.fixture
def redactor():
    """Create a Redactor instance."""
    from memex.protect.redactor import Redactor
    return Redactor()


@pytest.fixture
def chunker():
    """Create a SmartChunker instance."""
    from memex.index.chunker import SmartChunker
    return SmartChunker()


@pytest.fixture
def parser_dispatcher():
    """Create a ParserDispatcher instance."""
    from memex.parse.dispatcher import ParserDispatcher
    return ParserDispatcher()


@pytest.fixture
def sample_documents():
    """Sample test documents."""
    return {
        "plain": b"Hello, this is a test document about Python programming.",
        "markdown": b"# Test Document\n\nThis is a **markdown** file with some content.\n\n## Section 2\n\nMore content here.",
        "code": b'def hello_world():\n    """Say hello to the world."""\n    print("Hello, World!")\n\nclass Greeter:\n    pass\n',
        "html": b"<html><head><title>Test Page</title></head><body><p>Content here</p></body></html>",
    }
