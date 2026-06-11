# MEMEX Architecture Reference

> Detailed technical documentation for developers working on or extending MEMEX v2.0.0.

---

## Table of Contents

- [Overview](#overview)
- [Design Principles](#design-principles)
- [Data Model](#data-model)
- [Six-Pillar Deep Dive](#six-pillar-deep-dive)
- [Storage Engine Details](#storage-engine-details)
- [API Design](#api-design)
- [Daemon Lifecycle](#daemon-lifecycle)
- [Migration System](#migration-system)
- [Model Migration Protocol](#model-migration-protocol)
- [Observability](#observability)
- [Security Model](#security-model)
- [Performance Considerations](#performance-considerations)
- [Known Limitations](#known-limitations)

---

## Overview

MEMEX is a **local-first, passive second brain** that captures, indexes, and retrieves personal knowledge from four sources (filesystem, browser, terminal, clipboard) using a six-pillar pipeline architecture. All data stays on the user's machine — no cloud services, no telemetry, no external dependencies.

### Key Metrics

| Metric | Value |
|--------|-------|
| Source files | 75 Python files |
| Lines of code | ~9,500 |
| Tests | 152 passing |
| Invariant tests | 30 (INV-001 to INV-030) |
| Storage engines | 4 (SQLite, ChromaDB, KuzuDB, Ollama) |
| Content parsers | 6 types |
| Secret redaction patterns | 7 + entropy heuristic |

---

## Design Principles

### 1. Local-First
Every byte stays on the user's machine. MEMEX makes zero outbound network connections. The API binds to `127.0.0.1` exclusively.

### 2. Passive Capture
Users should never have to manually curate their knowledge base. MEMEX watches existing digital exhaust and builds structure automatically.

### 3. SSOT (Single Source of Truth)
All operational constants live in versioned TOML addenda files. No hardcoded values in Python code. If a threshold exists, it's in a TOML file.

### 4. Atomicity
The forget protocol is a 10-step transaction across 3 stores. If any step fails, the failure is logged and the document is marked for retry.

### 5. Graceful Degradation
Every component degrades gracefully when dependencies are unavailable. Missing Ollama? Retrieval still works via FTS5. Missing tree-sitter? Code parsing falls back to line-based chunking.

---

## Data Model

### Canonical Data Contracts

These dataclasses define the boundaries between pillars. They live in `memex/config/settings.py`.

#### RawDocument (INGEST → PARSE)

```python
@dataclass
class RawDocument:
    source_type: str           # "filesystem", "browser", "terminal", "clipboard"
    source_path: str           # File path or URL
    raw_bytes: bytes           # Raw content
    encoding: str              # Detected encoding
    captured_at: datetime      # Capture timestamp
    source_metadata: dict      # Arbitrary metadata from source
    checksum: str              # SHA-256 of raw_bytes (auto-computed)
    priority: Priority         # CRITICAL=0, HIGH=1, NORMAL=2, LOW=3
```

- Implements `__lt__` for `PriorityQueue` ordering (lower value = higher priority)
- Checksum is auto-computed in `__post_init__` if not provided

#### ParsedDocument (PARSE → INDEX)

```python
@dataclass
class ParsedDocument:
    document_id: str           # UUID assigned during parse
    clean_content: str         # Extracted and cleaned text
    content_type: ContentType  # PDF, HTML, CODE, EMAIL, MARKDOWN, PLAIN
    language: Optional[str]    # Programming language (for code)
    word_count: int            # Auto-computed from clean_content
    char_count: int            # Auto-computed from clean_content
    parse_metadata: dict       # Parser-specific metadata
    parsed_at: datetime        # Parse timestamp
```

#### Chunk (Atomic Retrieval Unit)

```python
@dataclass
class Chunk:
    chunk_id: str              # UUID (auto-generated)
    document_id: str           # Parent document UUID
    content: str               # Chunk text
    token_count: int           # Estimated tokens
    chunk_index: int           # Position in document (0-based)
    total_chunks: int          # Total chunks in document
    start_char: int            # Start offset in original content
    end_char: int              # End offset in original content
    chroma_id: Optional[str]   # ChromaDB vector ID (set after embedding)
```

#### RetrievalResult (RECALL → ANSWER)

```python
@dataclass
class RetrievalResult:
    chunk_id: str
    document_id: str
    content: str
    combined_score: float      # Weighted fusion score
    vector_score: float        # Vector similarity component
    keyword_score: float       # BM25 keyword component
    graph_score: float         # Graph traversal component
    temporal_score: float      # Temporal decay component
    source_type: str
    source_path: str
    captured_at: datetime
    citation_index: int = 0    # 1-based citation number
```

### Document Lifecycle States

```
PENDING → PARSED → EMBEDDED → GRAPHED → INDEXED
   │         │                              ↑
   ↓         ↓                              │
PARSE_FAILED ← → FAILED ──→ retry (max 5) ──┘
                    │
                    ↓ (after 5 retries)
                ABANDONED
```

| Status | Meaning |
|--------|---------|
| `PENDING` | Ingested, waiting to be parsed |
| `PARSED` | Successfully parsed, waiting for embedding |
| `EMBEDDED` | Chunks embedded in ChromaDB |
| `GRAPHED` | Entities extracted to KuzuDB |
| `INDEXED` | Fully indexed in all stores |
| `FAILED` | Pipeline error (retryable) |
| `PARSE_FAILED` | Parser error (retryable) |
| `FORGET_FAILED` | Forget protocol partial failure |
| `ABANDONED` | Exceeded max retries (5) |

---

## Six-Pillar Deep Dive

### Pillar 1: INGEST (`memex/ingest/`)

**Purpose**: Passively capture digital exhaust from four sources.

#### Architecture

```
FilesystemIngestor ──→ IngestionQueue ──→ RawDocument
BrowserIngestor   ──→     (max 500)       (with checksum)
TerminalIngestor  ──→
ClipboardIngestor ──→
```

#### IngestionQueue

- `PriorityQueue` with max depth of 500 (from `retention.toml`)
- **Backpressure**: When queue is at max depth, oldest items are dropped
- **Deduplication**: Checked downstream by SHA-256 checksum in the daemon
- Thread-safe: `threading.Lock` protects `put()` and `get()`

#### Ingestor Base Class

```python
class BaseIngestor(ABC):
    def __init__(self, queue: IngestionQueue, settings: Settings): ...
    @abstractmethod
    def start(self) -> None: ...
    def stop(self) -> None: ...
```

#### FilesystemIngestor

- Uses `watchdog` for real-time file events (create, modify)
- Filters by extension and excluded paths
- Reads file content with encoding detection (`chardet`)
- Respects `.git/`, `.svn/`, `__pycache__/`, `.venv/` exclusions

#### BrowserIngestor

- Polls browser history databases (Chrome, Firefox, Safari)
- Period: 300 seconds (configurable)
- **Never fetches** pages from excluded domains (22 domains in `redaction_patterns.toml`)
- `fetch_page_content` defaults to `false` for privacy

#### TerminalIngestor

- Polls shell history files (`~/.bash_history`, `~/.zsh_history`, `~/.local/share/fish/fish_history`)
- Period: 120 seconds (configurable)
- Deduplicates by content hash

#### ClipboardIngestor

- Polls system clipboard via `pyperclip`
- Period: 30 seconds (configurable)
- Deduplicates by content hash

### Pillar 2: PARSE (`memex/parse/`)

**Purpose**: Normalize raw bytes into clean text with content-type metadata.

#### ParserDispatcher

Routes to the correct parser based on file extension and content detection:

```python
class ParserDispatcher:
    EXTENSION_MAP = {
        ".md": ContentType.MARKDOWN,
        ".html": ContentType.HTML,
        ".pdf": ContentType.PDF,
        ".eml": ContentType.EMAIL,
        ".py": ContentType.CODE,
        # ... 30+ code extensions
    }
```

#### CodeParser — 3-Strategy Fallback

```
Strategy 1: tree-sitter (best AST-aware chunking)
    ↓ (fails if language pack unavailable)
Strategy 2: regex-based function/class splitting
    ↓ (fails if no patterns match)
Strategy 3: line-based splitting (always works)
```

This fallback chain ensures code parsing works even without `tree-sitter-languages` installed (which has no Python 3.13 wheel).

### Pillar 3: INDEX (`memex/index/`)

**Purpose**: Index parsed documents into three parallel stores.

#### SmartChunker

Content-aware token budgeting from `chunking.toml`:

| Content Type | Token Budget | Overlap |
|-------------|-------------|---------|
| Prose (`PLAIN`, `MARKDOWN`) | 400 | 50 |
| Code (`CODE`) | 300 | 30 |
| Email (`EMAIL`) | 200 | 20 |
| PDF (`PDF`) | 400 | 50 |

Overlapping chunks ensure context isn't lost at boundaries.

#### Embedder

- Model: `nomic-embed-text` v1.5 via Ollama
- Uses persistent `httpx.Client` for connection reuse
- Generates 768-dimensional embeddings
- Stores in ChromaDB with metadata (source_type, source_path, captured_at, content_type, chunk_index)

#### GraphExtractor

- Extracts named entities from parsed text
- Uses capitalization heuristics and noun phrase patterns
- Stores entities in KuzuDB with `MENTIONED_IN` and `RELATED_TO` edges
- Entity ID resolution: SQLite first, UUID fallback

### Pillar 4: RECALL (`memex/recall/`)

**Purpose**: Retrieve relevant chunks using 4-signal weighted fusion.

See [Retrieval Engine](#retrieval-engine) in the README for the full formula.

#### Signal Extraction

| Signal | Source | Normalization |
|--------|--------|---------------|
| Vector | ChromaDB cosine distance → `1.0 - distance` | [0, 1] |
| Keyword | SQLite FTS5 BM25 rank | Min-max normalized to [0, 1] |
| Graph | KuzuDB entity neighbors | Fixed 0.8 for 1-hop |
| Temporal | `exp(-0.005 × age_days)` | [0, 1] |

#### Score Fusion

```python
combined = (0.40 × vector) + (0.30 × keyword) + (0.20 × graph) + (0.10 × temporal)
```

Missing signals default to 0.0. A chunk only needs to appear in at least one signal to be a candidate.

#### FTS5 Query Escaping

User queries are sanitized before passing to FTS5:
1. Strip SQL operators and special characters
2. Tokenize on whitespace
3. Quote each token individually
4. Cap at 20 tokens
5. Join with `AND`

### Pillar 5: ANSWER (`memex/answer/`)

**Purpose**: Generate cited responses using local LLM.

#### ChatEngine

```python
class ChatEngine:
    def chat(self, message: str, session_id: str) -> str:
        # 1. Retrieve relevant chunks via HybridRetriever
        # 2. Build prompt with [Source N] citations
        # 3. Include last 6 conversation turns
        # 4. Stream response from llama3:8b via Ollama
        # 5. Extract and validate citations
```

#### Prompt Engineering

The system prompt enforces:
- Every factual claim must cite `[Source N]`
- Sources are numbered 1, 2, 3, ... matching retrieval order
- If unsure, explicitly state uncertainty
- Never fabricate sources

### Pillar 6: PROTECT (`memex/protect/`)

**Purpose**: Prevent sensitive data from being stored, and enable complete deletion.

#### Redactor

```python
class Redactor:
    def redact(self, text: str) -> str:
        # 1. Apply all 7 regex patterns from redaction_patterns.toml
        # 2. Apply Shannon entropy heuristic
        #    - Split text into words
        #    - For words >= 20 chars with entropy >= 4.5
        #    - Check context window (30 chars) for key/secret/password
        #    - If found, redact with [REDACTED:high_entropy_string]
```

#### Shannon Entropy Heuristic

```python
def _shannon_entropy(s: str) -> float:
    """Calculate Shannon entropy of a string in bits per character."""
    freq = Counter(s)
    length = len(s)
    return -sum((c / length) * math.log2(c / length) for c in freq.values())
```

Parameters (from `redaction_patterns.toml`):
- `min_length`: 20 characters
- `entropy_threshold`: 4.5 bits/char
- `context_window_chars`: 30

#### 10-Step Forget Protocol

| Step | Action | Store | Reversible? |
|------|--------|-------|-------------|
| 1 | Fetch all chunk_ids | SQLite | — |
| 2 | Delete vectors | ChromaDB | No |
| 3 | Delete graph nodes | KuzuDB | No |
| 4 | Delete entity mentions | SQLite | No |
| 5 | Delete relations | SQLite | No |
| 6 | Delete chunks | SQLite | No |
| 7 | Delete document | SQLite | No |
| 8 | FTS auto-updates | SQLite (trigger) | Auto |
| 9 | Orphan entity cleanup | SQLite | No |
| 10 | Write audit log | SQLite | Append-only |

Steps 4–7 execute within a single SQLite connection/transaction. If any step fails, the document is marked `FORGET_FAILED` and a partial failure is logged.

---

## Storage Engine Details

### SQLite (`memex/db/sqlite.py`)

#### Configuration

- **WAL mode**: `PRAGMA journal_mode=WAL` — allows concurrent reads during writes
- **Connection pool**: 4 cached connections with thread-safe `_acquire()`/`_release()` pattern
- **Busy timeout**: 30 seconds
- **Foreign keys**: Enabled (`PRAGMA foreign_keys=ON`)

#### Schema Highlights

```sql
-- Documents with status tracking
CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_path TEXT NOT NULL,
    raw_content BLOB,
    clean_content TEXT,
    content_type TEXT,
    checksum TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'PENDING',
    word_count INTEGER DEFAULT 0,
    captured_at TEXT DEFAULT (datetime('now')),
    retry_count INTEGER DEFAULT 0,
    last_error TEXT
);

-- Chunks with FTS5
CREATE TABLE chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    token_count INTEGER DEFAULT 0,
    chunk_index INTEGER NOT NULL,
    total_chunks INTEGER NOT NULL,
    start_char INTEGER DEFAULT 0,
    end_char INTEGER DEFAULT 0,
    chroma_id TEXT
);

-- FTS5 virtual table
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    content,
    content='chunks',
    content_rowid='rowid'
);

-- Auto-sync trigger
CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, content) VALUES (new.rowid, new.content);
END;
```

#### FTS5 Query Construction

User queries are sanitized to prevent FTS5 syntax errors:

```python
def _escape_fts_query(query: str) -> str:
    """Escape a user query for FTS5."""
    # Strip operators
    cleaned = re.sub(r'[^\w\s]', ' ', query)
    # Tokenize
    tokens = cleaned.split()
    # Cap at 20
    tokens = tokens[:20]
    # Quote each token
    return ' '.join(f'"{t}"' for t in tokens)
```

### ChromaDB (`memex/db/chroma.py`)

- **Collection**: `memex_vectors_v1` (configurable)
- **Distance function**: Cosine similarity
- **HNSW parameters**: Default (M=16, ef_search=100)
- **Metadata**: `source_type`, `source_path`, `captured_at`, `content_type`, `chunk_index`, `document_id`
- **Health check**: `collection.count()` returns vector count

### KuzuDB (`memex/db/kuzu.py`)

- **Node types**: `Document`, `Chunk`, `Entity`
- **Edge types**: `CONTAINS` (Document→Chunk), `MENTIONED_IN` (Entity→Chunk), `RELATED_TO` (Entity→Entity)
- **Query language**: Cypher (KuzuDB dialect)
- **Schema**: Initialized on startup via `initialize()`

```cypher
// Node creation
CREATE (d:Document {id: $id, source_type: $type, source_path: $path, captured_at: $at})

// Edge creation
MATCH (d:Document), (c:Chunk) WHERE d.id = $doc_id AND c.id = $chunk_id
CREATE (d)-[:CONTAINS]->(c)

// Entity neighborhood query
MATCH (e:Entity)-[:MENTIONED_IN]->(c:Chunk)<-[:CONTAINS]-(d:Document)
WHERE e.name IN $names
RETURN DISTINCT d.id AS doc_id
```

---

## API Design

### Framework

- **FastAPI** with async handlers
- **Lifespan handler** (not deprecated `on_event`)
- **Middleware stack**: `RequestTimingMiddleware` → `LoopbackOnlyMiddleware`

### LoopbackOnlyMiddleware

```python
class LoopbackOnlyMiddleware(BaseHTTPMiddleware):
    ALLOWED_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}

    async def dispatch(self, request: Request, call_next):
        client_host = request.client.host if request.client else "unknown"
        if client_host not in self.ALLOWED_HOSTS:
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
        return await call_next(request)
```

### Async/Sync Bridge

All route handlers use `_run_sync()` to avoid blocking the event loop:

```python
async def _run_sync(func, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args, **kwargs)
```

### SSE Streaming

Chat responses stream via Server-Sent Events:

```python
async def stream_chat(request: ChatRequest):
    async def generate():
        for token in chat_engine.stream(request.message, request.session_id):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"
    return EventResponse(generate())
```

---

## Daemon Lifecycle

### Startup Sequence

```
1. Settings.from_config()        → Load configuration
2. ensure_directories()          → Create ~/.memex/data, logs
3. initialize()                  → Run migrations, init stores
4. start_workers()               → ThreadPoolExecutor(count=4)
5. start_ingestors()             → Start 4 ingestor threads
6. purge_scheduler.start()       → TTL purge background thread
7. start_api()                   → Uvicorn on 127.0.0.1:7700
```

### Shutdown Sequence (5-Phase Graceful Drain)

```
SIGTERM/SIGINT received
    │
    ▼
Phase 1: Stop ingestors (no new items enter queue)
Phase 2: Drain in-flight work (wait up to 30s)
Phase 3: Shutdown ThreadPoolExecutor
Phase 4: Stop purge scheduler
Phase 5: Stop API server
```

The daemon uses `threading.Event` to coordinate drain completion. Workers check `self._draining` on each iteration and exit cleanly when set.

---

## Migration System

### Alembic-Style Runner (`memex/db/migrations/runner.py`)

```python
class MigrationRunner:
    def run_migrations(self, dry_run=False):
        # 1. Create _migrations table if not exists
        # 2. Get list of applied migrations
        # 3. Discover .sql files in migrations/ directory
        # 4. Sort by filename prefix (001_, 002_, ...)
        # 5. Execute unapplied migrations in order
        # 6. Record each in _migrations table
```

### Migration Files

| File | Description |
|------|-------------|
| `001_initial.sql` | Full schema: 12 tables, FTS5, triggers, indexes |
| `002_add_retry_columns.sql` | `retry_count`, `last_error` columns on documents |

### Adding a New Migration

1. Create `memex/db/migrations/003_descriptive_name.sql`
2. Include `UP` section with DDL statements
3. The runner will detect and execute it on next startup

---

## Model Migration Protocol

When switching embedding models, the `ModelMigrationWorker` executes a 5-phase protocol:

```
Phase 1: Register new model in embed_models table
Phase 2: Create new ChromaDB collection
Phase 3: Re-embed all documents (background, batched)
Phase 4: Verify vector counts match chunk counts
Phase 5: Atomically switch active_collection pointer
```

This allows zero-downtime model migrations — the old collection remains active until the new one is fully populated and verified.

---

## Observability

### Structured Logging

```python
logger.info("operation_completed",
    duration_ms=elapsed,
    document_id=doc_id[:16],
    chunk_count=len(chunks))
```

Logs are written to:
- `stdout` (configurable level)
- `~/.memex/logs/memex.log` (rotation: 10 MB, 5 backups)

### MetricsCollector

```python
metrics = get_metrics()
with metrics.timer("retrieval.hybrid"):
    results = retriever.retrieve(query)

# Report p50, p95, p99 latencies
report = metrics.report()
```

### SLOMonitor

Each SLO from `slos.toml` is tracked with:
- `SLOTimer` context manager for latency measurement
- p50/p95/p99 percentile tracking
- Violation logging when alert threshold is exceeded
- Measurement window tracking

### Log Streaming

`GET /api/logs/stream` provides SSE access to the application log, with rotation-aware file following:

```python
async def log_stream():
    """Rotation-aware SSE log generator."""
    while True:
        line = log_file.readline()
        if line:
            yield f"data: {json.dumps({'log': line.strip()})}\n\n"
        else:
            await asyncio.sleep(0.5)
            # Check for rotation (inode change)
```

---

## Security Model

### Trust Zones

```
┌─────────────────────────────────────────────┐
│ Zone 1: Fully Trusted                       │
│   MEMEX daemon, local stores, Ollama, UI    │
├─────────────────────────────────────────────┤
│ Zone 2: Semi-Trusted (read-only access)     │
│   Browser DB, filesystem, terminal history  │
├─────────────────────────────────────────────┤
│ Zone 3: Untrusted                           │
│   External services (zero data transmission)│
└─────────────────────────────────────────────┘
```

### Attack Surface

| Vector | Mitigation |
|--------|-----------|
| Network | Loopback-only middleware, Docker `127.0.0.1` binding |
| Secrets in data | 7 regex patterns + Shannon entropy redaction |
| Sensitive browsing | 22 excluded domains |
| Data deletion | 10-step atomic forget with verification |
| File permissions | `0o700` on data directory |
| Disk encryption | `memex doctor` checks FileVault/LUKS/BitLocker |

---

## Performance Considerations

### Connection Pooling

SQLite uses a pool of 4 cached connections with thread-safe acquire/release. This avoids the overhead of creating new connections for each operation.

### Batch Embedding

Chunks are embedded sequentially via Ollama. For large document sets, the model migration worker batches embeddings to avoid memory pressure.

### FTS5 Optimization

- FTS5 index is populated via triggers (no manual sync)
- Queries are tokenized and capped at 20 terms
- The `content=` parameter enables rebuilding the index

### Vector Search

ChromaDB HNSW with default parameters provides sub-200ms p95 latency at 1M chunks (per SLO-003).

### Backpressure

The ingestion queue has a hard ceiling of 500 items. When exceeded, oldest items are dropped. A warning is logged at 400 items.

---

## Known Limitations

| Limitation | Impact | Mitigation |
|-----------|--------|-----------|
| Sequential embedding | Large batches are slow | Model migration worker batches |
| Basic NER | Entity extraction uses heuristics, not spaCy NER | Graph signal is lowest weight (0.20) |
| No real-time sync | Source polling intervals (30-300s) | Acceptable for passive capture |
| KuzuDB dialect | Cypher syntax differs from Neo4j | Tested against KuzuDB's dialect |
| Single-user | No multi-user support | By design (local-first) |
| No OCR | Image content not extracted | Future enhancement |

---

*This document is maintained alongside the codebase. When architecture changes, update this file in the same PR.*
