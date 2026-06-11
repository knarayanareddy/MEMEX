-- ═══════════════════════════════════════════════════════════════
-- MEMEX SQLite Schema — Migration 001 (Initial)
-- ═══════════════════════════════════════════════════════════════

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;

-- Core document store
CREATE TABLE IF NOT EXISTS documents (
    id              TEXT PRIMARY KEY,
    source_type     TEXT NOT NULL,
    source_path     TEXT NOT NULL,
    raw_content     BLOB,
    clean_content   TEXT,
    content_type    TEXT,
    checksum        TEXT NOT NULL UNIQUE,
    word_count      INTEGER,
    status          TEXT NOT NULL DEFAULT 'PENDING',
    captured_at     DATETIME NOT NULL,
    ingested_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    parsed_at       DATETIME,
    embedded_at     DATETIME,
    graphed_at      DATETIME,
    raw_purged_at   DATETIME,
    is_embedded     INTEGER DEFAULT 0,
    is_graphed      INTEGER DEFAULT 0,
    source_metadata TEXT,
    retry_count     INTEGER DEFAULT 0,
    last_error      TEXT
);

-- Retrieval units
CREATE TABLE IF NOT EXISTS chunks (
    id              TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content         TEXT NOT NULL,
    token_count     INTEGER,
    chunk_index     INTEGER,
    total_chunks    INTEGER,
    start_char      INTEGER,
    end_char        INTEGER,
    chroma_id       TEXT,
    embedded_at     DATETIME,
    UNIQUE(document_id, chunk_index)
);

-- Entity registry
CREATE TABLE IF NOT EXISTS entities (
    id              TEXT PRIMARY KEY,
    canonical_name  TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    first_seen      DATETIME,
    last_seen       DATETIME,
    mention_count   INTEGER DEFAULT 0
);

-- Entity occurrence tracking
CREATE TABLE IF NOT EXISTS entity_mentions (
    id              TEXT PRIMARY KEY,
    entity_id       TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    document_id     TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id        TEXT REFERENCES chunks(id) ON DELETE CASCADE,
    mention_text    TEXT,
    start_char      INTEGER,
    confidence      REAL,
    mentioned_at    DATETIME
);

-- LLM-extracted relations
CREATE TABLE IF NOT EXISTS relations (
    id              TEXT PRIMARY KEY,
    subject_id      TEXT NOT NULL REFERENCES entities(id),
    predicate       TEXT NOT NULL,
    object_id       TEXT NOT NULL REFERENCES entities(id),
    document_id     TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id        TEXT REFERENCES chunks(id) ON DELETE CASCADE,
    confidence      REAL,
    evidence        TEXT,
    extracted_at    DATETIME
);

-- Conversation sessions
CREATE TABLE IF NOT EXISTS conversations (
    id              TEXT PRIMARY KEY,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_active     DATETIME,
    title           TEXT
);

-- Conversation turns
CREATE TABLE IF NOT EXISTS conversation_turns (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    sources_cited   TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Embed model registry
CREATE TABLE IF NOT EXISTS embed_model_registry (
    id              TEXT PRIMARY KEY,
    model_name      TEXT NOT NULL,
    model_version   TEXT NOT NULL,
    registered_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active       INTEGER DEFAULT 0,
    total_chunks    INTEGER DEFAULT 0,
    collection_name TEXT NOT NULL
);

-- Forget audit log
CREATE TABLE IF NOT EXISTS forget_log (
    id              TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL,
    source_path     TEXT,
    source_type     TEXT,
    forgotten_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    chroma_verified INTEGER DEFAULT 0,
    kuzu_verified   INTEGER DEFAULT 0,
    sqlite_verified INTEGER DEFAULT 0
);

-- FTS5 virtual tables
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    content,
    content="documents",
    content_rowid="rowid",
    tokenize="porter unicode61"
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    content,
    content="chunks",
    content_rowid="rowid",
    tokenize="porter unicode61"
);

-- FTS sync triggers for documents
CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, content) VALUES (new.rowid, COALESCE(new.clean_content, ''));
END;

CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, content) VALUES ('delete', old.rowid, COALESCE(old.clean_content, ''));
    INSERT INTO documents_fts(rowid, content) VALUES (new.rowid, COALESCE(new.clean_content, ''));
END;

CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, content) VALUES ('delete', old.rowid, COALESCE(old.clean_content, ''));
END;

-- FTS sync triggers for chunks
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, content) VALUES (new.rowid, new.content);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
    INSERT INTO chunks_fts(rowid, content) VALUES (new.rowid, new.content);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
END;

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_documents_source_type    ON documents(source_type);
CREATE INDEX IF NOT EXISTS idx_documents_captured_at    ON documents(captured_at);
CREATE INDEX IF NOT EXISTS idx_documents_checksum       ON documents(checksum);
CREATE INDEX IF NOT EXISTS idx_documents_status         ON documents(status);
CREATE INDEX IF NOT EXISTS idx_chunks_document_id       ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_chroma_id         ON chunks(chroma_id);
CREATE INDEX IF NOT EXISTS idx_entity_mentions_entity   ON entity_mentions(entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_mentions_document ON entity_mentions(document_id);
CREATE INDEX IF NOT EXISTS idx_relations_subject        ON relations(subject_id);
CREATE INDEX IF NOT EXISTS idx_relations_object         ON relations(object_id);
CREATE INDEX IF NOT EXISTS idx_relations_document       ON relations(document_id);
