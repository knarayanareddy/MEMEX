# MEMEX Engineering Design Document

---

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 DOCUMENT CONTROL BLOCK — SINGLE SOURCE OF TRUTH
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Title         : MEMEX — Local-First Passive Second Brain
 Version       : 2.0.0
 Status        : APPROVED — Single Source of Truth
 Last Updated  : 2026-06-11
 Authors       : knarayanareddy
 Deployment    : Local / On-Device Only
 Jurisdiction  : No regulatory jurisdiction (single-user, local-only)
 Locale        : en-US

 CANONICAL ADDENDA (these override all inline examples)
   Addendum A  : Retrieval Weight Constants
   Addendum B  : Retention & Purge Day Values
   Addendum C  : Chunk Token Budget Constants
   Addendum D  : Secret Redaction Pattern Registry
   Addendum E  : Testable Invariant Harness
   Addendum F  : SLO Definitions & Alert Thresholds
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 ⚠️  WARNING: Any constant, weight, regex, or threshold value
 that appears in the body of this document is ILLUSTRATIVE ONLY.
 The canonical values live exclusively in the Addenda above.
 All code, config, and tests MUST import from those addenda.
 Any PR that hard-codes a value from Addendum A–F into source
 code will be rejected at CI.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Table of Contents

1. [Product Vision & Scope](#1-product-vision--scope)
2. [System Pillars](#2-system-pillars)
3. [C4 Architecture](#3-c4-architecture)
4. [Architecture Decision Records (ADRs)](#4-architecture-decision-records-adrs)
5. [Trust Model & Privacy Posture](#5-trust-model--privacy-posture)
6. [Pillar I — INGEST (Passive Capture)](#6-pillar-i--ingest-passive-capture)
7. [Pillar II — PARSE (Universal Normalization)](#7-pillar-ii--parse-universal-normalization)
8. [Pillar III — INDEX (Embed + Graph + FTS)](#8-pillar-iii--index-embed--graph--fts)
9. [Pillar IV — RECALL (Hybrid Retrieval)](#9-pillar-iv--recall-hybrid-retrieval)
10. [Pillar V — ANSWER (Conversation + Citations)](#10-pillar-v--answer-conversation--citations)
11. [Pillar VI — PROTECT (Privacy, Redaction, Forget)](#11-pillar-vi--protect-privacy-redaction-forget)
12. [Data Model](#12-data-model)
13. [Local REST API Surface](#13-local-rest-api-surface)
14. [Failure Modes & Backpressure](#14-failure-modes--backpressure)
15. [Model Versioning & Re-Embed Migration](#15-model-versioning--re-embed-migration)
16. [Observability & Local Telemetry](#16-observability--local-telemetry)
17. [Performance SLOs](#17-performance-slos)
18. [Testable Invariants & CI Gates](#18-testable-invariants--ci-gates)
19. [Canonical Addenda](#19-canonical-addenda)
20. [Glossary](#20-glossary)

---

## 1. Product Vision & Scope

### 1.1 What MEMEX Is

MEMEX is a **local-first, privacy-preserving, self-building second brain** that passively ingests a user's digital exhaust — browser history, files, terminal sessions, email, screenshots, clipboard, calendar — and makes it all queryable through a **chat interface with strict source citations**. No data leaves the device. No cloud account is required. No manual curation is needed.

The core philosophical bet:

> **You should not have to curate your memory. MEMEX inverts the standard workflow — instead of "write notes, tag things, build a PKM system," MEMEX watches what you already do and builds the structure automatically.**

### 1.2 What MEMEX Is Not

| Not this | Why it matters |
|---|---|
| A cloud sync tool | All data stays on-device by design |
| A replacement for git/Notion/Obsidian | It indexes those, it doesn't replace them |
| A real-time assistant | Retrieval latency is acceptable at hundreds of ms |
| A multi-user system | Single OS user, single trust boundary |
| A compliance artifact | No GDPR/HIPAA burden; no regulatory overhead |

### 1.3 MVP Scope

| Pillar | MVP Feature |
|---|---|
| INGEST | Filesystem, browser history, clipboard, terminal |
| PARSE | Plain text, markdown, PDF, HTML, code |
| INDEX | Embeddings (Chroma), FTS (SQLite FTS5), entity graph (Kuzu) |
| RECALL | Hybrid retrieval: vector + keyword + graph + temporal |
| ANSWER | Local LLM chat with `[Source N]` citations, TUI + Web UI |
| PROTECT | Localhost-only API, secret redaction, hard delete across all stores |

**Phase 2 (post-MVP):**
- IMAP / email ingestion
- Screenshot OCR ingestion
- Calendar ingestion
- Graph visualization (D3)
- Chrome/Firefox extension for in-browser capture (replaces HTTP re-fetch)

---

## 2. System Pillars

MEMEX is decomposed into six named pillars. Every component, table, API route, and test maps to exactly one pillar.

```
┌─────────────────────────────────────────────────────────────┐
│                        MEMEX PILLARS                        │
├──────────┬──────────┬──────────┬──────────┬────────┬────────┤
│  INGEST  │  PARSE   │  INDEX   │  RECALL  │ ANSWER │PROTECT │
│          │          │          │          │        │        │
│ Passive  │Universal │Embed +   │Hybrid    │Chat +  │Privacy,│
│ capture  │normaliz- │Graph +   │4-signal  │Citati- │Redact, │
│ daemon   │ation     │FTS       │retrieval │ons     │Forget  │
└──────────┴──────────┴──────────┴──────────┴────────┴────────┘
```

| Pillar | Primary responsibility | Key stores touched |
|---|---|---|
| **INGEST** | Source watching, event dedup, queue management | Raw queue, SQLite `documents` |
| **PARSE** | Content-type detection, text extraction, clean text | SQLite `documents.clean_content` |
| **INDEX** | Chunking, embedding, NER/relations, FTS update | Chroma, Kuzu, SQLite `chunks`, `entities`, FTS |
| **RECALL** | Hybrid retrieval, score fusion, time filtering | Chroma, SQLite FTS5, Kuzu, SQLite `documents` |
| **ANSWER** | Context budgeting, prompt construction, citation rendering | SQLite `conversations` |
| **PROTECT** | Redaction, localhost enforcement, forget propagation | All stores |

---

## 3. C4 Architecture

### 3.1 Level 1 — System Context

```
┌─────────────────────────────────────────────────────────────────┐
│                        OS USER SESSION                          │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ Browser  │  │Filesystem│  │ Terminal │  │Email/Calendar │  │
│  │ History  │  │(watched) │  │ history  │  │   (IMAP/ical) │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └───────┬───────┘  │
│       │              │              │                │          │
│       └──────────────┴──────────────┴────────────────┘         │
│                              │                                  │
│                              ▼                                  │
│                     ┌─────────────────┐                        │
│                     │   MEMEX DAEMON  │◄── config.toml          │
│                     │  (background)   │                        │
│                     └────────┬────────┘                        │
│                              │                                  │
│              ┌───────────────┼───────────────┐                 │
│              ▼               ▼               ▼                 │
│       ┌────────────┐  ┌────────────┐  ┌────────────┐          │
│       │  SQLite DB │  │  ChromaDB  │  │  KuzuDB    │          │
│       │ (relational│  │  (vectors) │  │  (graph)   │          │
│       │   + FTS5)  │  │            │  │            │          │
│       └────────────┘  └────────────┘  └────────────┘          │
│              │               │               │                 │
│              └───────────────┼───────────────┘                 │
│                              │                                  │
│                     ┌────────┴────────┐                        │
│                     │  Local REST API │ localhost:7700 only     │
│                     │  (FastAPI)      │                        │
│                     └────────┬────────┘                        │
│                              │                                  │
│              ┌───────────────┴───────────────┐                 │
│              ▼                               ▼                 │
│       ┌────────────┐                  ┌────────────┐           │
│       │  TUI       │                  │  Web UI    │           │
│       │ (Textual)  │                  │ (localhost)│           │
│       └────────────┘                  └────────────┘           │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    OLLAMA (local)                        │  │
│  │   nomic-embed-text (embeddings) + llama3:8b (chat)       │  │
│  │   Bound to localhost. No external calls.                 │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

> **No arrows cross the OS boundary.** All data flows are intra-device.

---

### 3.2 Level 2 — Container Diagram (MEMEX Daemon internals)

```
┌──────────────────────────── MEMEX DAEMON ───────────────────────────────┐
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                      INGESTOR THREADS                            │   │
│  │  ┌───────────┐ ┌───────────┐ ┌──────────┐ ┌──────────────────┐  │   │
│  │  │ Filesystem│ │  Browser  │ │ Terminal │ │ Clipboard/Email/ │  │   │
│  │  │  Watcher  │ │  Poller   │ │  Poller  │ │ Calendar Pollers │  │   │
│  │  └─────┬─────┘ └─────┬─────┘ └─────┬────┘ └────────┬─────────┘  │   │
│  └────────┼─────────────┼─────────────┼───────────────┼────────────┘   │
│           └─────────────┴──────┬───────┘               │               │
│                                ▼                        │               │
│                    ┌───────────────────────┐            │               │
│                    │   PRIORITY QUEUE      │◄───────────┘               │
│                    │  (RawDocument items)  │                            │
│                    │  max_depth: see ADR-6 │                            │
│                    └──────────┬────────────┘                            │
│                               │                                         │
│                    ┌──────────▼────────────┐                            │
│                    │   WORKER POOL         │                            │
│                    │  (N threads, bounded) │                            │
│                    └──────────┬────────────┘                            │
│                               │                                         │
│         ┌─────────────────────┼──────────────────────────┐             │
│         ▼                     ▼                          ▼             │
│  ┌─────────────┐    ┌──────────────────┐    ┌────────────────────┐     │
│  │   PARSER    │    │  CHUNKER         │    │  GRAPH EXTRACTOR   │     │
│  │ (by content │    │ (content-aware   │    │  (spaCy NER +      │     │
│  │  type)      │    │  token budgets)  │    │   LLM relations)   │     │
│  └──────┬──────┘    └────────┬─────────┘    └──────────┬─────────┘     │
│         │                   │                          │               │
│         ▼                   ▼                          ▼               │
│  ┌─────────────┐    ┌──────────────────┐    ┌────────────────────┐     │
│  │  REDACTOR   │    │  EMBEDDER        │    │  KUZU WRITER       │     │
│  │  (pre-store │    │  (Ollama local)  │    │  (entities +       │     │
│  │   secrets)  │    │  → Chroma        │    │   relations)       │     │
│  └──────┬──────┘    └────────┬─────────┘    └──────────┬─────────┘     │
│         └───────────────────┴──────────────────────────┘               │
│                                      │                                  │
│                                      ▼                                  │
│                           ┌─────────────────────┐                      │
│                           │  SQLITE WRITER      │                      │
│                           │  (FTS trigger +     │                      │
│                           │   metadata update)  │                      │
│                           └─────────────────────┘                      │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Architecture Decision Records (ADRs)

Each ADR follows the format: **Context → Forces → Decision → Consequences → Status.**

---

### ADR-001: ChromaDB as Vector Store

**Context:** MEMEX needs a persistent local vector store for chunk embeddings.

**Forces:**
- Must run fully on-device with no server process or cloud dependency
- Must support cosine similarity + metadata filtering
- Must be embeddable in Python without a separate daemon
- Must support persistent collections across restarts

**Candidates considered:** Qdrant (local mode), Weaviate (local Docker), LanceDB, ChromaDB, FAISS (flat file).

**Decision:** ChromaDB with `PersistentClient` and HNSW cosine space.

**Consequences:**
- ✅ Zero-server, embedded Python client
- ✅ HNSW index gives sub-200ms search at 1M chunks (see Addendum F)
- ✅ Supports `where` metadata filter for time-scoped retrieval
- ⚠️ No built-in encryption at rest (mitigated by OS-level disk encryption guidance)
- ⚠️ No native BM25; FTS handled by SQLite FTS5 separately

**Status:** APPROVED

---

### ADR-002: KuzuDB as Graph Store

**Context:** Entity relationships extracted from documents need a queryable graph layer.

**Forces:**
- Must be embeddable (no separate server process)
- Must support Cypher-like query syntax for graph traversal
- Must be writable from Python
- Must handle delete propagation (when a document is forgotten)

**Candidates considered:** Neo4j (server), SQLite adjacency tables (hand-rolled), NetworkX (in-memory only), KuzuDB.

**Decision:** KuzuDB embedded graph database.

**Consequences:**
- ✅ Embedded, no server
- ✅ Cypher query language for entity neighborhood traversal
- ✅ Persistent on disk
- ⚠️ Smaller ecosystem than Neo4j; less community tooling
- ⚠️ Delete propagation must be explicitly implemented (see §11)

**Status:** APPROVED

---

### ADR-003: SQLite as Relational + FTS Layer

**Context:** MEMEX needs a relational store for document metadata, chunk records, conversation history, and full-text search.

**Forces:**
- Must be single-file, zero-server
- Must support FTS (BM25) natively
- Must support WAL mode for concurrent reads during ingestion
- Must be portable (single file = easy backup)

**Candidates considered:** DuckDB (OLAP-optimised, less suited for concurrent writes), PostgreSQL (server required), SQLite.

**Decision:** SQLite with WAL mode, FTS5 virtual tables, and indexed columns.

**Consequences:**
- ✅ Single file, zero-server, WAL mode for concurrent read/write
- ✅ FTS5 with BM25 ranking built in
- ✅ Triggers keep FTS tables in sync automatically
- ⚠️ Write concurrency limited (single writer); mitigated by worker pool serialization through a write queue
- ⚠️ No column-level encryption (raw content exposure risk: see §5)

**Status:** APPROVED

---

### ADR-004: Ollama for Local Inference (Embeddings + Chat)

**Context:** MEMEX requires both embedding generation and chat completion, with a hard constraint that no user data leaves the device.

**Forces:**
- Embeddings must be generated locally
- Chat completions must be generated locally
- Must support model swapping without code changes
- Must expose a consistent HTTP API

**Candidates considered:** llama.cpp direct (lower level, more portable), Ollama, LM Studio (GUI-only), ctransformers.

**Decision:** Ollama bound to `localhost` only, with `nomic-embed-text` for embeddings and `llama3:8b` as the default chat model. Model names are config-driven.

**Consequences:**
- ✅ Zero external calls; all inference local
- ✅ Model swap via config change, no code change
- ✅ HTTP API allows future language-agnostic clients
- ⚠️ Ollama must be running before daemon starts; daemon must handle `OllamaUnavailable` gracefully (see §14)
- ⚠️ Model upgrades invalidate existing embeddings; migration strategy required (see §15)

**Status:** APPROVED

---

### ADR-005: nomic-embed-text as Default Embedding Model

**Context:** A specific embedding model must be chosen as the default for Chroma collections.

**Forces:**
- High retrieval quality on mixed-content corpora (prose + code + email)
- Runs comfortably on CPU (no GPU required for MVP)
- Context window large enough for chunks (see Addendum C)
- Actively maintained and available via Ollama

**Candidates considered:** `mxbai-embed-large`, `all-minilm`, `bge-m3`, `nomic-embed-text`.

**Decision:** `nomic-embed-text` v1.5 as default; model name stored in `embed_model_registry` table so migrations are trackable (see §15).

**Consequences:**
- ✅ Strong quality-to-size ratio; works on CPU
- ✅ Model name is config-driven and version-tracked
- ⚠️ If model is upgraded, full re-embed required; see §15 for migration protocol

**Status:** APPROVED

---

### ADR-006: Priority Queue with Bounded Depth for Ingestion

**Context:** The ingestion daemon needs a queue between ingestors and workers.

**Forces:**
- Ingestors can burst (e.g., mounting a large filesystem)
- Workers should not be overwhelmed
- Memory usage must be bounded
- High-priority sources (clipboard, terminal) should not be starved by bulk filesystem events

**Decision:** A `PriorityQueue` with configurable `max_depth` (canonical value: see Addendum B). Priority tiers: `CRITICAL` (crisis/clipboard) > `HIGH` (terminal, email) > `NORMAL` (filesystem, browser) > `LOW` (bulk re-index).

**Consequences:**
- ✅ Bounded memory regardless of burst size
- ✅ Priority tiers ensure interactive sources are responsive
- ⚠️ When queue is full, new items are DROPPED with a structured log entry (not silently ignored)
- ⚠️ Queue depth must be surfaced in `/health` endpoint and local telemetry

**Status:** APPROVED

---

### ADR-007: pdfminer.six for PDF Extraction

**Context:** PDF parsing is required. Library choice affects extraction quality, license, and dependency weight.

**Forces:**
- Must extract text with layout awareness (columns, headers)
- Must handle encrypted PDFs gracefully (skip, not crash)
- Must be pure Python (no system binary dependency)
- Must be actively maintained

**Candidates considered:** PyMuPDF (AGPL license risk), pypdf (simpler but lower quality), pdfplumber (good but heavier), pdfminer.six.

**Decision:** `pdfminer.six`.

**Consequences:**
- ✅ Pure Python, MIT-compatible license
- ✅ Good layout analysis for multi-column documents
- ⚠️ Slower than PyMuPDF on large files; mitigated by async worker model
- ⚠️ Scanned PDFs (image-only) return empty text; fallback to OCR pipeline required (Phase 2)

**Status:** APPROVED

---

### ADR-008: pgvector vs. Chroma (Why Not pgvector?)

**Context:** HAVEN uses pgvector inside Postgres. Should MEMEX do the same?

**Forces:**
- MEMEX has no existing Postgres instance (local-only, no server)
- pgvector requires a running Postgres server
- SQLite is already the relational store

**Decision:** Chroma (embedded) for vectors, not pgvector. This is explicitly not a HAVEN pattern that transfers to MEMEX.

**Consequences:**
- ✅ No server process required
- ✅ Consistent with local-first constraint
- ⚠️ Two separate stores (SQLite + Chroma) must be kept consistent; delete propagation is a hard requirement

**Status:** APPROVED

---

## 5. Trust Model & Privacy Posture

### 5.1 Trust Zones

```
┌──────────────────────────────────────────────────────┐
│  ZONE 1: FULLY TRUSTED (read + write)                │
│  - MEMEX daemon process                              │
│  - SQLite, Chroma, Kuzu (local files)                │
│  - Ollama (localhost only)                           │
│  - FastAPI (localhost:7700 only)                     │
│  - TUI and Web UI (same OS user session)             │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│  ZONE 2: SEMI-TRUSTED (read-only observation)        │
│  - Browser SQLite history DB (read-only open)        │
│  - Filesystem (read-only ingestor)                   │
│  - Terminal history file (read-only)                 │
│  - IMAP (read-only, no send)                         │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│  ZONE 3: UNTRUSTED (no user data transmitted)        │
│  - Internet / any external service                   │
│  - Any non-localhost network interface               │
└──────────────────────────────────────────────────────┘
```

### 5.2 Hard Security Rules

These are not guidelines — they are enforced by code and verified by CI:

| Rule | Enforcement mechanism |
|---|---|
| API never binds to non-loopback | FastAPI middleware rejects non-127.0.0.1 source IPs; CI test asserts this |
| Ollama never contacts external endpoints | Ollama config `OLLAMA_HOST=127.0.0.1`; network mock test asserts no external calls |
| Secret patterns are redacted before storage | Redactor runs post-parse, pre-chunk; CI unit tests verify known patterns are stripped |
| Hard delete propagates to all stores | Forget function deletes SQLite + Chroma + Kuzu + FTS atomically; CI integration test verifies |
| Raw content is purged on schedule | pg_cron equivalent: a scheduled local job nulls `raw_content` after N days (canonical: Addendum B) |
| Browser fetcher excluded domains are enforced | Excluded domain list verified by unit test; test asserts known sensitive domains are in default list |

### 5.3 Threat Model (Scoped)

| Threat | In scope? | Mitigation |
|---|---|---|
| Another OS user reading MEMEX data | ✅ | OS file permissions (chmod 700 on data dir) |
| Process on same machine sniffing localhost API | ✅ | Localhost-only bind; no auth token needed beyond OS user boundary |
| MEMEX daemon leaking data externally | ✅ | No outbound calls; Ollama localhost only; CI network mock |
| Stolen laptop / disk image | ⚠️ Partial | OS-level disk encryption (FileVault/LUKS) REQUIRED; documented in setup guide; MEMEX does not implement its own encryption |
| Browser re-fetch capturing auth-gated pages | ✅ | Excluded domains config; HTTP-only fetch (no cookie forwarding); raw content TTL |
| SQL injection via chat input | ✅ | All SQLite queries use parameterized statements; no string interpolation |
| Hallucinated citations | ✅ | Prompt template mandates citation-only answers; CI eval test |

### 5.4 Encryption at Rest

**MEMEX does not implement its own encryption at rest.** This is a deliberate scope decision. The setup guide MUST instruct users to enable OS-level disk encryption before using MEMEX. This must be verified in onboarding (`memex doctor` command checks for OS encryption status and warns if disabled).

---

## 6. Pillar I — INGEST (Passive Capture)

### 6.1 Ingestor Registry

| Source | Strategy | Cadence | Priority tier | Phase |
|---|---|---|---|---|
| Filesystem | OS watcher (`watchdog`) | Event-driven | NORMAL | MVP |
| Browser history | Poll browser SQLite DB | Every 5 min | NORMAL | MVP |
| Terminal history | Poll `~/.zsh_history` / `~/.bash_history` | On command / 2 min | HIGH | MVP |
| Clipboard | Poll `pyperclip` | Every 30 sec | CRITICAL | MVP |
| IMAP email | IDLE + periodic poll | Every 10 min | HIGH | Phase 2 |
| Calendar | Poll `.ics` / CalDAV | Every 30 min | LOW | Phase 2 |
| Screenshots | Directory watcher | Event-driven | NORMAL | Phase 2 |

### 6.2 RawDocument Contract

Every ingestor emits a `RawDocument`. This is the canonical interface between INGEST and PARSE:

```python
@dataclass
class RawDocument:
    source_type: str          # "filesystem" | "browser" | "terminal" | ...
    source_path: str          # URI or file path
    raw_bytes: bytes          # Original bytes before any processing
    encoding: str             # Detected or declared encoding
    captured_at: datetime     # When the ingestor captured this
    source_metadata: dict     # Source-specific extras (browser: url, title; email: from, subject)
    checksum: str             # SHA-256 of raw_bytes (dedup key)
    priority: Priority        # CRITICAL | HIGH | NORMAL | LOW
```

### 6.3 Dedup Logic

Before any item enters the processing pipeline:

```
1. Compute SHA-256 of raw_bytes
2. Query SQLite: SELECT id FROM documents WHERE checksum = ?
3a. If found AND checksum matches stored checksum → SKIP (already indexed, unchanged)
3b. If found AND checksum differs → MARK for re-index (delete old chunks/vectors first)
3c. If not found → PROCEED to parse pipeline
```

This prevents redundant embedding on re-ingestion of unchanged files.

### 6.4 Browser Ingestor Trust Boundary

The browser ingestor is the highest-risk ingestor because it may fetch live pages via HTTP. The following rules are **canonical and enforced**:

#### Fetch Policy
- The ingestor reads the **browser's local SQLite history DB** (Chrome: `History`, Firefox: `places.sqlite`) to get `(url, title, visit_time)` tuples. It does **not** read cached page content from the browser cache.
- For URLs that are `http://` or `https://`, the ingestor **optionally** fetches the live page to extract body text. This is **opt-in** via `config.toml: browser.fetch_page_content = false` (default: `false`).
- When `fetch_page_content = true`, the fetch uses `requests.get` with **no cookies forwarded**, a neutral User-Agent, a 10-second timeout, and follows at most 2 redirects.
- If the response is a 4xx/5xx or a login redirect (detected by presence of `<form` with `password` input in response body), the fetch is **silently skipped** and only `(url, title, visit_time)` metadata is stored.

#### Excluded Domains (canonical list: Addendum D)
The excluded domains list is the single source of truth. Any domain in that list is never fetched, and its URL is stored only as metadata (no title fetch attempt). The default list includes:

- All banking TLDs and common banking subdomains
- Healthcare portals
- Password managers
- Corporate SSO / identity providers
- Social media direct message paths
- All `localhost` and `127.*` patterns

**CI enforcement:** A unit test asserts that every domain in the default excluded list returns `SKIP` from the fetch policy function.

#### Raw HTML Retention
Raw fetched HTML is stored in `documents.raw_content` and is purged after the canonical raw retention period (Addendum B). Only `clean_content` (readability-extracted text) is retained long-term.

### 6.5 Daemon Orchestration

```
daemon.start()
  └─ for each ingestor in registry:
       ingestor.start_thread()
       ingestor.emit() → priority_queue.put(RawDocument)

priority_queue.get()
  └─ worker_pool.submit(pipeline, raw_doc)
       └─ parse → redact → persist_raw → chunk → embed → graph → update_fts
            (each step wrapped in try/except; failure logs structured error, 
             marks document as FAILED in SQLite, continues to next item)
```

**The daemon never crashes on a single bad document.** Every pipeline step is isolated. Failed documents are queryable via `SELECT * FROM documents WHERE status = 'FAILED'`.

---

## 7. Pillar II — PARSE (Universal Normalization)

### 7.1 ParsedDocument Contract

The parser's output is a `ParsedDocument`. This is the canonical interface between PARSE and INDEX:

```python
@dataclass
class ParsedDocument:
    document_id: str          # FK to SQLite documents.id
    clean_content: str        # Normalized UTF-8 text, ready for chunking
    content_type: ContentType # PDF | HTML | CODE | EMAIL | IMAGE | MARKDOWN | PLAIN
    language: Optional[str]   # Programming language (for CODE type only)
    word_count: int
    char_count: int
    parse_metadata: dict      # Parser-specific extras (pdf: page_count; code: top_symbols)
    parsed_at: datetime
```

### 7.2 Parser Dispatch Table

| Content type | Detection method | Parser library | Fallback |
|---|---|---|---|
| PDF | `.pdf` extension + magic bytes | `pdfminer.six` | Empty string + FAILED log |
| HTML | `text/html` MIME or `.html` | `readability-lxml` | Raw tag-stripped text |
| Code | Extension map + tree-sitter heuristic | `tree-sitter` | Plain text |
| Email | `.eml` / MIME multipart | stdlib `email` | Plain text |
| Markdown | `.md` / `.markdown` | `markdown-it-py` → plain | Plain text |
| Image | `.png/.jpg/.gif` + MIME | `pytesseract` + Tesseract | Empty string + WARN log |
| Plain | Everything else | UTF-8 decode with chardet fallback | Latin-1 decode |

### 7.3 Code Parser Enrichment

For `ContentType.CODE`, the parser uses tree-sitter to extract:
1. All docstrings and block comments (prepended to clean_content)
2. All function/class names (appended as a "symbol index" for embedding quality)
3. The raw code body

The order in `clean_content` is: `docstrings → symbol index → raw code`. This prioritizes semantic content in the embedding context window.

### 7.4 Parse Failure Policy

| Failure type | Action |
|---|---|
| Library exception (corrupt PDF, etc.) | Log structured error; set `documents.status = 'PARSE_FAILED'`; do NOT propagate exception |
| Empty clean_content after parse | Log WARN; set `status = 'EMPTY'`; skip downstream steps |
| Encoding detection failure | Attempt Latin-1 fallback; if still fails, mark PARSE_FAILED |
| OCR returns no text | Log WARN; set `status = 'OCR_EMPTY'`; store metadata only |

---

## 8. Pillar III — INDEX (Embed + Graph + FTS)

### 8.1 Chunking

Chunking is the primary quality lever for retrieval. The `SmartChunker` dispatches by `content_type` to a content-aware chunking strategy.

#### Token Budgets (illustrative — canonical values in Addendum C)

| Content type | Target tokens | Overlap tokens | Split boundary |
|---|---|---|---|
| Prose (plain/markdown/HTML) | ~400 | ~50 | Paragraph boundary |
| Code | ~300 | ~30 | Function/class boundary |
| Email | ~200 | ~20 | Paragraph boundary |
| PDF | ~400 | ~50 | Paragraph boundary |
| Image OCR | ~150 | 0 | Sentence boundary |

#### Chunk Contract

```python
@dataclass
class Chunk:
    chunk_id: str             # UUID
    document_id: str          # FK to documents
    content: str              # The chunk text
    token_count: int
    chunk_index: int          # Position in document (0-based)
    total_chunks: int         # Total chunks in document
    start_char: int           # Character offset in clean_content
    end_char: int
    chroma_id: Optional[str]  # Set after embedding
```

### 8.2 Embedding Pipeline

```
Chunk.content
  → Ollama.embed(model=config.embed_model, text=chunk.content)
  → vector: List[float]  (1536-dim for nomic-embed-text)
  → Chroma.collection.upsert(
        ids=[chunk.chunk_id],
        embeddings=[vector],
        documents=[chunk.content],
        metadatas=[{
            "document_id": chunk.document_id,
            "source_type": doc.source_type,
            "source_path": doc.source_path,
            "captured_at": doc.captured_at.isoformat(),
            "content_type": doc.content_type,
            "chunk_index": chunk.chunk_index,
            "embed_model": config.embed_model,      # ← critical for migration
            "embed_model_version": config.embed_model_version
        }]
    )
  → SQLite: UPDATE chunks SET chroma_id = ?, embedded_at = ? WHERE chunk_id = ?
```

**`embed_model` and `embed_model_version` are stored in every Chroma metadata record.** This enables selective re-embedding during model migration (see §15).

#### Embedding Cache Strategy

1. If `chunks.chroma_id IS NOT NULL` AND document checksum unchanged → skip embedding
2. If document checksum changed → delete old Chroma vectors by `document_id` filter → re-embed all chunks
3. If `documents.is_embedded = 1` AND checksum unchanged → skip all chunks for that document

### 8.3 Knowledge Graph Extraction

#### Entity Extraction (spaCy)
```
clean_content
  → spaCy NER (en_core_web_trf or en_core_web_sm for CPU)
  → entities: List[{text, label, start_char, end_char, confidence}]
  → SQLite: INSERT INTO entities (canonical_name, entity_type, ...)
  → SQLite: INSERT INTO entity_mentions (entity_id, document_id, chunk_id, ...)
```

#### Relation Extraction (LLM, optional)
```
chunk.content + entity list
  → Ollama.chat(model=config.chat_model, prompt=RELATION_EXTRACTION_PROMPT)
  → relations: List[{subject, predicate, object, confidence, evidence}]
  → filter: confidence >= RELATION_CONFIDENCE_THRESHOLD (canonical: Addendum A)
  → KuzuDB: CREATE (subject)-[predicate]->(object) with evidence
  → SQLite: INSERT INTO relations (...)
```

Relation extraction is **opt-in** via `config.toml: graph.extract_relations = true` (default: `false` for CPU-only systems). Entity extraction (spaCy) always runs.

### 8.4 FTS Update

SQLite FTS5 tables are updated via triggers automatically on `INSERT` / `UPDATE` / `DELETE` to `documents` and `chunks`. No explicit FTS write step is needed in the pipeline.

```sql
-- Trigger (canonical SQL in migration files, not here)
CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, content) VALUES (new.rowid, new.content);
END;
```

---

## 9. Pillar IV — RECALL (Hybrid Retrieval)

### 9.1 The Four-Signal Model

MEMEX retrieval fuses four independent signals. The weights are **illustrative here; canonical values are in Addendum A.**

| Signal | Mechanism | Illustrative weight |
|---|---|---|
| **Vector** | Cosine similarity, Chroma HNSW | 0.40 |
| **Keyword** | SQLite FTS5 BM25 rank | 0.30 |
| **Graph** | KuzuDB entity neighborhood traversal → doc IDs | 0.20 |
| **Temporal** | Exponential recency decay on `captured_at` | 0.10 |

#### Temporal Decay Formula
```
temporal_score(doc) = exp(-λ * age_days)
```
Where `λ` (lambda, the decay constant) is canonical in Addendum A. Higher λ = faster decay = stronger recency bias.

### 9.2 Retrieval Flow

```
query: str
  │
  ├─[1] VECTOR SIGNAL
  │     → Ollama.embed(query)
  │     → Chroma.query(embedding, n_results=50, where=time_filter)
  │     → List[(chunk_id, score)]
  │
  ├─[2] KEYWORD SIGNAL
  │     → SQLite FTS5: SELECT rowid, bm25(chunks_fts) FROM chunks_fts WHERE chunks_fts MATCH ?
  │     → Normalize BM25 scores to [0,1]
  │     → List[(chunk_id, score)]
  │
  ├─[3] GRAPH SIGNAL
  │     → spaCy NER on query → entity list
  │     → KuzuDB: MATCH (e:Entity)-[:MENTIONED_IN]->(d:Document) WHERE e.name IN [entities]
  │     → Expand to 2-hop neighbors
  │     → List[(document_id, hop_distance_score)]
  │     → Join to chunk_ids via SQLite
  │
  ├─[4] TEMPORAL SIGNAL
  │     → For each candidate chunk: fetch captured_at from SQLite
  │     → Compute exp(-λ * age_days) for each
  │
  └─[FUSION]
        → For each unique chunk_id across all signals:
             combined_score = (w_vec * vec_score)
                            + (w_kw  * kw_score)
                            + (w_graph * graph_score)
                            + (w_time * temporal_score)
        → Sort descending by combined_score
        → Return top K (canonical K: Addendum A)
```

### 9.3 Time Filtering

Users can express time constraints in natural language:

| User input | Resolved filter |
|---|---|
| "last week" | `captured_at >= now() - 7 days` |
| "in March" | `captured_at BETWEEN ...` |
| "before my job change" | LLM resolves to approximate date range |
| "recently" | Temporal signal weight increased; no hard cutoff |

Time filters are applied as `WHERE` clauses in both the Chroma query metadata filter AND the SQLite FTS query. Temporal decay still runs on filtered results.

### 9.4 Retrieval Result Contract

```python
@dataclass
class RetrievalResult:
    chunk_id: str
    document_id: str
    content: str
    combined_score: float
    vector_score: float
    keyword_score: float
    graph_score: float
    temporal_score: float
    source_type: str
    source_path: str
    captured_at: datetime
    citation_index: int       # Assigned by ANSWER layer (1-based)
```

---

## 10. Pillar V — ANSWER (Conversation + Citations)

### 10.1 Context Window Budgeting

```
MAX_CONTEXT_TOKENS = config.llm.context_budget  (canonical: Addendum C)

For each RetrievalResult in ranked order:
  if accumulated_tokens + result.token_count <= MAX_CONTEXT_TOKENS:
    include in context
  else:
    stop
```

This ensures the LLM prompt never exceeds the model's context window regardless of chunk sizes.

### 10.2 Prompt Template

The prompt template is **not** negotiable — it enforces citation-only answers. The canonical template is:

```
SYSTEM:
You are MEMEX, a personal memory assistant. You have access to the user's 
indexed personal documents, notes, and digital history. Your job is to answer 
questions using ONLY the provided context below.

Rules (non-negotiable):
1. Only use information from the CONTEXT section. Do not use prior knowledge.
2. Every factual claim MUST be followed by [Source N] citing the source.
3. If the answer is not in the context, say exactly: 
   "I don't have information about that in your indexed memory."
4. Do not fabricate, infer beyond the context, or fill gaps with general knowledge.
5. If multiple sources support a claim, cite all relevant ones: [Source 1][Source 3].

CONTEXT:
[Source 1] (captured: {captured_at}, from: {source_type} — {source_path})
{chunk_content}

[Source 2] ...

CONVERSATION HISTORY:
{last_N_turns}

USER: {query}

ASSISTANT:
```

### 10.3 Citation Rendering

The ANSWER layer:
1. Assigns `citation_index` (1-based) to each included `RetrievalResult`
2. Passes the formatted context to Ollama
3. Parses `[Source N]` markers from the LLM response
4. Renders each `[Source N]` as a clickable card in the Web UI / expandable line in TUI, showing: `document title | source type | capture date | snippet`

### 10.4 Conversation History

```python
@dataclass
class ConversationTurn:
    turn_id: str
    session_id: str
    role: str         # "user" | "assistant"
    content: str
    sources_cited: List[str]   # chunk_ids cited in this turn
    created_at: datetime
```

Sessions are stored in SQLite `conversations` and `conversation_turns` tables. History window for prompt inclusion is configurable (canonical: Addendum C).

### 10.5 Streaming

The ANSWER layer streams tokens from Ollama to the UI via:
- **TUI:** Textual `update()` live widget
- **Web UI:** `/api/chat/stream` SSE endpoint (see §13)

---

## 11. Pillar VI — PROTECT (Privacy, Redaction, Forget)

### 11.1 Secret Redaction

The redactor runs **after parsing and before chunking/storage**. It is the last gate before user data is written.

#### Redaction patterns (canonical registry: Addendum D)

The canonical pattern list in Addendum D covers (illustrative categories):
- API keys and tokens (`sk-...`, `ghp_...`, `Bearer ...`)
- Private key headers (`-----BEGIN ... PRIVATE KEY-----`)
- AWS credentials (`AKIA...`)
- Database connection strings (`postgres://user:pass@...`)
- Generic high-entropy secrets (entropy-based heuristic, configurable threshold)
- Credit card patterns (Luhn-validated)
- Social Security / BSN-format numbers

Redaction replaces matched text with `[REDACTED:{pattern_name}]` in `clean_content`. The original `raw_content` is NOT redacted (it is subject to TTL purge; see Addendum B).

**CI enforcement:** Unit tests verify every pattern in Addendum D correctly redacts known fixtures and does not false-positive on common innocuous strings.

### 11.2 Raw Content TTL Purge

`documents.raw_content` is purged (set to `NULL`) after the canonical raw retention period (Addendum B). This is handled by a scheduled local job (`memex_scheduler.py`) that runs:

```sql
UPDATE documents
SET raw_content = NULL, raw_purged_at = CURRENT_TIMESTAMP
WHERE raw_content IS NOT NULL
  AND captured_at < datetime('now', '-' || ? || ' days')
```

Where the number of days is sourced **exclusively from Addendum B**. Hard-coding this value anywhere else will fail CI.

### 11.3 The "Forget" Protocol

Forget must be **complete, verifiable, and atomic** across all four stores. Partial forget is a bug.

#### Single Document Forget

```
DELETE /api/memory/{document_id}

Step 1: Fetch all chunk_ids for document_id from SQLite chunks table
Step 2: Chroma.collection.delete(ids=chunk_ids)  → verify len(result) == len(chunk_ids)
Step 3: KuzuDB: MATCH (m:Mention)-[:IN_DOC]->(d:Doc {id: document_id}) DELETE m
         KuzuDB: MATCH (:Entity)-[r:RELATION {doc_id: document_id}]-() DELETE r
Step 4: SQLite DELETE FROM entity_mentions WHERE document_id = ?
Step 5: SQLite DELETE FROM relations WHERE document_id = ?
Step 6: SQLite DELETE FROM chunks WHERE document_id = ?
Step 7: SQLite DELETE FROM documents WHERE id = ?
Step 8: SQLite FTS auto-updates via trigger
Step 9: Orphan entity cleanup: 
        DELETE FROM entities WHERE id NOT IN (SELECT entity_id FROM entity_mentions)
Step 10: Write audit entry to forget_log: {document_id, path, source_type, forgotten_at, 
          chroma_verified: bool, kuzu_verified: bool}

If ANY step fails: rollback what is reversible, log FORGET_PARTIAL_FAILURE, 
                   mark document status = 'FORGET_FAILED' for retry
```

#### Bulk Forget by Source Type

```
DELETE /api/memory/source/{source_type}

Same as above but fetches all document_ids WHERE source_type = ? first,
then executes the 10-step protocol per document in a transaction.
```

#### Forget Verification

The `/api/memory/forget/verify/{document_id}` endpoint:
1. Queries Chroma for any vectors with metadata `document_id = ?` → asserts 0 results
2. Queries SQLite for `chunks WHERE document_id = ?` → asserts 0 rows
3. Queries KuzuDB for mentions in doc → asserts 0 nodes
4. Returns `{verified: true, stores_checked: ["chroma", "sqlite", "kuzu"]}` or lists failures

---

## 12. Data Model

### 12.1 SQLite Schema

```sql
-- Core document store
CREATE TABLE documents (
    id              TEXT PRIMARY KEY,           -- UUID
    source_type     TEXT NOT NULL,
    source_path     TEXT NOT NULL,
    raw_content     BLOB,                       -- Purged after TTL (Addendum B)
    clean_content   TEXT,
    content_type    TEXT,
    checksum        TEXT NOT NULL UNIQUE,       -- SHA-256
    word_count      INTEGER,
    status          TEXT NOT NULL DEFAULT 'PENDING',
    -- PENDING | PARSED | EMBEDDED | GRAPHED | INDEXED | FAILED | 
    -- PARSE_FAILED | OCR_EMPTY | FORGET_FAILED
    captured_at     DATETIME NOT NULL,
    ingested_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    parsed_at       DATETIME,
    embedded_at     DATETIME,
    graphed_at      DATETIME,
    raw_purged_at   DATETIME,
    is_embedded     INTEGER DEFAULT 0,
    is_graphed      INTEGER DEFAULT 0,
    source_metadata TEXT                        -- JSON
);

-- Retrieval units
CREATE TABLE chunks (
    id              TEXT PRIMARY KEY,           -- UUID
    document_id     TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content         TEXT NOT NULL,
    token_count     INTEGER,
    chunk_index     INTEGER,
    total_chunks    INTEGER,
    start_char      INTEGER,
    end_char        INTEGER,
    chroma_id       TEXT,                       -- NULL until embedded
    embedded_at     DATETIME,
    UNIQUE(document_id, chunk_index)
);

-- Entity registry
CREATE TABLE entities (
    id              TEXT PRIMARY KEY,
    canonical_name  TEXT NOT NULL,
    entity_type     TEXT NOT NULL,              -- PERSON | ORG | PLACE | CONCEPT | ...
    first_seen      DATETIME,
    last_seen       DATETIME,
    mention_count   INTEGER DEFAULT 0
);

-- Entity occurrence tracking
CREATE TABLE entity_mentions (
    id              TEXT PRIMARY KEY,
    entity_id       TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    document_id     TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id        TEXT REFERENCES chunks(id) ON DELETE CASCADE,
    mention_text    TEXT,                       -- Surface form as it appeared
    start_char      INTEGER,
    confidence      REAL,
    mentioned_at    DATETIME
);

-- LLM-extracted relations
CREATE TABLE relations (
    id              TEXT PRIMARY KEY,
    subject_id      TEXT NOT NULL REFERENCES entities(id),
    predicate       TEXT NOT NULL,
    object_id       TEXT NOT NULL REFERENCES entities(id),
    document_id     TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id        TEXT REFERENCES chunks(id) ON DELETE CASCADE,
    confidence      REAL,
    evidence        TEXT,                       -- Supporting quote
    extracted_at    DATETIME
);

-- Conversation sessions
CREATE TABLE conversations (
    id              TEXT PRIMARY KEY,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_active     DATETIME,
    title           TEXT                        -- Auto-generated from first turn
);

-- Conversation turns
CREATE TABLE conversation_turns (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,              -- "user" | "assistant"
    content         TEXT NOT NULL,
    sources_cited   TEXT,                       -- JSON array of chunk_ids
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Embed model registry (critical for migration tracking)
CREATE TABLE embed_model_registry (
    id              TEXT PRIMARY KEY,
    model_name      TEXT NOT NULL,
    model_version   TEXT NOT NULL,
    registered_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active       INTEGER DEFAULT 0,          -- Only one active at a time
    total_chunks    INTEGER DEFAULT 0,
    collection_name TEXT NOT NULL               -- Chroma collection name for this model
);

-- Forget audit log
CREATE TABLE forget_log (
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
CREATE VIRTUAL TABLE documents_fts USING fts5(
    content,
    content="documents",
    content_rowid="rowid",
    tokenize="porter unicode61"
);

CREATE VIRTUAL TABLE chunks_fts USING fts5(
    content,
    content="chunks",
    content_rowid="rowid",
    tokenize="porter unicode61"
);

-- FTS sync triggers
CREATE TRIGGER documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, content) VALUES (new.rowid, new.clean_content);
END;
CREATE TRIGGER documents_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, content) VALUES ('delete', old.rowid, old.clean_content);
    INSERT INTO documents_fts(rowid, content) VALUES (new.rowid, new.clean_content);
END;
CREATE TRIGGER documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, content) VALUES ('delete', old.rowid, old.clean_content);
END;
-- (Identical triggers for chunks_fts on chunks table)

-- Performance indexes
CREATE INDEX idx_documents_source_type    ON documents(source_type);
CREATE INDEX idx_documents_captured_at    ON documents(captured_at);
CREATE INDEX idx_documents_checksum       ON documents(checksum);
CREATE INDEX idx_documents_status         ON documents(status);
CREATE INDEX idx_chunks_document_id       ON chunks(document_id);
CREATE INDEX idx_chunks_chroma_id         ON chunks(chroma_id);
CREATE INDEX idx_entity_mentions_entity   ON entity_mentions(entity_id);
CREATE INDEX idx_entity_mentions_document ON entity_mentions(document_id);
CREATE INDEX idx_relations_subject        ON relations(subject_id);
CREATE INDEX idx_relations_object         ON relations(object_id);
CREATE INDEX idx_relations_document       ON relations(document_id);
```

### 12.2 KuzuDB Graph Schema

```cypher
-- Node types
CREATE NODE TABLE Document (id STRING, source_type STRING, source_path STRING, 
                             captured_at STRING, PRIMARY KEY (id));
CREATE NODE TABLE Entity   (id STRING, canonical_name STRING, entity_type STRING, 
                             PRIMARY KEY (id));
CREATE NODE TABLE Chunk    (id STRING, document_id STRING, chunk_index INT64, 
                             PRIMARY KEY (id));

-- Edge types
CREATE REL TABLE MENTIONED_IN  (FROM Entity TO Document, confidence DOUBLE, mention_text STRING);
CREATE REL TABLE MENTIONED_IN_CHUNK (FROM Entity TO Chunk, confidence DOUBLE);
CREATE REL TABLE RELATED_TO    (FROM Entity TO Entity, predicate STRING, 
                                 confidence DOUBLE, evidence STRING, document_id STRING);
CREATE REL TABLE CONTAINS      (FROM Document TO Chunk);
```

---

## 13. Local REST API Surface

### 13.1 Binding Contract

The FastAPI server **MUST** bind to `127.0.0.1:7700` only. It MUST NOT bind to `0.0.0.0`. Middleware rejects any request whose source IP is not loopback:

```python
@app.middleware("http")
async def loopback_only(request: Request, call_next):
    if request.client.host not in ("127.0.0.1", "::1"):
        return Response(status_code=403, content="Remote access forbidden")
    return await call_next(request)
```

**CI test:** A test spins up the server and asserts that a request from a mocked non-loopback IP receives `403`.

### 13.2 Endpoint Inventory

#### Memory
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/memory/search` | Hybrid search; params: `q`, `limit`, `after`, `before`, `source_type` |
| `GET` | `/api/memory/timeline` | Chronological document listing; params: `source_type`, `after`, `before`, `limit`, `offset` |
| `GET` | `/api/memory/{document_id}` | Fetch single document with all chunks |
| `DELETE` | `/api/memory/{document_id}` | Hard forget (10-step protocol, see §11.3) |
| `DELETE` | `/api/memory/source/{source_type}` | Bulk forget by source |
| `GET` | `/api/memory/forget/verify/{document_id}` | Verify forget completion across all stores |

#### Conversation
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/chat` | Single-turn chat; body: `{session_id, query}` |
| `GET` | `/api/chat/stream` | SSE streaming chat; params: `session_id`, `query` |
| `GET` | `/api/chat/sessions` | List all sessions |
| `GET` | `/api/chat/sessions/{session_id}` | Get session history |
| `DELETE` | `/api/chat/sessions/{session_id}` | Delete session + all turns |

#### Graph
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/graph/entities` | List entities; params: `type`, `q`, `limit` |
| `GET` | `/api/graph/entity/{entity_id}` | Entity + neighbors |
| `GET` | `/api/graph/relations` | List relations; params: `subject_id`, `object_id`, `predicate` |

#### System
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Daemon status, store connectivity, queue depth, Ollama status |
| `GET` | `/api/stats` | Ingestion counts, embedding coverage %, graph size, index size |
| `POST` | `/api/reindex` | Trigger re-index for a specific `document_id` or `source_type` |
| `GET` | `/api/models` | List registered embed models, active model, migration status |
| `POST` | `/api/models/migrate` | Trigger re-embed migration (see §15) |
| `GET` | `/api/logs/stream` | SSE stream of structured daemon log lines |

### 13.3 Response Envelope

All API responses follow:
```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "request_id": "uuid",
    "duration_ms": 45,
    "version": "2.0.0"
  },
  "error": null
}
```

Error responses:
```json
{
  "success": false,
  "data": null,
  "meta": { ... },
  "error": {
    "code": "DOCUMENT_NOT_FOUND",
    "message": "No document with id abc123",
    "retryable": false
  }
}
```

---

## 14. Failure Modes & Backpressure

This section defines the behavior of the system under every named failure condition. "Undefined behavior" is not acceptable in a production daemon.

### 14.1 Queue Backpressure

| Condition | Detection | Action |
|---|---|---|
| Queue depth > `QUEUE_WARN_THRESHOLD` (Addendum B) | Queue size check in ingestor emit path | Log WARN with queue depth; emit telemetry event |
| Queue depth >= `QUEUE_MAX_DEPTH` (Addendum B) | Queue size check on `put()` | DROP new item; log structured DROP event with `{source_type, source_path, checksum, reason: "queue_full"}`; increment `stats.dropped_count` |
| Queue depth returns to < 50% after high water | Queue size check in worker loop | Log INFO "queue_recovered" |

Dropped items are **never silently lost** — they produce a structured log entry that can be replayed via `memex reindex --source <path>`.

### 14.2 Ollama Unavailable

| Stage | Failure | Action |
|---|---|---|
| Daemon startup | Ollama not running | Log WARN; daemon starts but marks embedding workers as SUSPENDED; ingestion + parsing continue; documents queued for embedding once Ollama recovers |
| Mid-pipeline embed | Ollama connection refused | Retry 3× with exponential backoff (1s, 2s, 4s); if all fail, mark chunk `embed_status = 'PENDING_RETRY'`; continue to next item |
| Ollama returns error response | HTTP 5xx from Ollama | Same retry policy as above |
| Ollama recovery detection | Health check every 30s | When `/api/tags` returns 200, re-activate embedding workers; process all `embed_status = 'PENDING_RETRY'` chunks |

### 14.3 Chroma Errors

| Failure | Action |
|---|---|
| Chroma file locked (another process) | Retry with 500ms backoff × 5; if still locked, log ERROR and suspend Chroma writes; SQLite continues |
| Chroma returns inconsistent result on verify | Log CHROMA_INCONSISTENCY; mark chunk `chroma_id = NULL`; schedule re-embed |
| Chroma collection corrupt | Log CRITICAL; halt embedding pipeline; alert via `/health` endpoint; do NOT delete; human intervention required |

### 14.4 KuzuDB Errors

| Failure | Action |
|---|---|
| Kuzu transaction fails | Rollback; log ERROR; mark document `is_graphed = 0`; schedule graph retry |
| Kuzu file corrupt | Log CRITICAL; disable graph extraction; vector + keyword retrieval continue (graph signal weight → 0.0); alert in `/health` |

### 14.5 Parser Failures

| Failure | Action |
|---|---|
| Library exception (any parser) | Catch broadly; log structured `{document_id, parser, exception_type, message}`; set `status = 'PARSE_FAILED'`; continue to next item |
| Encoding error | Attempt fallback chain: UTF-8 → chardet detect → Latin-1; if all fail, mark PARSE_FAILED |
| Parse produces empty clean_content | Mark `status = 'EMPTY'`; skip downstream steps; log WARN |
| Parse takes > `PARSE_TIMEOUT_SECONDS` (Addendum B) | Kill parser thread; mark PARSE_FAILED with `reason: 'timeout'` |

### 14.6 SQLite Write Errors

| Failure | Action |
|---|---|
| SQLITE_BUSY (WAL conflict) | Retry with 100ms backoff × 10; if still failing, log ERROR and requeue item |
| SQLITE_FULL (disk full) | Log CRITICAL; halt ALL writes; alert via `/health`; do NOT corrupt existing data |
| UNIQUE constraint violation on checksum | This means dedup should have caught it; log WARN; skip gracefully |

### 14.7 Retry Tracking

The SQLite `documents` table has a `retry_count INTEGER DEFAULT 0` and `last_error TEXT` column. Any step that fails increments `retry_count`. Documents with `retry_count >= MAX_RETRY` (Addendum B) are marked `status = 'ABANDONED'` and excluded from future retry cycles but remain queryable in status checks.

---

## 15. Model Versioning & Re-Embed Migration

This is a production-critical gap not covered in the original design. **Upgrading the embedding model invalidates all existing vectors.** This section defines the protocol.

### 15.1 Why This Matters

Embeddings from `nomic-embed-text v1` are in a different geometric space than `nomic-embed-text v2` (or any other model). Querying a Chroma collection with v2 embeddings against v1 vectors produces **semantically meaningless similarity scores** — results will silently degrade without error.

### 15.2 Model Registry

The `embed_model_registry` table tracks all models that have ever been used:

```sql
-- Example state during migration
SELECT model_name, model_version, is_active, total_chunks, collection_name
FROM embed_model_registry;

-- nomic-embed-text | 1.5 | 0 (old)  | 142,000 | memex_vectors_v1
-- nomic-embed-text | 2.0 | 1 (new)  |  28,000 | memex_vectors_v2  ← migration in progress
```

### 15.3 Migration Protocol

```
Phase 1: REGISTER NEW MODEL
  → INSERT INTO embed_model_registry (model_name, model_version, is_active=0, collection_name='memex_vectors_v2')
  → Pull new model: `ollama pull nomic-embed-text:v2`
  → Create new Chroma collection: `memex_vectors_v2`

Phase 2: PARALLEL RE-EMBED (background, non-blocking)
  → Set daemon config: embed_model = new model, target_collection = memex_vectors_v2
  → Worker processes all documents in batches (low priority, CPU-throttled)
  → For each chunk: embed with new model → upsert to memex_vectors_v2 collection
  → Update chunk metadata: embed_model = new_model, embed_model_version = new_version
  → Increment embed_model_registry.total_chunks for new model
  
Phase 3: CUTOVER (when migration_progress = 100%)
  → UPDATE embed_model_registry SET is_active = 0 WHERE model_version = '1.5'
  → UPDATE embed_model_registry SET is_active = 1 WHERE model_version = '2.0'
  → Update config.toml: active_collection = memex_vectors_v2
  → All new queries now use memex_vectors_v2
  
Phase 4: CLEANUP (after validation period, manual)
  → Delete old Chroma collection: memex_vectors_v1
  → Archive embed_model_registry record for v1

Phase 5: VALIDATION
  → Run eval suite (see §18, INV-012) against new collection
  → If recall quality degrades: rollback to Phase 3 with old model
```

### 15.4 Migration Progress API

`GET /api/models/migrate/progress` returns:
```json
{
  "old_model": "nomic-embed-text:1.5",
  "new_model": "nomic-embed-text:2.0",
  "total_chunks": 142000,
  "migrated_chunks": 28000,
  "progress_pct": 19.7,
  "eta_minutes": 187,
  "status": "IN_PROGRESS"
}
```

### 15.5 Config-Driven Model Selection

```toml
[embedding]
model = "nomic-embed-text"
model_version = "1.5"
active_collection = "memex_vectors_v1"
migration_collection = ""          # Set during migration

[chat]
model = "llama3:8b"
```

**No embedding model name or collection name is ever hard-coded in source files.** CI rejects any string literal matching `/nomic|llama|embed/` outside of config-loading code.

---

## 16. Observability & Local Telemetry

### 16.1 Structured Logging

All daemon logs are written as **structured JSON** to a rotating log file at `~/.memex/logs/daemon.log`.

#### Log format
```json
{
  "timestamp": "2026-06-11T10:23:45.123Z",
  "level": "INFO",
  "pillar": "INGEST",
  "event": "document_ingested",
  "document_id": "abc-123",
  "source_type": "filesystem",
  "source_path": "/home/user/notes/meeting.md",
  "duration_ms": 42,
  "checksum": "sha256:...",
  "queue_depth": 14
}
```

#### Log rotation policy
- Max file size: `50MB`
- Retain: `7 rotated files`
- Total max log storage: `~350MB`
- Log level configurable: `DEBUG | INFO | WARN | ERROR | CRITICAL`

#### Named events (all structured, searchable)

| Event name | Level | Pillar | Meaning |
|---|---|---|---|
| `document_ingested` | INFO | INGEST | Ingestor emitted a RawDocument |
| `document_deduped` | DEBUG | INGEST | Checksum match; skipped |
| `queue_high_water` | WARN | INGEST | Queue > warn threshold |
| `queue_item_dropped` | WARN | INGEST | Queue full; item dropped |
| `parse_complete` | INFO | PARSE | Parser produced clean_content |
| `parse_failed` | ERROR | PARSE | Parser threw exception |
| `embed_complete` | INFO | INDEX | Chunk embedded to Chroma |
| `embed_retry` | WARN | INDEX | Ollama unavailable; retry |
| `graph_extracted` | INFO | INDEX | Entities/relations extracted |
| `retrieval_complete` | INFO | RECALL | Hybrid retrieval returned results |
| `answer_generated` | INFO | ANSWER | LLM response + citations produced |
| `forget_complete` | INFO | PROTECT | Document forgotten from all stores |
| `forget_partial_failure` | ERROR | PROTECT | Forget incomplete; manual check needed |
| `redaction_applied` | INFO | PROTECT | Secret pattern matched and redacted |
| `raw_content_purged` | INFO | PROTECT | Raw bytes purged per TTL |
| `ollama_unavailable` | WARN | INDEX | Cannot reach Ollama |
| `ollama_recovered` | INFO | INDEX | Ollama back online |
| `migration_started` | INFO | INDEX | Re-embed migration begun |
| `migration_complete` | INFO | INDEX | Re-embed migration finished |

### 16.2 Health Endpoint

`GET /api/health` returns the canonical daemon health snapshot:

```json
{
  "status": "healthy",              
  "daemon_running": true,
  "queue_depth": 3,
  "queue_max": 500,
  "stores": {
    "sqlite": { "status": "ok", "size_mb": 142.3 },
    "chroma": { "status": "ok", "total_chunks": 142000, "collection": "memex_vectors_v1" },
    "kuzu":   { "status": "ok", "total_nodes": 8420, "total_edges": 14200 }
  },
  "ollama": {
    "status": "ok",
    "embed_model": "nomic-embed-text:1.5",
    "chat_model": "llama3:8b"
  },
  "migration": {
    "in_progress": false,
    "progress_pct": null
  },
  "os_encryption": {
    "detected": true,
    "method": "FileVault"
  },
  "pending_failures": {
    "parse_failed": 2,
    "embed_pending_retry": 0,
    "forget_failed": 0
  }
}
```

### 16.3 Stats Endpoint

`GET /api/stats` returns aggregate ingestion metrics:

```json
{
  "total_documents": 8420,
  "by_source_type": {
    "filesystem": 6100,
    "browser": 1800,
    "terminal": 320,
    "clipboard": 200
  },
  "total_chunks": 142000,
  "embedding_coverage_pct": 98.6,
  "graph_coverage_pct": 71.2,
  "total_entities": 3200,
  "total_relations": 1840,
  "conversations": 142,
  "dropped_since_start": 0,
  "failed_documents": 2
}
```

### 16.4 Daemon Self-Check (`memex doctor`)

The `memex doctor` CLI command performs a pre-flight check before daemon start:

| Check | Pass condition | Fail action |
|---|---|---|
| Ollama reachable | `GET localhost:11434/api/tags` returns 200 | WARN (daemon starts degraded) |
| Embed model pulled | Model name in Ollama model list | WARN + prompt to pull |
| Chat model pulled | Model name in Ollama model list | WARN + prompt to pull |
| SQLite readable/writable | Open + write test row | ERROR — halt |
| Chroma directory writable | Write test file | ERROR — halt |
| Kuzu directory writable | Write test file | ERROR — halt |
| OS disk encryption | OS-specific check (FileVault/LUKS) | WARN (not halt; user informed) |
| Data dir permissions | `chmod 700` equivalent | WARN + auto-fix prompt |
| Config file valid TOML | Parse `config.toml` | ERROR — halt |
| Excluded domains list present | Addendum D file readable | ERROR — halt |

---

## 17. Performance SLOs

These are **Service Level Objectives** — targets the system must meet to be considered "production healthy." They are checked by the CI performance suite and reported in `/api/stats`.

*Note: All threshold values below are illustrative. Canonical values are in Addendum F.*

### 17.1 SLO Table

| SLO ID | Metric | Target | Measurement method | Alert threshold |
|---|---|---|---|---|
| SLO-001 | Daemon idle CPU usage | < 1% (no active ingestion) | `psutil` 60s average | > 5% for 5min |
| SLO-002 | FTS search latency (p95) | < 50ms at 1M chunks | Benchmark harness | > 200ms |
| SLO-003 | Vector search latency (p95) | < 200ms at 1M chunks | Benchmark harness | > 500ms |
| SLO-004 | Hybrid retrieval latency (p95) | < 500ms at 1M chunks | Benchmark harness | > 1000ms |
| SLO-005 | LLM first-token latency (p50, CPU) | < 3s | Ollama timing | > 10s |
| SLO-006 | End-to-end ingestion (avg doc, CPU) | < 30s | Pipeline timer | > 120s |
| SLO-007 | End-to-end ingestion (avg doc, GPU) | < 10s | Pipeline timer | > 30s |
| SLO-008 | Embedding throughput (CPU) | > 10 chunks/min | Throughput timer | < 5 chunks/min |
| SLO-009 | Queue high-water frequency | < 1 event/hour (normal use) | Log event count | > 5 events/hour |
| SLO-010 | Hard forget completion | < 5s for single document | Operation timer | > 30s |
| SLO-011 | API response latency (non-search) | < 100ms p95 | Request timer | > 500ms |
| SLO-012 | Log file rotation lag | < 1s after size threshold | File monitor | > 10s |

### 17.2 SLO Measurement in CI

The CI performance suite (`tests/perf/`) runs against a synthetic dataset of 10,000 documents and validates SLO-002 through SLO-006 on every PR that touches RECALL, INDEX, or ANSWER pillars.

---

## 18. Testable Invariants & CI Gates

This section defines the canonical set of invariants that MEMEX must maintain. Every invariant has a corresponding automated test. **PRs that break any invariant are blocked.**

### 18.1 Security Invariants

| ID | Invariant | Test type | Pillar |
|---|---|---|---|
| INV-001 | API server never binds to non-loopback address | Integration | PROTECT |
| INV-002 | Non-loopback HTTP request receives 403 | Integration | PROTECT |
| INV-003 | No outbound network calls during normal operation | Network mock | PROTECT |
| INV-004 | Ollama is called only on localhost | Network mock | INDEX |
| INV-005 | Every pattern in Addendum D correctly redacts a known fixture | Unit | PROTECT |
| INV-006 | No Addendum D pattern false-positives on common innocuous strings | Unit | PROTECT |
| INV-007 | Raw content is NULL after TTL period (Addendum B) | Integration | PROTECT |

### 18.2 Forget / Delete Invariants

| ID | Invariant | Test type | Pillar |
|---|---|---|---|
| INV-008 | After forget, Chroma has zero vectors for document_id | Integration | PROTECT |
| INV-009 | After forget, SQLite has zero chunks for document_id | Integration | PROTECT |
| INV-010 | After forget, KuzuDB has zero mentions for document_id | Integration | PROTECT |
| INV-011 | After forget, document does not appear in hybrid retrieval | Integration | PROTECT |
| INV-012 | Forget audit log entry is written for every forget operation | Integration | PROTECT |
| INV-013 | Bulk forget by source_type removes all documents of that type | Integration | PROTECT |

### 18.3 Retrieval Quality Invariants

| ID | Invariant | Test type | Pillar |
|---|---|---|---|
| INV-014 | LLM answer contains at least one `[Source N]` citation | Eval | ANSWER |
| INV-015 | Every cited `[Source N]` maps to a real chunk_id in the context | Eval | ANSWER |
| INV-016 | Hybrid retrieval returns results in score-descending order | Unit | RECALL |
| INV-017 | Time filter `after:X` returns no documents captured before X | Unit | RECALL |
| INV-018 | Retrieval weights sum to 1.0 (canonical Addendum A) | Unit | RECALL |
| INV-019 | Temporal decay score is monotonically decreasing with age | Unit | RECALL |

### 18.4 Ingestion Invariants

| ID | Invariant | Test type | Pillar |
|---|---|---|---|
| INV-020 | Duplicate checksum is deduped; document count does not increase | Unit | INGEST |
| INV-021 | Changed file (new checksum) triggers re-index, not duplicate | Integration | INGEST |
| INV-022 | Every excluded domain in Addendum D returns SKIP from browser fetcher | Unit | INGEST |
| INV-023 | Queue full condition produces structured DROP log, not silent loss | Unit | INGEST |
| INV-024 | Parse failure marks document PARSE_FAILED, does not crash daemon | Integration | PARSE |
| INV-025 | Ollama unavailability suspends embedding but does not crash daemon | Integration | INDEX |

### 18.5 Configuration Invariants

| ID | Invariant | Test type | Pillar |
|---|---|---|---|
| INV-026 | No Addendum A weight values are hard-coded outside Addendum A | Static analysis | RECALL |
| INV-027 | No Addendum B day values are hard-coded outside Addendum B | Static analysis | PROTECT |
| INV-028 | No Addendum C token budget values are hard-coded outside Addendum C | Static analysis | PARSE |
| INV-029 | No embedding model name is hard-coded outside config-loading code | Static analysis | INDEX |
| INV-030 | `embed_model` metadata is present on every Chroma vector | Integration | INDEX |

### 18.6 CI Pipeline Structure

```
┌──────────────────────────────────────────────────────────┐
│                      CI PIPELINE                         │
│                                                          │
│  Stage 1: STATIC ANALYSIS                                │
│  ├─ Lint (ruff)                                          │
│  ├─ Type check (mypy)                                    │
│  └─ Invariant checks: INV-026, 027, 028, 029             │
│                                                          │
│  Stage 2: UNIT TESTS                                     │
│  ├─ INV-005, 006 (redactor patterns)                     │
│  ├─ INV-016, 017, 018, 019 (retrieval math)              │
│  ├─ INV-020 (dedup)                                      │
│  ├─ INV-022 (excluded domains)                           │
│  └─ INV-023 (queue drop logging)                         │
│                                                          │
│  Stage 3: INTEGRATION TESTS (ephemeral SQLite+Chroma+Kuzu)│
│  ├─ INV-001, 002 (API binding)                           │
│  ├─ INV-003, 004 (network mock)                          │
│  ├─ INV-007 (TTL purge)                                  │
│  ├─ INV-008 to 013 (forget protocol)                     │
│  ├─ INV-021 (re-index on change)                         │
│  ├─ INV-024 (parse failure isolation)                    │
│  ├─ INV-025 (Ollama unavailability)                      │
│  └─ INV-030 (Chroma metadata)                            │
│                                                          │
│  Stage 4: EVAL TESTS (synthetic 1000-doc corpus)         │
│  ├─ INV-014, 015 (citation validity)                     │
│  └─ INV-012 (forget audit)                               │
│                                                          │
│  Stage 5: PERFORMANCE SUITE (synthetic 10k-doc corpus)   │
│  └─ SLO-002 to SLO-006 benchmarks                        │
│                                                          │
│  ALL STAGES MUST PASS. No stage can be skipped on main.  │
└──────────────────────────────────────────────────────────┘
```

---

## 19. Canonical Addenda

> **These addenda are the single source of truth for all constants, thresholds, and registries. All source code, tests, and configuration files MUST read from these. Inline values in the document body are illustrative only.**

---

### Addendum A — Retrieval Weight Constants

```toml
# memex/config/retrieval_weights.toml
# CANONICAL — do not duplicate these values anywhere else

[hybrid_retrieval]
vector_weight          = 0.40
keyword_weight         = 0.30
graph_weight           = 0.20
temporal_weight        = 0.10
# Invariant: vector + keyword + graph + temporal == 1.0

[temporal_decay]
lambda                 = 0.005      # exp(-lambda * age_days); higher = faster decay

[retrieval_limits]
default_top_k          = 20         # Candidates returned before context budgeting
max_top_k              = 50         # Hard ceiling regardless of user request

[relation_extraction]
confidence_threshold   = 0.50       # Relations below this are discarded
```

---

### Addendum B — Retention & Purge Day Values

```toml
# memex/config/retention.toml
# CANONICAL — do not duplicate these values anywhere else

[raw_content]
purge_after_days       = 7          # days after captured_at before raw_content is NULLed

[conversations]
retain_turns_days      = 365        # turns older than this are soft-deleted

[failed_documents]
max_retry_count        = 5          # abandon after this many retries
retry_backoff_seconds  = [1, 2, 4, 8, 16]  # exponential backoff per retry

[queue]
max_depth              = 500        # hard ceiling; items dropped above this
warn_threshold         = 400        # WARN logged above this

[purge_schedule]
run_interval_minutes   = 60         # how often the purge job runs

[parser]
timeout_seconds        = 30         # parser killed after this; document marked PARSE_FAILED
```

---

### Addendum C — Chunk Token Budget Constants

```toml
# memex/config/chunking.toml
# CANONICAL — do not duplicate these values anywhere else

[chunk_budgets]
prose_tokens           = 400
prose_overlap_tokens   = 50
code_tokens            = 300
code_overlap_tokens    = 30
email_tokens           = 200
email_overlap_tokens   = 20
pdf_tokens             = 400
pdf_overlap_tokens     = 50
image_ocr_tokens       = 150
image_ocr_overlap      = 0

[context_window]
max_context_tokens     = 6000       # Tokens reserved for retrieved context in LLM prompt
conversation_history_turns = 6      # Last N turns included in prompt
```

---

### Addendum D — Secret Redaction Pattern Registry

```toml
# memex/config/redaction_patterns.toml
# CANONICAL — the ONLY place new patterns are added
# All entries must have: name, pattern (regex), replacement, test_fixture, innocuous_fixture

[[patterns]]
name          = "openai_key"
pattern       = 'sk-[A-Za-z0-9]{48}'
replacement   = "[REDACTED:openai_key]"
test_fixture  = "sk-aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcdefghij"
innocuous     = "asking a question is fine"

[[patterns]]
name          = "github_pat"
pattern       = 'ghp_[A-Za-z0-9]{36}'
replacement   = "[REDACTED:github_pat]"
test_fixture  = "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ01234567"
innocuous     = "github is a platform"

[[patterns]]
name          = "aws_access_key"
pattern       = 'AKIA[0-9A-Z]{16}'
replacement   = "[REDACTED:aws_access_key]"
test_fixture  = "AKIAIOSFODNN7EXAMPLE"
innocuous     = "aws is a cloud provider"

[[patterns]]
name          = "private_key_header"
pattern       = '-----BEGIN [A-Z ]*PRIVATE KEY-----'
replacement   = "[REDACTED:private_key]"
test_fixture  = "-----BEGIN RSA PRIVATE KEY-----"
innocuous     = "-----BEGIN PUBLIC KEY-----"

[[patterns]]
name          = "bearer_token"
pattern       = 'Bearer [A-Za-z0-9\-._~+/]+=*'
replacement   = "[REDACTED:bearer_token]"
test_fixture  = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
innocuous     = "bearer of bad news"

[[patterns]]
name          = "db_connection_string"
pattern       = '(postgres|mysql|mongodb|redis)://[^@\s]+:[^@\s]+@[^\s]+'
replacement   = "[REDACTED:db_connection_string]"
test_fixture  = "postgres://user:password@localhost:5432/mydb"
innocuous     = "postgres is a database"

[[patterns]]
name          = "credit_card"
pattern       = '\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11})\b'
replacement   = "[REDACTED:credit_card]"
test_fixture  = "4532015112830366"
innocuous     = "the year 1234567890"

[entropy_heuristic]
enabled                = true
min_length             = 20
entropy_threshold      = 4.5        # Shannon entropy; strings above this flagged as high-entropy secrets
context_window_chars   = 30         # Characters around the string checked for "key=", "secret=", "token=" etc.

[browser_excluded_domains]
# Domains that are NEVER fetched by the browser ingestor
# This list is append-only. Removal requires explicit ADR.
domains = [
  "chase.com", "bankofamerica.com", "wellsfargo.com",
  "1password.com", "lastpass.com", "bitwarden.com", "dashlane.com",
  "okta.com", "auth0.com", "onelogin.com",
  "mail.google.com", "outlook.live.com", "mail.yahoo.com",
  "myhealth.*", "mychart.*", "*.epic.com",
  "127.0.0.1", "localhost", "*.local",
  "facebook.com/messages", "instagram.com/direct",
  "twitter.com/messages", "signal.me"
]
```

---

### Addendum E — Testable Invariant Harness

```python
# tests/invariants/__init__.py
# CANONICAL — the source of truth for which tests block CI

BLOCKING_INVARIANTS = [
    "INV-001", "INV-002", "INV-003", "INV-004",  # Security
    "INV-005", "INV-006", "INV-007",               # Redaction + purge
    "INV-008", "INV-009", "INV-010", "INV-011",    # Forget completeness
    "INV-012", "INV-013",                           # Forget audit
    "INV-014", "INV-015",                           # Citation validity
    "INV-016", "INV-017", "INV-018", "INV-019",    # Retrieval math
    "INV-020", "INV-021", "INV-022",               # Ingestion
    "INV-023", "INV-024", "INV-025",               # Failure handling
    "INV-026", "INV-027", "INV-028", "INV-029", "INV-030",  # Config hygiene
]

# Any test marked @invariant("INV-XXX") that fails blocks the PR merge.
# Tests NOT in BLOCKING_INVARIANTS are informational only.
```

---

### Addendum F — SLO Definitions & Alert Thresholds

```toml
# memex/config/slos.toml
# CANONICAL — do not duplicate these values anywhere else

[slo_001_idle_cpu]
metric                 = "daemon_idle_cpu_pct"
target                 = 1.0
alert_threshold        = 5.0
measurement_window_sec = 60

[slo_002_fts_latency]
metric                 = "fts_search_p95_ms"
target                 = 50
alert_threshold        = 200
corpus_size_chunks     = 1_000_000

[slo_003_vector_latency]
metric                 = "vector_search_p95_ms"
target                 = 200
alert_threshold        = 500
corpus_size_chunks     = 1_000_000

[slo_004_hybrid_latency]
metric                 = "hybrid_retrieval_p95_ms"
target                 = 500
alert_threshold        = 1000
corpus_size_chunks     = 1_000_000

[slo_005_llm_first_token]
metric                 = "llm_first_token_p50_ms"
target                 = 3000
alert_threshold        = 10000
hardware               = "cpu"

[slo_006_ingestion_cpu]
metric                 = "ingestion_avg_ms"
target                 = 30_000
alert_threshold        = 120_000
hardware               = "cpu"

[slo_007_ingestion_gpu]
metric                 = "ingestion_avg_ms"
target                 = 10_000
alert_threshold        = 30_000
hardware               = "gpu"

[slo_010_forget_latency]
metric                 = "forget_single_doc_ms"
target                 = 5000
alert_threshold        = 30_000
```

---

## 20. Glossary

| Term | Definition |
|---|---|
| **BM25** | Best Match 25 — the ranking algorithm used by SQLite FTS5 for keyword search |
| **Chunk** | A text segment derived from a document, sized for embedding; the atomic retrieval unit |
| **Chroma** | Embedded vector database used to store and query chunk embeddings |
| **Clean content** | Parser output: normalized UTF-8 text, redacted of secrets, ready for chunking |
| **Combined score** | The weighted sum of vector, keyword, graph, and temporal scores for a chunk |
| **Daemon** | The background process that runs ingestors, workers, and the API server |
| **Embedding** | A fixed-length floating-point vector representing the semantic content of a chunk |
| **Entity** | A named real-world object extracted by NER (person, org, place, concept) |
| **FTS5** | SQLite's Full-Text Search module (version 5), supporting BM25 ranking |
| **Forget** | The 10-step protocol to permanently remove a document from all four stores |
| **Hybrid retrieval** | Fusion of four signals: vector similarity, keyword BM25, graph traversal, temporal decay |
| **Ingestor** | A thread that watches one source type and emits `RawDocument` objects to the queue |
| **Invariant** | A system property that must always hold; tested in CI and blocking on failure |
| **KuzuDB** | Embedded graph database used to store and query entity relationships |
| **Loopback** | The `127.0.0.1` / `localhost` network interface; all MEMEX API traffic stays here |
| **NER** | Named Entity Recognition — the spaCy process of identifying entities in text |
| **Ollama** | The local LLM runtime that serves both embedding and chat completion models |
| **ParsedDocument** | The canonical output of the PARSE pillar; contains `clean_content` and metadata |
| **Priority queue** | The bounded queue between ingestors and workers; items have CRITICAL/HIGH/NORMAL/LOW tiers |
| **RawDocument** | The canonical output of an ingestor; contains raw bytes, checksum, source metadata |
| **Redactor** | The component that strips secret patterns from `clean_content` before storage |
| **Re-embed migration** | The protocol for regenerating all embeddings when the embedding model is changed |
| **Relation** | A LLM-extracted directional predicate between two entities (subject → predicate → object) |
| **SLO** | Service Level Objective — a target performance metric with an alert threshold |
| **SSOT** | Single Source of Truth — this document and its Addenda are the SSOT for MEMEX's design |
| **Temporal decay** | Exponential score reduction applied to older documents during retrieval |
| **TTL** | Time-to-live — the period after which a piece of data is purged or nulled |
| **Worker pool** | A bounded thread pool that processes `RawDocument` items from the priority queue |

---

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 END OF DOCUMENT
 MEMEX Engineering Design Document v2.0.0
 Status: APPROVED — Single Source of Truth
 Any change to this document requires a version bump and 
 update to the DOCUMENT CONTROL BLOCK at the top.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```
