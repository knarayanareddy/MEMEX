# Changelog

All notable changes to MEMEX are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.0.1] — 2025-01-16

### Fixed

#### Critical Bugs
- **[CRITICAL] Fixed vector metadata corruption during model migration** (`migration.py`):
  - SQL query now includes `c.document_id` in the SELECT clause
  - `embed_and_store()` receives the correct document UUID instead of `source_path`
  - Prevents orphaned vectors that would survive the forget protocol
- **Fixed forget audit log always recording `chroma_verified=0, kuzu_verified=0`** (`forget.py`):
  - `chroma_verified` and `kuzu_verified` are now set to `True` after successful deletion
  - Audit trail now accurately reflects actual store verification status
  - Forget response now includes a `verification` dict with per-store flags

#### Dead Code Integration
- **Integrated `ModelMigrationWorker` into production API** (`app.py`, `system.py`):
  - `/api/models/migrate` now delegates to real `ModelMigrationWorker.start_migration()`
  - `/api/models/migrate/progress` now returns real progress from `get_progress()`
  - Worker is initialized in app state with proper dependency injection
- **Integrated `SLOTimer` into production code paths** (`hybrid_retrieval.py`, `forget.py`):
  - `vector_search_ms` tracked in `_vector_signal()`
  - `fts_search_ms` tracked in `_keyword_signal()`
  - `hybrid_retrieval_ms` tracked in `retrieve()`
  - `forget_doc_ms` tracked in `forget_document()`

#### Documentation Alignment
- **Reindexed all 30 invariant tests** (INV-001 to INV-030) with 1-to-1 mapping:
  - INV-001 to INV-004: Security (was: INV-001 to INV-005)
  - INV-005 to INV-006: Redaction (was: INV-005 to INV-012)
  - INV-007 to INV-012: Forget (was: INV-008 to INV-013)
  - INV-013 to INV-017: Ingestion (was: INV-020 to INV-025)
  - INV-018 to INV-024: Retrieval (was: INV-016 to INV-019)
  - INV-025 to INV-030: Config Hygiene (was: INV-026 to INV-030)
- Updated `docs/INVARIANTS.md` with exact ID-to-test-function mapping table
- Updated `SLOMonitor` initialized in app state for dashboard access

---

## [2.0.0] — 2025-01-15

### Added

#### Six-Pillar Architecture
- **INGEST**: Four passive ingestors (filesystem, browser, terminal, clipboard) with priority queue (max depth 500)
- **PARSE**: Six content-type parsers (plain, markdown, HTML, email, PDF, code) with universal dispatcher
- **INDEX**: Triple-store indexing (ChromaDB vectors, SQLite FTS5, KuzuDB graph) with smart content-aware chunker
- **RECALL**: Four-signal hybrid retrieval (vector 0.40 + keyword 0.30 + graph 0.20 + temporal 0.10)
- **ANSWER**: RAG chat engine with `[Source N]` citation enforcement, conversation history, SSE streaming
- **PROTECT**: Secret redaction (7 regex + Shannon entropy), 10-step atomic forget, TTL purge scheduler

#### Storage Stack
- SQLite with WAL mode, 12 tables, FTS5 virtual tables, triggers, connection pool (4 connections)
- ChromaDB with HNSW cosine similarity, metadata filtering
- KuzuDB with Cypher queries for entity-relationship graph
- Ollama integration for local LLM inference (nomic-embed-text + llama3:8b)

#### API & Interfaces
- FastAPI REST API bound to `127.0.0.1:7700` with loopback-only middleware
- Chat endpoints with SSE streaming
- Memory search, timeline, and hard-forget endpoints
- Graph entity and relation query endpoints
- System health, stats, reindex, and log streaming endpoints
- Textual TUI chat interface with session management
- Web SPA with Chat, Search, Timeline, Graph, and Settings views

#### Configuration (SSOT)
- 5 addenda TOML files as canonical source of truth for all operational constants
- `retrieval_weights.toml` — signal weights, temporal decay, retrieval limits
- `chunking.toml` — token budgets per content type (prose 400, code 300, email 200)
- `redaction_patterns.toml` — 7 secret patterns, entropy config, 22 excluded domains
- `retention.toml` — TTLs, queue limits, purge intervals
- `slos.toml` — 8 SLO definitions with targets and alert thresholds

#### Security
- `LoopbackOnlyMiddleware` rejects all non-loopback requests (127.0.0.1, ::1, localhost)
- Secret redaction before storage: OpenAI keys, GitHub PATs, AWS keys, private keys, bearer tokens, DB strings, credit cards
- Shannon entropy heuristic (threshold 4.5, min length 20) catches unknown secrets
- 22 excluded browser domains (banking, password managers, SSO, email, health)
- 10-step atomic forget protocol with store verification and audit logging
- Data directory permissions enforced to `0o700`
- Disk encryption detection in `memex doctor` (FileVault/LUKS/BitLocker)

#### Daemon & Operations
- `MEMEXDaemon` with 5-phase graceful drain shutdown (SIGTERM/SIGINT)
- `ThreadPoolExecutor` for worker pool (configurable count, default 4)
- Alembic-style migration runner with `_migrations` tracking table
- Model migration worker (5-phase background re-embedding protocol)
- SLO monitor with `SLOTimer`, p50/p95 tracking, violation logging
- Structured logging with rotation-aware file handler

#### DevOps
- Multi-stage Dockerfile (builder + runtime with Ollama bundled)
- `docker-compose.yml` with localhost-only binding, resource limits (4 GB RAM, 2 CPUs)
- GitHub Actions CI: 4-stage pipeline (static analysis → unit → integration → coverage)

#### Testing
- **150 tests passing**: 30 invariant tests + 25+ unit tests + 10+ integration tests
- Invariant tests (INV-001 through INV-030) covering security, redaction, forget, retrieval, ingestion, config hygiene
- Shared test fixtures with ephemeral SQLite databases
- Coverage reporting with `pytest-cov`

#### Code Parser
- 3-strategy tree-sitter fallback for 30+ programming languages
- Graceful degradation when tree-sitter languages pack is unavailable

### Fixed
- `RawDocument` implements `__lt__` for `PriorityQueue` comparison
- FastAPI `TestClient` host `"testclient"` added to loopback middleware allowlist
- Markdown parser handles empty content after `.strip()`
- SQLite `purge_raw_content` correctly handles timestamp-based purging
- FTS5 query escaping strips operators and special characters, caps at 20 tokens
- Graph extractor scoping: `entity_id` always resolved from SQLite first
- All API routes use `run_in_executor` to avoid blocking the event loop
- Lifespan handler replaces deprecated `on_event` in FastAPI app factory

---

## [1.0.0] — 2024-06-01

### Added
- Initial proof-of-concept with basic ingestion and search
- SQLite storage with FTS5
- Simple CLI interface

[2.0.0]: https://github.com/knarayanareddy/MEMEX/releases/tag/v2.0.0
[1.0.0]: https://github.com/knarayanareddy/MEMEX/releases/tag/v1.0.0
