<p align="center">
  <img src="https://img.shields.io/badge/version-2.0.0-blue" alt="Version" />
  <img src="https://img.shields.io/badge/python-3.11%2B-brightgreen" alt="Python" />
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License" />
  <img src="https://img.shields.io/badge/tests-150%20passing-success" alt="Tests" />
  <img src="https://img.shields.io/badge/local--first-100%25-orange" alt="Local First" />
</p>

<h1 align="center">🧠 MEMEX v2.0.0</h1>
<h3 align="center">Local-First Passive Second Brain</h3>

<p align="center">
  <em>"You should not have to curate your memory."</em>
</p>

<p align="center">
  MEMEX watches what you already do — browsing, coding, writing, copying — and builds<br/>
  a queryable knowledge graph automatically. <strong>All data stays on your machine.</strong><br/>
  No cloud. No telemetry. No accounts. You own every byte.
</p>

---

## 📑 Table of Contents

- [Features](#-features)
- [Architecture](#-architecture)
- [Quick Start](#-quick-start)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [CLI Reference](#-cli-reference)
- [API Reference](#-api-reference)
- [Data Flow](#-data-flow)
- [Storage Stack](#-storage-stack)
- [Security & Privacy](#-security--privacy)
- [The Six Pillars](#-the-six-pillars)
- [Retrieval Engine](#-retrieval-engine)
- [Invariants](#-invariants)
- [Docker Deployment](#-docker-deployment)
- [Development](#-development)
- [Testing](#-testing)
- [Project Structure](#-project-structure)
- [Configuration Addenda](#-configuration-addenda-ssot)
- [SLO Targets](#-slo-targets)
- [Troubleshooting](#-troubleshooting)
- [License](#-license)

---

## ✨ Features

| Category | What it does |
|----------|-------------|
| **Passive Ingestion** | Watches filesystem, browser history, terminal sessions, and clipboard — zero manual curation |
| **Universal Parsing** | PDF, HTML, Markdown, Email, Code (30+ languages), Plain text |
| **Hybrid Retrieval** | 4-signal fusion: vector similarity + keyword (BM25) + graph traversal + temporal decay |
| **Local LLM Chat** | Chat with your knowledge using llama3:8b, every answer cites `[Source N]` |
| **Entity Graph** | Automatically extracts entities and relationships into a knowledge graph |
| **Secret Redaction** | 7 regex patterns + Shannon entropy heuristic — API keys, PATs, private keys never stored |
| **Hard Forget** | 10-step atomic deletion across all stores with verification and audit logging |
| **Loopback-Only API** | All endpoints bound to `127.0.0.1:7700` — network inaccessible by design |
| **Multi-UI** | Terminal TUI, Web SPA, and REST API — pick your interface |
| **Config SSOT** | All weights, budgets, and thresholds defined in versioned TOML addenda files |
| **150 Tests** | 30 invariant tests + unit + integration — every assertion has real logic |

---

## 🏛 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        USER INTERFACES                       │
│   TUI (Textual)  │  Web SPA  │  REST API (FastAPI :7700)    │
└────────┬──────────────┬──────────────┬───────────────────────┘
         │              │              │
         ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────┐
│                      ANSWER (RAG Engine)                     │
│        Chat with citations · SSE streaming · Sessions         │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                     RECALL (Hybrid Retrieval)                 │
│   Vector(0.40) + Keyword(0.30) + Graph(0.20) + Temporal(0.10)│
└──────┬──────────┬──────────┬──────────┬──────────────────────┘
       │          │          │          │
       ▼          ▼          ▼          ▼
┌───────────┐ ┌────────┐ ┌────────┐ ┌──────────────────────────┐
│  ChromaDB │ │ SQLite │ │ KuzuDB │ │     Temporal Decay       │
│  (HNSW)   │ │ (FTS5) │ │(Cypher)│ │  exp(-λ × age_days)      │
└─────┬─────┘ └───┬────┘ └───┬────┘ └──────────────────────────┘
      │           │          │
      └───────────┼──────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                       INDEX (Pipeline)                       │
│   Embed (nomic-embed-text) · Chunk · Graph Extract           │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                        PARSE (Universal)                     │
│   PDF · HTML · Markdown · Email · Code · Plain text          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                       INGEST (Passive)                       │
│   Filesystem Watcher · Browser History · Terminal · Clipboard│
└─────────────────────────────────────────────────────────────┘
                         ▲
                         │
              ┌──────────┴──────────┐
              │      PROTECT        │
              │  Redact · Forget    │
              │  Purge · Audit      │
              └─────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | ≥ 3.11 | 3.13 recommended |
| Ollama | Latest | [ollama.com](https://ollama.com) |
| Disk space | ~2 GB | Models + data |

### 1. Install Ollama and pull models

```bash
# Install Ollama (macOS/Linux)
curl -fsSL https://ollama.com/install.sh | sh

# Pull required models
ollama pull nomic-embed-text    # Embedding model (~274 MB)
ollama pull llama3:8b           # Chat model (~4.7 GB)
```

### 2. Install MEMEX

```bash
git clone https://github.com/knarayanareddy/MEMEX.git
cd MEMEX
pip install -e ".[dev]"
```

### 3. Initialize and verify

```bash
memex init      # Create ~/.memex/ with default config
memex doctor    # Pre-flight health check
```

### 4. Start the daemon

```bash
memex start     # Starts daemon on 127.0.0.1:7700
```

### 5. Interact

```bash
# Terminal TUI
memex chat

# Or open the Web UI
open http://localhost:7700

# Or use the API directly
curl http://localhost:7700/api/health
curl "http://localhost:7700/api/memory/search?q=my+query"
```

---

## 📦 Installation

### From Source (Recommended)

```bash
git clone https://github.com/knarayanareddy/MEMEX.git
cd MEMEX
pip install -e ".[dev]"
```

### With Docker

```bash
docker compose up -d
```

See [Docker Deployment](#-docker-deployment) for details.

### Dependencies

MEMEX depends on:

| Package | Purpose |
|---------|---------|
| `fastapi` + `uvicorn` | REST API server |
| `chromadb` | Vector embeddings (HNSW cosine) |
| `kuzu` | Graph database (Cypher queries) |
| `httpx` | HTTP client for Ollama |
| `textual` | Terminal UI framework |
| `watchdog` | Filesystem event watching |
| `pdfminer.six` | PDF text extraction |
| `markdown-it-py` | Markdown parsing |
| `lxml` + `readability-lxml` | HTML content extraction |
| `tree-sitter` | Code parsing (30+ languages) |
| `rich` | Terminal formatting |
| `psutil` | System metrics |

---

## ⚙ Configuration

MEMEX uses a two-layer configuration system:

### Layer 1: User Config (`~/.memex/config.toml`)

User-facing settings for data paths, models, watchers, and intervals. Generated by `memex init`:

```toml
[daemon]
data_dir         = "~/.memex"
log_level        = "INFO"
api_host         = "127.0.0.1"     # MUST be loopback
api_port         = 7700
ollama_base_url  = "http://127.0.0.1:11434"

[embedding]
model             = "nomic-embed-text"
model_version     = "1.5"
active_collection = "memex_vectors_v1"

[chat]
model             = "llama3:8b"

[watcher]
paths             = ["~/Documents", "~/Projects"]
excluded_extensions = [".git", ".svn", ".hg", "__pycache__"]

[browser]
fetch_page_content     = false
poll_interval_seconds  = 300

[terminal]
poll_interval_seconds  = 120

[clipboard]
poll_interval_seconds  = 30

[workers]
count              = 4

[graph]
extract_relations  = false
```

### Layer 2: Addenda TOML (SSOT — Single Source of Truth)

Operational constants are defined in versioned addenda files inside the package. These are the **canonical source** — values are never duplicated in code.

| File | Purpose |
|------|---------|
| `retrieval_weights.toml` | Vector/keyword/graph/temporal weights, temporal decay λ |
| `chunking.toml` | Token budgets per content type |
| `redaction_patterns.toml` | Secret regex patterns, entropy config, excluded domains |
| `retention.toml` | TTLs, queue depth, purge intervals |
| `slos.toml` | SLO targets and alert thresholds |

### Environment Variables

| Variable | Overrides | Default |
|----------|-----------|---------|
| `MEMEX_DATA_DIR` | Data directory path | `~/.memex` |
| `MEMEX_LOG_LEVEL` | Log level | `INFO` |
| `MEMEX_API_PORT` | API port | `7700` |
| `MEMEX_OLLAMA_URL` | Ollama base URL | `http://127.0.0.1:11434` |

---

## 🖥 CLI Reference

```bash
memex init          # Initialize config and data directories
memex doctor        # Pre-flight health check (Ollama, Python, encryption, perms)
memex start         # Start the daemon (blocking)
memex chat          # Launch the terminal TUI
memex status        # Query daemon health endpoint
```

### `memex doctor` Checks

| Check | What it verifies |
|-------|-----------------|
| Data directory | `~/.memex` exists with correct permissions (`700`) |
| Config file | `~/.memex/config.toml` exists and parses correctly |
| Ollama | Running at `localhost:11434`, models available |
| Python | Version ≥ 3.11 |
| Disk encryption | FileVault (macOS) / LUKS (Linux) / BitLocker (Windows) |
| Directory permissions | Data dir is `0o700` |

---

## 🔌 API Reference

All endpoints are on `http://127.0.0.1:7700`. Requests from non-loopback addresses are rejected.

### Chat

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/chat` | Send a message, get a cited response |
| `GET` | `/api/chat/stream` | SSE streaming chat |
| `GET` | `/api/chat/sessions` | List conversation sessions |
| `GET` | `/api/chat/sessions/{id}` | Get session history |
| `DELETE` | `/api/chat/sessions/{id}` | Delete a session |

### Memory

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/memory/search?q=...` | Hybrid search across all indexed content |
| `GET` | `/api/memory/timeline` | Chronological listing with pagination |
| `GET` | `/api/memory/{id}` | Get document details |
| `DELETE` | `/api/memory/{id}` | Hard forget (10-step protocol) |

### Graph

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/graph/entities?q=...` | Search entities |
| `GET` | `/api/graph/relations?entity=...` | Get relations for an entity |

### System

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | System health (stores, models, uptime) |
| `GET` | `/api/stats` | Ingestion metrics (document counts, chunk counts) |
| `POST` | `/api/reindex` | Trigger full re-index |
| `GET` | `/api/models` | List active embedding models |
| `GET` | `/api/logs/stream` | SSE log stream (rotation-aware) |

### Example Requests

```bash
# Health check
curl http://localhost:7700/api/health

# Search your knowledge
curl "http://localhost:7700/api/memory/search?q=deploy+pipeline&limit=10"

# Chat with citations
curl -X POST http://localhost:7700/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How did I configure the CI pipeline?"}'

# Hard forget a document
curl -X DELETE http://localhost:7700/api/memory/doc-uuid-here

# Stream logs
curl http://localhost:7700/api/logs/stream
```

---

## 🔄 Data Flow

```
1. INGEST
   Filesystem Watcher ──┐
   Browser History   ──┤
   Terminal Sessions ──┼──→ IngestionQueue (max 500) ──→ RawDocument
   Clipboard         ──┘         (PriorityQueue)

2. PARSE
   RawDocument ──→ ParserDispatcher ──→ ParsedDocument
                    ├── PlainParser
                    ├── MarkdownParser
                    ├── HTMLParser
                    ├── EmailParser
                    ├── PDFParser
                    └── CodeParser (tree-sitter, 3-strategy fallback)

3. PROTECT (Redaction)
   ParsedDocument ──→ Redactor ──→ Clean content
                       ├── 7 regex patterns (API keys, PATs, etc.)
                       └── Shannon entropy heuristic (threshold 4.5)

4. INDEX
   Clean content ──→ SmartChunker ──→ Chunks
                      │  prose: 400 tokens, code: 300, email: 200
                      │
                      ├──→ Embedder (nomic-embed-text) ──→ ChromaDB
                      ├──→ FTS5 Index ──→ SQLite
                      └──→ GraphExtractor ──→ KuzuDB

5. RECALL
   Query ──→ HybridRetriever
              ├── Vector signal (cosine similarity)     weight: 0.40
              ├── Keyword signal (BM25 FTS5)            weight: 0.30
              ├── Graph signal (entity neighborhood)    weight: 0.20
              └── Temporal signal (exp decay)           weight: 0.10
              ──→ Fused results sorted by combined score

6. ANSWER
   Results ──→ ChatEngine (llama3:8b)
               ├── Retrieves top-k chunks via RECALL
               ├── Builds prompt with [Source N] citations
               ├── Manages conversation history (6 turns)
               ──→ Streams response with SSE
```

---

## 💾 Storage Stack

| Store | Engine | Purpose | Location |
|-------|--------|---------|----------|
| **SQLite** | WAL mode | Relational data, FTS5 search, metadata | `~/.memex/data/memex.db` |
| **ChromaDB** | HNSW cosine | Vector embeddings | `~/.memex/data/chroma/` |
| **KuzuDB** | Cypher queries | Entity-relationship graph | `~/.memex/data/kuzu/` |
| **Ollama** | Local inference | Embeddings + chat LLM | `127.0.0.1:11434` |

### SQLite Schema (12 tables)

| Table | Purpose |
|-------|---------|
| `documents` | Source documents with status tracking |
| `chunks` | Content chunks (atomic retrieval unit) |
| `chunks_fts` | FTS5 virtual table for full-text search |
| `entities` | Extracted named entities |
| `entity_mentions` | Entity-chunk associations |
| `relations` | Entity-entity relationships |
| `embed_models` | Embedding model registry |
| `conversations` | Chat conversation sessions |
| `conversation_turns` | Individual chat messages |
| `forget_audit_log` | Forget operation audit trail |
| `_migrations` | Schema migration tracking |
| `_migrations_lock` | Migration concurrency control |

---

## 🔒 Security & Privacy

### Trust Zones

| Zone | Scope | Trust Level |
|------|-------|-------------|
| **Zone 1** | MEMEX daemon, local stores, Ollama, UI | Fully trusted |
| **Zone 2** | Browser DB, filesystem, terminal history | Semi-trusted (read-only) |
| **Zone 3** | Any external service | Untrusted — no data transmitted |

### Network Security

- **API bound to `127.0.0.1:7700`** — `LoopbackOnlyMiddleware` rejects all non-loopback requests
- **No outbound connections** — MEMEX never phones home
- **No telemetry** — zero analytics, zero tracking
- **Docker binds to `127.0.0.1`** — `ports: ["127.0.0.1:7700:7700"]`

### Secret Redaction (7 patterns + entropy)

| Pattern | Regex | Example |
|---------|-------|---------|
| OpenAI API Key | `sk-[A-Za-z0-9]{48}` | `[REDACTED:openai_key]` |
| GitHub PAT | `ghp_[A-Za-z0-9]{36}` | `[REDACTED:github_pat]` |
| AWS Access Key | `AKIA[0-9A-Z]{16}` | `[REDACTED:aws_access_key]` |
| Private Key Header | `-----BEGIN [A-Z ]*PRIVATE KEY-----` | `[REDACTED:private_key]` |
| Bearer Token | `Bearer [A-Za-z0-9\-._~+/]+=*` | `[REDACTED:bearer_token]` |
| DB Connection String | `(postgres\|mysql\|mongodb\|redis)://...` | `[REDACTED:db_connection_string]` |
| Credit Card | Visa/MC/Amex patterns | `[REDACTED:credit_card]` |

Plus **Shannon entropy heuristic** (threshold 4.5, min length 20) catches secrets that don't match known patterns.

### 22 Excluded Browser Domains

Banking, password managers, SSO providers, email, health, and messaging sites are **never** fetched:

```
chase.com, bankofamerica.com, wellsfargo.com,
1password.com, lastpass.com, bitwarden.com, dashlane.com,
okta.com, auth0.com, onelogin.com,
mail.google.com, outlook.live.com, mail.yahoo.com,
127.0.0.1, localhost, *.local
```

### Hard Forget Protocol (10 steps)

1. Fetch all chunk IDs for document
2. Delete vectors from ChromaDB
3. Delete graph nodes from KuzuDB
4. Delete entity mentions from SQLite
5. Delete relations from SQLite
6. Delete chunks from SQLite
7. Delete document row from SQLite
8. FTS auto-updates via triggers
9. Orphan entity cleanup
10. Write audit log entry

---

## 🏛 The Six Pillars

### 1. INGEST — Passive Capture

Four ingestors silently collect digital exhaust:

| Ingestor | Source | Mechanism |
|----------|--------|-----------|
| `FilesystemIngestor` | Watched directories | `watchdog` file events |
| `BrowserIngestor` | Browser history DBs | Periodic polling (300s) |
| `TerminalIngestor` | Shell history files | Periodic polling (120s) |
| `ClipboardIngestor` | System clipboard | Periodic polling (30s) |

All ingestors push to a `PriorityQueue` (max depth 500). Backpressure drops oldest items.

### 2. PARSE — Universal Normalization

The `ParserDispatcher` routes to content-type-specific parsers:

| Parser | Content Types | Strategy |
|--------|--------------|----------|
| `PlainParser` | `.txt`, `.log`, `.csv` | Encoding detection + text extraction |
| `MarkdownParser` | `.md`, `.mdx` | `markdown-it-py` with metadata extraction |
| `HTMLParser` | `.html`, `.htm` | `readability-lxml` content extraction |
| `EmailParser` | `.eml`, `.msg` | Header parsing + body extraction |
| `PDFParser` | `.pdf` | `pdfminer.six` text extraction |
| `CodeParser` | 30+ languages | 3-strategy tree-sitter fallback |

### 3. INDEX — Multi-Store Indexing

Documents pass through three parallel indexing paths:

- **Vector Index**: Chunks → `nomic-embed-text` → ChromaDB (HNSW cosine)
- **Full-Text Index**: Chunks → SQLite FTS5 (BM25 ranking)
- **Graph Index**: Entities → KuzuDB (Cypher graph)

### 4. RECALL — Hybrid Retrieval

Four-signal weighted fusion (weights from `retrieval_weights.toml`):

| Signal | Weight | Source |
|--------|--------|--------|
| Vector similarity | 0.40 | ChromaDB cosine |
| Keyword (BM25) | 0.30 | SQLite FTS5 |
| Graph traversal | 0.20 | KuzuDB entity neighborhood |
| Temporal decay | 0.10 | `exp(-0.005 × age_days)` |

### 5. ANSWER — RAG Chat Engine

- Retrieves top-k chunks via `HybridRetriever`
- Builds a context-windowed prompt with `[Source N]` citation enforcement
- Streams responses via SSE
- Maintains conversation history (last 6 turns)
- Model: `llama3:8b` via Ollama

### 6. PROTECT — Privacy Layer

- **Redactor**: Strips secrets before storage (7 regex + entropy)
- **ForgetManager**: 10-step atomic hard-forget across all stores
- **PurgeScheduler**: TTL-based raw content purge (7 days)
- **AuditLog**: Every forget operation is recorded

---

## 🔍 Retrieval Engine

### Score Fusion Formula

```
combined_score = (0.40 × vector) + (0.30 × keyword) + (0.20 × graph) + (0.10 × temporal)
```

**Invariant**: `0.40 + 0.30 + 0.20 + 0.10 = 1.0` (verified by `test_config_hygiene.py`)

### Temporal Decay

```python
temporal_score = math.exp(-0.005 * age_days)
```

| Age | Score |
|-----|-------|
| Today | 1.000 |
| 1 week | 0.997 |
| 1 month | 0.986 |
| 3 months | 0.963 |
| 6 months | 0.928 |
| 1 year | 0.861 |
| 2 years | 0.741 |

### Default Limits

| Parameter | Value |
|-----------|-------|
| `default_top_k` | 20 candidates |
| `max_top_k` | 50 (hard ceiling) |
| `context_window` | 6,000 tokens |
| `conversation_history` | 6 turns |

---

## 🧪 Invariants

30 invariant tests (`INV-001` through `INV-030`) enforce critical system properties:

| Category | Invariants |
|----------|-----------|
| **Security** | Loopback-only enforcement, no remote connections, correct middleware rejection |
| **Redaction** | All 7 patterns redact correctly, innocuous text preserved, entropy heuristic works |
| **Forget** | All stores cleared, audit log written, orphan cleanup |
| **Retrieval** | Weight sum = 1.0, temporal decay ∈ [0,1], score ordering |
| **Ingestion** | Queue depth limits, deduplication by checksum, priority ordering |
| **Config Hygiene** | All addenda parse, no duplicate values, all referenced files exist |

Run them:

```bash
pytest tests/invariants/ -v
```

---

## 🐳 Docker Deployment

### Quick Start

```bash
docker compose up -d
```

### Configuration

The `docker-compose.yml`:

- Binds to **localhost only** (`127.0.0.1:7700:7700`)
- Mounts `~/Documents` and `~/Projects` as read-only watched paths
- Resource limits: 4 GB RAM, 2 CPUs
- Health check every 30s
- Named volume for persistent data (`memex-data`)

### Environment

```yaml
environment:
  - MEMEX_DATA_DIR=/home/memex/.memex
  - MEMEX_LOG_LEVEL=INFO
  - OLLAMA_HOST=127.0.0.1:11434
```

### Building

The multi-stage `Dockerfile`:

1. **Builder stage**: Installs dependencies with `build-essential`
2. **Runtime stage**: Minimal `python:3.13-slim` with Ollama bundled
3. **Entrypoint**: Starts Ollama, pulls models, then launches MEMEX daemon

---

## 🛠 Development

### Setup

```bash
git clone https://github.com/knarayanareddy/MEMEX.git
cd MEMEX
pip install -e ".[dev]"
```

### Code Quality

```bash
# Lint
ruff check memex/ tests/

# Type check
mypy memex/ --ignore-missing-imports

# Format
ruff format memex/ tests/
```

### CI Pipeline (GitHub Actions)

4-stage pipeline, all must pass:

| Stage | What it runs |
|-------|-------------|
| 1. Static Analysis | `ruff check`, `mypy`, config hygiene invariants |
| 2. Unit Tests | Parser, chunker, redactor, SQLite, prompt tests |
| 3. Integration + Invariants | Full pipeline test, API endpoint tests, all 30 invariants |
| 4. Coverage | Full suite with `--cov=memex`, coverage upload |

---

## 🧪 Testing

### Test Structure

```
tests/
├── conftest.py                  # Shared fixtures (ephemeral SQLite, etc.)
├── invariants/                  # 30 blocking invariant tests (INV-001 to INV-030)
│   ├── test_security.py         # Network, middleware, loopback
│   ├── test_redaction.py        # Secret patterns, entropy, excluded domains
│   ├── test_forget.py           # 10-step protocol verification
│   ├── test_retrieval.py        # Weights, decay, fusion
│   ├── test_ingestion.py        # Queue, dedup, priority
│   └── test_config_hygiene.py   # SSOT validation
├── unit/                        # Isolated component tests
│   ├── test_parsers.py          # All 6 parsers
│   ├── test_chunker.py          # Smart chunker with content types
│   ├── test_redactor.py         # Pattern + entropy tests
│   ├── test_sqlite.py           # Schema, FTS5, migrations
│   ├── test_prompt.py           # Citation extraction
│   └── test_production_fixes.py # Regression tests
└── integration/                 # End-to-end pipeline tests
    ├── test_pipeline.py         # Full ingest→parse→index→recall
    └── test_api.py              # FastAPI endpoint tests
```

### Running Tests

```bash
# All tests
pytest tests/ -v

# Invariant tests only
pytest tests/ -m invariant -v

# Unit tests only
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# With coverage
pytest tests/ --cov=memex --cov-report=term-missing

# Specific test
pytest tests/invariants/test_redaction.py::test_openai_key_redacted -v
```

### Test Markers

| Marker | Purpose |
|--------|---------|
| `@pytest.mark.invariant` | Blocking invariant test |
| `@pytest.mark.integration` | Integration test |
| `@pytest.mark.perf` | Performance benchmark |

---

## 📁 Project Structure

```
MEMEX/
├── README.md                         # This file
├── CHANGELOG.md                      # Version history
├── CONTRIBUTING.md                   # Contribution guidelines
├── ARCHITECTURE.md                   # Detailed architecture docs
├── SECURITY.md                       # Security policy
├── LICENSE                           # MIT License
├── pyproject.toml                    # Package config, dependencies
├── Dockerfile                        # Multi-stage container build
├── docker-compose.yml                # Local deployment config
│
├── .github/
│   └── workflows/
│       └── ci.yml                    # 4-stage CI pipeline
│
├── memex/                            # Main package
│   ├── __init__.py                   # Version: 2.0.0
│   ├── __main__.py                   # CLI (init, doctor, start, chat, status)
│   ├── daemon.py                     # Daemon orchestrator with drain shutdown
│   │
│   ├── config/                       # Configuration (SSOT)
│   │   ├── settings.py               # Settings dataclass, addenda loaders
│   │   ├── default_config.toml       # User-facing config template
│   │   ├── retrieval_weights.toml    # Addendum A: retrieval constants
│   │   ├── retention.toml            # Addendum B: retention TTLs
│   │   ├── chunking.toml             # Addendum C: token budgets
│   │   ├── redaction_patterns.toml   # Addendum D: secret patterns
│   │   └── slos.toml                 # Addendum F: SLO targets
│   │
│   ├── ingest/                       # INGEST pillar
│   │   ├── base.py                   # BaseIngestor ABC
│   │   ├── queue.py                  # PriorityQueue with backpressure
│   │   ├── filesystem.py             # Watchdog-based file watcher
│   │   ├── browser.py                # Browser history ingestor
│   │   ├── terminal.py               # Shell history ingestor
│   │   └── clipboard.py              # Clipboard ingestor
│   │
│   ├── parse/                        # PARSE pillar
│   │   ├── base.py                   # BaseParser ABC
│   │   ├── dispatcher.py             # Content-type routing
│   │   ├── plain_parser.py           # Plain text
│   │   ├── markdown_parser.py        # Markdown
│   │   ├── html_parser.py            # HTML
│   │   ├── email_parser.py           # Email
│   │   ├── pdf_parser.py             # PDF
│   │   └── code_parser.py            # Code (tree-sitter fallback)
│   │
│   ├── index/                        # INDEX pillar
│   │   ├── chunker.py                # SmartChunker (content-aware budgets)
│   │   ├── embedder.py               # Ollama embedder (nomic-embed-text)
│   │   ├── graph_extractor.py        # Entity/relationship extraction
│   │   └── migration.py              # Model migration worker
│   │
│   ├── recall/                       # RECALL pillar
│   │   └── hybrid_retrieval.py       # 4-signal fusion retrieval
│   │
│   ├── answer/                       # ANSWER pillar
│   │   ├── chat.py                   # RAG chat engine
│   │   └── prompt.py                 # System prompt with citation enforcement
│   │
│   ├── protect/                      # PROTECT pillar
│   │   ├── redactor.py               # Secret redaction (7 patterns + entropy)
│   │   ├── forget.py                 # 10-step atomic forget protocol
│   │   └── purge.py                  # TTL-based purge scheduler
│   │
│   ├── db/                           # Storage layer
│   │   ├── sqlite.py                 # SQLite (WAL, connection pool, FTS5)
│   │   ├── chroma.py                 # ChromaDB (HNSW cosine)
│   │   ├── kuzu.py                   # KuzuDB (Cypher graph)
│   │   └── migrations/
│   │       ├── runner.py             # Alembic-style migration runner
│   │       ├── 001_initial.sql       # Full schema (12 tables)
│   │       └── 002_add_retry_columns.sql
│   │
│   ├── api/                          # REST API
│   │   ├── app.py                    # FastAPI factory with lifespan
│   │   ├── middleware.py             # LoopbackOnly, RequestTiming
│   │   ├── models.py                 # Pydantic request/response models
│   │   └── routes/
│   │       ├── memory.py             # Search, timeline, forget
│   │       ├── chat.py               # Chat, SSE stream, sessions
│   │       ├── graph.py              # Entity/relation queries
│   │       └── system.py             # Health, stats, reindex, logs
│   │
│   ├── observability/                # Monitoring
│   │   ├── logging.py                # Structured logging with Timer
│   │   ├── metrics.py                # MetricsCollector (p50/p95/p99)
│   │   └── slos.py                   # SLO monitor with timers
│   │
│   ├── tui/                          # Terminal UI
│   │   └── app.py                    # Textual TUI chat interface
│   │
│   └── web/                          # Web UI
│       └── static/
│           ├── index.html            # SPA shell
│           ├── style.css             # Dark theme
│           └── app.js                # Chat, Search, Timeline, Graph views
│
└── tests/                            # Test suite (150 tests)
    ├── conftest.py
    ├── invariants/                   # 30 invariant tests
    ├── unit/                         # Component tests
    └── integration/                  # End-to-end tests
```

**75 Python files · ~9,500 lines of code · 150 passing tests**

---

## 📋 Configuration Addenda (SSOT)

All operational constants live in versioned TOML files. These are the **Single Source of Truth** — never duplicate values in code.

### Addendum A — Retrieval Weights (`retrieval_weights.toml`)

| Parameter | Value |
|-----------|-------|
| `vector_weight` | 0.40 |
| `keyword_weight` | 0.30 |
| `graph_weight` | 0.20 |
| `temporal_weight` | 0.10 |
| `lambda` (temporal decay) | 0.005 |
| `default_top_k` | 20 |
| `max_top_k` | 50 |
| `relation_confidence_threshold` | 0.50 |

### Addendum B — Retention (`retention.toml`)

| Parameter | Value |
|-----------|-------|
| `raw_content purge_after_days` | 7 |
| `conversation retain_turns_days` | 365 |
| `failed_docs max_retry_count` | 5 |
| `queue max_depth` | 500 |
| `queue warn_threshold` | 400 |
| `purge run_interval_minutes` | 60 |
| `parser timeout_seconds` | 30 |

### Addendum C — Chunking (`chunking.toml`)

| Content Type | Token Budget | Overlap |
|-------------|-------------|---------|
| Prose | 400 | 50 |
| Code | 300 | 30 |
| Email | 200 | 20 |
| PDF | 400 | 50 |
| Image OCR | 150 | 0 |

### Addendum D — Redaction Patterns (`redaction_patterns.toml`)

7 regex patterns + Shannon entropy heuristic:
- **Entropy threshold**: 4.5
- **Min string length**: 20
- **Context window**: 30 chars around matches

22 excluded browser domains (banking, password managers, SSO, email, health, messaging).

### Addendum F — SLO Targets (`slos.toml`)

See [SLO Targets](#-slo-targets) section.

---

## 📊 SLO Targets

| SLO | Metric | Target | Alert Threshold |
|-----|--------|--------|----------------|
| SLO-001 | Idle CPU % | ≤ 1% | > 5% |
| SLO-002 | FTS search p95 latency | ≤ 50 ms | > 200 ms |
| SLO-003 | Vector search p95 latency | ≤ 200 ms | > 500 ms |
| SLO-004 | Hybrid retrieval p95 latency | ≤ 500 ms | > 1000 ms |
| SLO-005 | LLM first token p50 latency | ≤ 3000 ms | > 10000 ms |
| SLO-006 | Ingestion avg time (CPU) | ≤ 30,000 ms | > 120,000 ms |
| SLO-007 | Ingestion avg time (GPU) | ≤ 10,000 ms | > 30,000 ms |
| SLO-010 | Forget single doc latency | ≤ 5000 ms | > 30,000 ms |

---

## 🔧 Troubleshooting

### Common Issues

| Problem | Solution |
|---------|----------|
| `memex: command not found` | Run `pip install -e .` from project root |
| Ollama not reachable | Start with `ollama serve` |
| Missing models | Run `ollama pull nomic-embed-text` and `ollama pull llama3:8b` |
| Port 7700 in use | Change `api_port` in `~/.memex/config.toml` |
| Permission denied | `chmod 700 ~/.memex` |
| Slow embedding | Ensure Ollama has enough RAM (~4 GB for llama3:8b) |
| Docker build fails | Ensure Docker has ≥4 GB memory allocated |

### Debug Mode

```bash
# Enable verbose logging
MEMEX_LOG_LEVEL=DEBUG memex start

# Or set in config
[daemon]
log_level = "DEBUG"
```

### Health Check

```bash
memex doctor     # CLI health check
curl http://localhost:7700/api/health   # API health check
memex status     # Remote health check
```

---

## 📜 License

MIT License — see [LICENSE](./LICENSE) file.

---

<p align="center">
  <strong>MEMEX</strong> — Your data. Your machine. Your memory.<br/>
  <em>Built with Python, SQLite, ChromaDB, KuzuDB, Ollama, FastAPI, and Textual.</em>
</p>
