"""
SQLite database management for MEMEX.

Handles:
- Connection management with WAL mode
- Schema migrations
- CRUD operations for documents, chunks, entities, conversations
- FTS5 queries
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Optional

from ..config.settings import DocumentStatus, Settings, get_settings
from ..observability.logging import get_logger

logger = get_logger(__name__)

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class SQLiteDatabase:
    """Thread-safe SQLite database wrapper with WAL mode.

    FIX: Uses a connection pool (queue of connections) instead of
    creating a new connection for every operation. This avoids the
    overhead of PRAGMA setup on each call and provides better
    concurrent read performance under WAL mode.
    """

    _POOL_SIZE = 4  # Max cached connections

    def __init__(self, db_path: Optional[Path] = None, settings: Optional[Settings] = None):
        self._settings = settings or get_settings()
        self._db_path = db_path or self._settings.db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._pool: list[sqlite3.Connection] = []
        self._pool_lock = __import__("threading").Lock()

    def connect(self) -> sqlite3.Connection:
        """Create a new connection with optimal settings."""
        conn = sqlite3.connect(
            str(self._db_path),
            timeout=10.0,
            check_same_thread=False,
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        conn.row_factory = sqlite3.Row
        return conn

    def _acquire(self) -> sqlite3.Connection:
        """Acquire a connection from the pool (or create one)."""
        import threading
        with self._pool_lock:
            if self._pool:
                return self._pool.pop()
        return self.connect()

    def _release(self, conn: sqlite3.Connection) -> None:
        """Return a connection to the pool."""
        import threading
        with self._pool_lock:
            if len(self._pool) < self._POOL_SIZE:
                self._pool.append(conn)
            else:
                conn.close()

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for pooled database connections."""
        conn = self._acquire()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._release(conn)

    def run_migrations(self) -> None:
        """Execute all pending migrations using the Alembic-style runner."""
        from .migrations.runner import run_pending_migrations, discover_migrations

        # Ensure the initial migration exists
        migrations = discover_migrations()
        if not migrations:
            raise FileNotFoundError(f"No migration files found in {_MIGRATIONS_DIR}")

        with self.connection() as conn:
            applied = run_pending_migrations(conn)
            if applied:
                for name in applied:
                    logger.info("migration_applied", name=name)
            else:
                logger.info("database_migrations_up_to_date")

    # ------------------------------------------------------------------
    # Document operations
    # ------------------------------------------------------------------

    def insert_document(
        self,
        source_type: str,
        source_path: str,
        raw_content: bytes,
        checksum: str,
        source_metadata: Optional[dict] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Optional[str]:
        """Insert a new document. Returns document_id or None if duplicate."""
        doc_id = str(uuid.uuid4())

        def _insert(c: sqlite3.Connection) -> Optional[str]:
            try:
                c.execute(
                    """INSERT INTO documents
                       (id, source_type, source_path, raw_content, checksum, status,
                        captured_at, source_metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        doc_id,
                        source_type,
                        source_path,
                        raw_content,
                        checksum,
                        DocumentStatus.PENDING.value,
                        datetime.utcnow().isoformat(),
                        json.dumps(source_metadata or {}),
                    ),
                )
                return doc_id
            except sqlite3.IntegrityError:
                logger.debug("document_deduped", checksum=checksum[:16])
                return None

        if conn:
            return _insert(conn)
        with self.connection() as c:
            return _insert(c)

    def get_document_by_checksum(self, checksum: str, conn: Optional[sqlite3.Connection] = None) -> Optional[dict]:
        """Look up a document by its SHA-256 checksum."""
        def _query(c: sqlite3.Connection) -> Optional[dict]:
            row = c.execute(
                "SELECT * FROM documents WHERE checksum = ?", (checksum,)
            ).fetchone()
            return dict(row) if row else None

        if conn:
            return _query(conn)
        with self.connection() as c:
            return _query(c)

    def get_document(self, doc_id: str) -> Optional[dict]:
        """Get a single document by ID."""
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
            return dict(row) if row else None

    def update_document_status(
        self,
        doc_id: str,
        status: DocumentStatus,
        error: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        """Update document processing status."""
        def _update(c: sqlite3.Connection) -> None:
            if error:
                c.execute(
                    "UPDATE documents SET status = ?, last_error = ? WHERE id = ?",
                    (status.value, error, doc_id),
                )
            else:
                c.execute(
                    "UPDATE documents SET status = ? WHERE id = ?",
                    (status.value, doc_id),
                )

        if conn:
            _update(conn)
        else:
            with self.connection() as c:
                _update(c)

    def update_document_parsed(
        self,
        doc_id: str,
        clean_content: str,
        content_type: str,
        word_count: int,
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        """Update document with parsed content."""
        def _update(c: sqlite3.Connection) -> None:
            c.execute(
                """UPDATE documents
                   SET clean_content = ?, content_type = ?, word_count = ?,
                       status = ?, parsed_at = ?
                   WHERE id = ?""",
                (
                    clean_content,
                    content_type,
                    word_count,
                    DocumentStatus.PARSED.value,
                    datetime.utcnow().isoformat(),
                    doc_id,
                ),
            )

        if conn:
            _update(conn)
        else:
            with self.connection() as c:
                _update(c)

    def update_document_embedded(self, doc_id: str, conn: Optional[sqlite3.Connection] = None) -> None:
        """Mark document as fully embedded."""
        def _update(c: sqlite3.Connection) -> None:
            c.execute(
                """UPDATE documents SET is_embedded = 1, embedded_at = ?, status = ?
                   WHERE id = ?""",
                (datetime.utcnow().isoformat(), DocumentStatus.EMBEDDED.value, doc_id),
            )

        if conn:
            _update(conn)
        else:
            with self.connection() as c:
                _update(c)

    def update_document_graphed(self, doc_id: str, conn: Optional[sqlite3.Connection] = None) -> None:
        """Mark document as graphed."""
        def _update(c: sqlite3.Connection) -> None:
            c.execute(
                """UPDATE documents SET is_graphed = 1, graphed_at = ? WHERE id = ?""",
                (datetime.utcnow().isoformat(), doc_id),
            )

        if conn:
            _update(conn)
        else:
            with self.connection() as c:
                _update(c)

    def increment_retry(self, doc_id: str, error: str, max_retry: int = 5) -> None:
        """Increment retry count; abandon if over max."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT retry_count FROM documents WHERE id = ?", (doc_id,)
            ).fetchone()
            if not row:
                return
            new_count = row["retry_count"] + 1
            if new_count >= max_retry:
                conn.execute(
                    "UPDATE documents SET retry_count = ?, last_error = ?, status = ? WHERE id = ?",
                    (new_count, error, DocumentStatus.ABANDONED.value, doc_id),
                )
            else:
                conn.execute(
                    "UPDATE documents SET retry_count = ?, last_error = ?, status = ? WHERE id = ?",
                    (new_count, error, DocumentStatus.FAILED.value, doc_id),
                )

    def list_documents(
        self,
        source_type: Optional[str] = None,
        status: Optional[str] = None,
        after: Optional[str] = None,
        before: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List documents with optional filters."""
        with self.connection() as conn:
            query = "SELECT * FROM documents WHERE 1=1"
            params: list[Any] = []
            if source_type:
                query += " AND source_type = ?"
                params.append(source_type)
            if status:
                query += " AND status = ?"
                params.append(status)
            if after:
                query += " AND captured_at >= ?"
                params.append(after)
            if before:
                query += " AND captured_at <= ?"
                params.append(before)
            query += " ORDER BY captured_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def count_documents_by_source(self) -> dict[str, int]:
        """Count documents grouped by source_type."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT source_type, COUNT(*) as cnt FROM documents GROUP BY source_type"
            ).fetchall()
            return {r["source_type"]: r["cnt"] for r in rows}

    def purge_raw_content(self, purge_after_days: int) -> int:
        """Null raw_content for documents older than purge_after_days."""
        with self.connection() as conn:
            cursor = conn.execute(
                """UPDATE documents
                   SET raw_content = NULL, raw_purged_at = CURRENT_TIMESTAMP
                   WHERE raw_content IS NOT NULL
                     AND captured_at < datetime('now', '-' || ? || ' days')""",
                (purge_after_days,),
            )
            count = cursor.rowcount
            if count > 0:
                logger.info("raw_content_purged", count=count)
            return count

    def delete_document(self, doc_id: str, conn: Optional[sqlite3.Connection] = None) -> bool:
        """Delete a document and all dependent records."""
        def _delete(c: sqlite3.Connection) -> bool:
            cursor = c.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            return cursor.rowcount > 0

        if conn:
            return _delete(conn)
        with self.connection() as c:
            return _delete(c)

    # ------------------------------------------------------------------
    # Chunk operations
    # ------------------------------------------------------------------

    def insert_chunk(
        self,
        document_id: str,
        content: str,
        token_count: int,
        chunk_index: int,
        total_chunks: int,
        start_char: int,
        end_char: int,
        conn: Optional[sqlite3.Connection] = None,
    ) -> str:
        """Insert a chunk record."""
        chunk_id = str(uuid.uuid4())

        def _insert(c: sqlite3.Connection) -> str:
            c.execute(
                """INSERT INTO chunks
                   (id, document_id, content, token_count, chunk_index,
                    total_chunks, start_char, end_char)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (chunk_id, document_id, content, token_count, chunk_index,
                 total_chunks, start_char, end_char),
            )
            return chunk_id

        if conn:
            return _insert(conn)
        with self.connection() as c:
            return _insert(c)

    def get_chunks_for_document(self, doc_id: str) -> list[dict]:
        """Get all chunks for a document."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM chunks WHERE document_id = ? ORDER BY chunk_index",
                (doc_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def update_chunk_chroma_id(self, chunk_id: str, chroma_id: str, conn: Optional[sqlite3.Connection] = None) -> None:
        """Update chunk with Chroma vector ID."""
        def _update(c: sqlite3.Connection) -> None:
            c.execute(
                "UPDATE chunks SET chroma_id = ?, embedded_at = ? WHERE id = ?",
                (chroma_id, datetime.utcnow().isoformat(), chunk_id),
            )

        if conn:
            _update(conn)
        else:
            with self.connection() as c:
                _update(c)

    def delete_chunks_for_document(self, doc_id: str, conn: Optional[sqlite3.Connection] = None) -> int:
        """Delete all chunks for a document."""
        def _delete(c: sqlite3.Connection) -> int:
            cursor = c.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
            return cursor.rowcount

        if conn:
            return _delete(conn)
        with self.connection() as c:
            return _delete(c)

    def get_chunk_by_id(self, chunk_id: str) -> Optional[dict]:
        """Get a single chunk by ID."""
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM chunks WHERE id = ?", (chunk_id,)).fetchone()
            return dict(row) if row else None

    def count_chunks(self) -> int:
        """Total chunk count."""
        with self.connection() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM chunks").fetchone()
            return row["cnt"]

    # ------------------------------------------------------------------
    # Entity operations
    # ------------------------------------------------------------------

    def upsert_entity(
        self,
        canonical_name: str,
        entity_type: str,
        conn: Optional[sqlite3.Connection] = None,
    ) -> str:
        """Insert or update an entity. Returns entity_id."""
        def _upsert(c: sqlite3.Connection) -> str:
            existing = c.execute(
                "SELECT id, mention_count FROM entities WHERE canonical_name = ? AND entity_type = ?",
                (canonical_name, entity_type),
            ).fetchone()

            now = datetime.utcnow().isoformat()
            if existing:
                entity_id = existing["id"]
                c.execute(
                    "UPDATE entities SET last_seen = ?, mention_count = ? WHERE id = ?",
                    (now, existing["mention_count"] + 1, entity_id),
                )
                return entity_id
            else:
                entity_id = str(uuid.uuid4())
                c.execute(
                    """INSERT INTO entities (id, canonical_name, entity_type, first_seen, last_seen, mention_count)
                       VALUES (?, ?, ?, ?, ?, 1)""",
                    (entity_id, canonical_name, entity_type, now, now),
                )
                return entity_id

        if conn:
            return _upsert(conn)
        with self.connection() as c:
            return _upsert(c)

    def insert_entity_mention(
        self,
        entity_id: str,
        document_id: str,
        chunk_id: str,
        mention_text: str,
        start_char: int,
        confidence: float,
        conn: Optional[sqlite3.Connection] = None,
    ) -> str:
        """Record an entity mention in a document."""
        mention_id = str(uuid.uuid4())

        def _insert(c: sqlite3.Connection) -> str:
            c.execute(
                """INSERT INTO entity_mentions
                   (id, entity_id, document_id, chunk_id, mention_text, start_char, confidence, mentioned_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (mention_id, entity_id, document_id, chunk_id, mention_text,
                 start_char, confidence, datetime.utcnow().isoformat()),
            )
            return mention_id

        if conn:
            return _insert(conn)
        with self.connection() as c:
            return _insert(c)

    def insert_relation(
        self,
        subject_id: str,
        predicate: str,
        object_id: str,
        document_id: str,
        chunk_id: str,
        confidence: float,
        evidence: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> str:
        """Insert a relation between entities."""
        rel_id = str(uuid.uuid4())

        def _insert(c: sqlite3.Connection) -> str:
            c.execute(
                """INSERT INTO relations
                   (id, subject_id, predicate, object_id, document_id, chunk_id,
                    confidence, evidence, extracted_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (rel_id, subject_id, predicate, object_id, document_id, chunk_id,
                 confidence, evidence, datetime.utcnow().isoformat()),
            )
            return rel_id

        if conn:
            return _insert(conn)
        with self.connection() as c:
            return _insert(c)

    def delete_entity_mentions_for_document(self, doc_id: str, conn: Optional[sqlite3.Connection] = None) -> int:
        """Delete all entity mentions for a document."""
        def _delete(c: sqlite3.Connection) -> int:
            cursor = c.execute("DELETE FROM entity_mentions WHERE document_id = ?", (doc_id,))
            return cursor.rowcount

        if conn:
            return _delete(conn)
        with self.connection() as c:
            return _delete(c)

    def delete_relations_for_document(self, doc_id: str, conn: Optional[sqlite3.Connection] = None) -> int:
        """Delete all relations for a document."""
        def _delete(c: sqlite3.Connection) -> int:
            cursor = c.execute("DELETE FROM relations WHERE document_id = ?", (doc_id,))
            return cursor.rowcount

        if conn:
            return _delete(conn)
        with self.connection() as c:
            return _delete(c)

    def cleanup_orphan_entities(self, conn: Optional[sqlite3.Connection] = None) -> int:
        """Delete entities with no remaining mentions."""
        def _cleanup(c: sqlite3.Connection) -> int:
            cursor = c.execute(
                "DELETE FROM entities WHERE id NOT IN (SELECT entity_id FROM entity_mentions)"
            )
            return cursor.rowcount

        if conn:
            return _cleanup(conn)
        with self.connection() as c:
            return _cleanup(c)

    def count_entities(self) -> int:
        with self.connection() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM entities").fetchone()
            return row["cnt"]

    def count_relations(self) -> int:
        with self.connection() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM relations").fetchone()
            return row["cnt"]

    def search_entities(self, query: str, entity_type: Optional[str] = None, limit: int = 20) -> list[dict]:
        """Search entities by name."""
        with self.connection() as conn:
            sql = "SELECT * FROM entities WHERE canonical_name LIKE ?"
            params: list[Any] = [f"%{query}%"]
            if entity_type:
                sql += " AND entity_type = ?"
                params.append(entity_type)
            sql += " LIMIT ?"
            params.append(limit)
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    # ------------------------------------------------------------------
    # Conversation operations
    # ------------------------------------------------------------------

    def create_conversation(self, title: Optional[str] = None) -> str:
        """Create a new conversation session."""
        session_id = str(uuid.uuid4())
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO conversations (id, created_at, last_active, title) VALUES (?, ?, ?, ?)",
                (session_id, datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), title),
            )
        return session_id

    def add_conversation_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        sources_cited: Optional[list[str]] = None,
    ) -> str:
        """Add a turn to a conversation."""
        turn_id = str(uuid.uuid4())
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO conversation_turns (id, session_id, role, content, sources_cited, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (turn_id, session_id, role, content,
                 json.dumps(sources_cited or []), datetime.utcnow().isoformat()),
            )
            conn.execute(
                "UPDATE conversations SET last_active = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), session_id),
            )
        return turn_id

    def get_conversation_history(self, session_id: str, limit: int = 6) -> list[dict]:
        """Get recent conversation turns."""
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT * FROM conversation_turns
                   WHERE session_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (session_id, limit),
            ).fetchall()
            return list(reversed([dict(r) for r in rows]))

    def list_conversations(self, limit: int = 20) -> list[dict]:
        """List all conversation sessions."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM conversations ORDER BY last_active DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_conversation(self, session_id: str) -> bool:
        """Delete a conversation and all its turns."""
        with self.connection() as conn:
            cursor = conn.execute("DELETE FROM conversations WHERE id = ?", (session_id,))
            return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Forget log operations
    # ------------------------------------------------------------------

    def insert_forget_log(
        self,
        document_id: str,
        source_path: Optional[str],
        source_type: Optional[str],
        chroma_verified: bool,
        kuzu_verified: bool,
        sqlite_verified: bool,
    ) -> str:
        """Log a forget operation."""
        log_id = str(uuid.uuid4())
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO forget_log
                   (id, document_id, source_path, source_type, chroma_verified, kuzu_verified, sqlite_verified)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (log_id, document_id, source_path, source_type,
                 int(chroma_verified), int(kuzu_verified), int(sqlite_verified)),
            )
        return log_id

    # ------------------------------------------------------------------
    # Embed model registry
    # ------------------------------------------------------------------

    def register_embed_model(
        self,
        model_name: str,
        model_version: str,
        collection_name: str,
    ) -> str:
        """Register a new embedding model."""
        model_id = str(uuid.uuid4())
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO embed_model_registry
                   (id, model_name, model_version, collection_name)
                   VALUES (?, ?, ?, ?)""",
                (model_id, model_name, model_version, collection_name),
            )
        return model_id

    def get_active_model(self) -> Optional[dict]:
        """Get the currently active embedding model."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM embed_model_registry WHERE is_active = 1"
            ).fetchone()
            return dict(row) if row else None

    def set_active_model(self, model_id: str) -> None:
        """Set a model as active; deactivate all others."""
        with self.connection() as conn:
            conn.execute("UPDATE embed_model_registry SET is_active = 0")
            conn.execute("UPDATE embed_model_registry SET is_active = 1 WHERE id = ?", (model_id,))

    def list_embed_models(self) -> list[dict]:
        """List all registered embedding models."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM embed_model_registry ORDER BY registered_at"
            ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # FTS5 search
    # ------------------------------------------------------------------

    @staticmethod
    def _escape_fts5_query(query: str) -> str:
        """FIX: Properly escape a user query for SQLite FTS5 MATCH.

        FTS5 has a rich query syntax. To prevent injection and parse errors,
        we sanitize aggressively:
          1. Remove all FTS5 operators (AND, OR, NOT, NEAR, column filters)
          2. Strip special characters that break the parser
          3. Quote each token individually
          4. Join with OR for broad matching

        This turns user input into a safe, literal token search.
        """
        import re

        # FTS5 special characters that can break parsing
        # Remove: * ? ( ) { } [ ] ^ : = ! @ # % & \ ~
        cleaned = re.sub(r'[*?(){}\[\]^:=!@#%&\\~]', ' ', query)

        # Remove FTS5 keywords that could change query semantics
        # (case-insensitive, word-boundary)
        cleaned = re.sub(
            r'\b(AND|OR|NOT|NEAR)\b', ' ', cleaned, flags=re.IGNORECASE
        )

        # Collapse whitespace and split into tokens
        tokens = cleaned.split()

        if not tokens:
            return '""'  # Empty safe query

        # Quote each token individually and join with OR
        # Each token gets its own double-quote pair
        escaped_tokens = []
        for token in tokens[:20]:  # Cap at 20 tokens to prevent abuse
            # Double any internal quotes
            safe_token = token.replace('"', '""')
            escaped_tokens.append(f'"{safe_token}"')

        return ' OR '.join(escaped_tokens)

    def fts_search(self, query: str, limit: int = 50) -> list[dict]:
        """Full-text search using SQLite FTS5 BM25.

        FIX: Uses _escape_fts5_query() to sanitize user input,
        preventing FTS5 syntax injection and parse errors.
        """
        safe_query = self._escape_fts5_query(query)

        try:
            with self.connection() as conn:
                rows = conn.execute(
                    """SELECT c.id as chunk_id, c.document_id, c.content,
                              bm25(chunks_fts) as rank
                       FROM chunks_fts fts
                       JOIN chunks c ON c.rowid = fts.rowid
                       WHERE chunks_fts MATCH ?
                       ORDER BY rank
                       LIMIT ?""",
                    (safe_query, limit),
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error("fts_search_error", query=query[:50], error=str(e))
            return []

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Get aggregate database stats."""
        with self.connection() as conn:
            doc_count = conn.execute("SELECT COUNT(*) as c FROM documents").fetchone()["c"]
            chunk_count = conn.execute("SELECT COUNT(*) as c FROM chunks").fetchone()["c"]
            embedded_count = conn.execute(
                "SELECT COUNT(*) as c FROM chunks WHERE chroma_id IS NOT NULL"
            ).fetchone()["c"]
            entity_count = conn.execute("SELECT COUNT(*) as c FROM entities").fetchone()["c"]
            relation_count = conn.execute("SELECT COUNT(*) as c FROM relations").fetchone()["c"]
            conv_count = conn.execute("SELECT COUNT(*) as c FROM conversations").fetchone()["c"]
            failed = conn.execute(
                "SELECT COUNT(*) as c FROM documents WHERE status IN ('FAILED', 'PARSE_FAILED', 'FORGET_FAILED')"
            ).fetchone()["c"]
            by_source = self.count_documents_by_source()

            coverage = (embedded_count / chunk_count * 100) if chunk_count > 0 else 0.0
            graph_docs = conn.execute(
                "SELECT COUNT(*) as c FROM documents WHERE is_graphed = 1"
            ).fetchone()["c"]
            graph_coverage = (graph_docs / doc_count * 100) if doc_count > 0 else 0.0

            return {
                "total_documents": doc_count,
                "by_source_type": by_source,
                "total_chunks": chunk_count,
                "embedding_coverage_pct": round(coverage, 1),
                "graph_coverage_pct": round(graph_coverage, 1),
                "total_entities": entity_count,
                "total_relations": relation_count,
                "conversations": conv_count,
                "failed_documents": failed,
            }
