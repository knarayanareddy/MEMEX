-- Migration: 002 — Add retry tracking columns
-- Applied: automatically by migration runner

-- Add retry_count and last_error if they don't exist (idempotent)
-- SQLite doesn't have IF NOT EXISTS for columns, so we use a safe pattern:

-- Create a new table with the desired schema
CREATE TABLE IF NOT EXISTS documents_v2 (
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
