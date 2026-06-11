# Architecture Decision Records (ADRs)

> Key design decisions made during MEMEX v2.0.0 development and the rationale behind them.

---

## ADR-001: Local-First Architecture

**Decision**: All data processing and storage happens on the user's machine. No cloud services.

**Rationale**:
- Personal knowledge contains sensitive information (API keys, private thoughts, work documents)
- Users should own every byte of their data
- Eliminates privacy concerns, subscription costs, and internet dependency
- Ollama provides sufficient LLM quality for local inference

**Consequences**:
- Requires local GPU/CPU for embedding and inference
- No collaborative features by default
- Ollama must be installed and running

---

## ADR-002: SQLite + ChromaDB + KuzuDB Triple Store

**Decision**: Use three separate storage engines instead of one.

**Rationale**:
- **SQLite**: Proven reliability, WAL mode for concurrency, FTS5 for full-text search, no server process
- **ChromaDB**: Purpose-built for vector similarity with HNSW, metadata filtering, simple API
- **KuzuDB**: Embedded graph database with Cypher support, no server process, complements relational data
- No single database excels at all three access patterns (relational, vector, graph)

**Consequences**:
- Three stores to manage, back up, and delete from
- Forget protocol must touch all three (10-step protocol)
- Migration complexity when changing schemas
- Each store is independently healthy/unhealthy

---

## ADR-003: TOML Addenda as SSOT

**Decision**: All operational constants live in versioned TOML addenda files. Never duplicate in code.

**Rationale**:
- Prevents magic numbers scattered across 75 Python files
- Single place to audit, review, and change parameters
- Enables config validation via invariant tests
- TOML is human-readable and has native Python support

**Consequences**:
- Every module must load its config from the appropriate addenda
- Adding a constant requires touching a TOML file + test
- Config changes don't require code changes

---

## ADR-004: Four-Signal Hybrid Retrieval

**Decision**: Fuse vector similarity, keyword search, graph traversal, and temporal decay with fixed weights.

**Rationale**:
- No single retrieval method covers all use cases
- Vector: semantic similarity, handles paraphrasing
- Keyword: exact term matching, handles technical terms
- Graph: entity-based connections, handles "what relates to X"
- Temporal: recency bias, handles "what did I work on recently"
- Fixed weights (0.40/0.30/0.20/0.10) provide predictable behavior

**Consequences**:
- Weights may need tuning for different use cases
- Graph signal requires entity extraction quality
- Temporal signal may undervalue older but important knowledge

---

## ADR-005: Passive Ingestion (No Manual Curation)

**Decision**: Users never need to manually add or organize content.

**Rationale**:
- Manual curation creates friction and reduces adoption
- Digital exhaust (files, browser, terminal, clipboard) already contains valuable knowledge
- Automatic capture ensures nothing is missed
- Deduplication handles repeat content

**Consequences**:
- May capture noise (log files, temporary files)
- Requires exclusion rules for sensitive sources
- Users may need to trust the filtering logic

---

## ADR-006: Loopback-Only API

**Decision**: API binds to `127.0.0.1` exclusively. No network exposure.

**Rationale**:
- MEMEX stores potentially sensitive personal data
- Network exposure would create attack surface
- Local-only access is sufficient for all interfaces (TUI, Web UI, CLI)
- Docker also binds to `127.0.0.1:7700:7700`

**Consequences**:
- Cannot access MEMEX from other devices on the network
- Remote access requires SSH tunneling
- API testing must account for middleware allowlist

---

## ADR-007: 10-Step Atomic Forget Protocol

**Decision**: Hard delete is a 10-step process across all stores with verification and audit logging.

**Rationale**:
- GDPR and privacy best practices require complete deletion
- Partial deletion (e.g., only SQLite) leaks data through other stores
- Audit log provides accountability and debugging capability
- Idempotent design handles retry scenarios

**Consequences**:
- Forget is slower than simple DELETE
- Requires touching all three stores
- Partial failures must be handled gracefully
- Audit log grows over time

---

## ADR-008: ThreadPoolExecutor Over Raw Threads

**Decision**: Use `ThreadPoolExecutor` for the worker pool instead of raw `threading.Thread`.

**Rationale**:
- Built-in queue management and future tracking
- Proper shutdown semantics (`shutdown(wait=False)`)
- Named threads for debugging (`thread_name_prefix="memex-worker"`)
- Standard library, no additional dependencies

**Consequences**:
- Workers are threads, not processes (GIL implications for CPU-bound work)
- Embedding calls to Ollama release the GIL (I/O bound)
- Worker count is configurable (default: 4)

---

## ADR-009: 3-Strategy Code Parser Fallback

**Decision**: Code parsing uses a 3-strategy fallback chain: tree-sitter → regex → line-based.

**Rationale**:
- `tree-sitter-languages` has no Python 3.13 wheel
- Tree-sitter core works, but language packs may be missing
- Regex-based splitting handles common patterns (functions, classes)
- Line-based splitting always works as a last resort

**Consequences**:
- Code parsing quality varies by language
- Tree-sitter provides best results when available
- The `treesitter_used` flag tracks which strategy was used

---

## ADR-010: Shannon Entropy for Unknown Secret Detection

**Decision**: Use Shannon entropy (threshold 4.5 bits/char, min 20 chars) to detect secrets that don't match known patterns.

**Rationale**:
- Known regex patterns can't catch every secret format
- API keys, tokens, and passwords have high entropy
- Context window checking (30 chars) for key=/secret=/password= words reduces false positives
- Entropy is a well-established heuristic for secret detection

**Consequences**:
- May produce false positives on high-entropy non-secret strings (UUIDs, base64 data)
- Context window mitigates but doesn't eliminate false positives
- Threshold of 4.5 was chosen to balance sensitivity vs. specificity

---

*These ADRs are living documents. When making a significant architectural change, add a new ADR or update an existing one.*
