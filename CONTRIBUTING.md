# Contributing to MEMEX

First off, thank you for considering contributing to MEMEX. It's people like you that make MEMEX such a great tool.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Project Architecture](#project-architecture)
- [Coding Standards](#coding-standards)
- [Commit Guidelines](#commit-guidelines)
- [Pull Request Process](#pull-request-process)
- [Testing Requirements](#testing-requirements)
- [Configuration SSOT Rules](#configuration-ssot-rules)
- [Adding New Features](#adding-new-features)
- [Bug Reports](#bug-reports)
- [Release Process](#release-process)

---

## Code of Conduct

- Be respectful and constructive
- Focus on what is best for the community
- Keep discussions on-topic

---

## Getting Started

### Prerequisites

- Python 3.11+ (3.13 recommended)
- Ollama installed and running
- Git

### Fork and Clone

```bash
# Fork the repo on GitHub, then:
git clone https://github.com/YOUR_USERNAME/MEMEX.git
cd MEMEX
pip install -e ".[dev]"
```

### Verify Setup

```bash
memex init
memex doctor
pytest tests/ -v
```

All 150 tests should pass.

---

## Development Setup

### Install Dependencies

```bash
pip install -e ".[dev]"
```

This installs:
- All runtime dependencies
- `pytest`, `pytest-asyncio`, `pytest-cov` — testing
- `ruff` — linting and formatting
- `mypy` — type checking

### Start Ollama

```bash
ollama serve
ollama pull nomic-embed-text
ollama pull llama3:8b
```

### Run Tests

```bash
# All tests
pytest tests/ -v

# Specific test categories
pytest tests/invariants/ -v       # 30 invariant tests
pytest tests/unit/ -v             # Component tests
pytest tests/integration/ -v      # End-to-end tests

# With coverage
pytest tests/ --cov=memex --cov-report=term-missing
```

### Lint and Format

```bash
ruff check memex/ tests/          # Lint
ruff format memex/ tests/         # Format
mypy memex/ --ignore-missing-imports  # Type check
```

---

## Project Architecture

MEMEX follows a strict **six-pillar** architecture. Understanding this is essential for contributing:

```
INGEST → PARSE → INDEX → RECALL → ANSWER
                                      ↕
                                   PROTECT
```

| Pillar | Package | Responsibility |
|--------|---------|---------------|
| INGEST | `memex/ingest/` | Passive capture from sources |
| PARSE | `memex/parse/` | Content-type normalization |
| INDEX | `memex/index/` | Multi-store indexing |
| RECALL | `memex/recall/` | Hybrid retrieval |
| ANSWER | `memex/answer/` | RAG chat engine |
| PROTECT | `memex/protect/` | Redaction, forget, purge |

### Data Flow Contracts

The canonical interfaces between pillars are defined in `memex/config/settings.py`:

- `RawDocument` — INGEST → PARSE boundary
- `ParsedDocument` — PARSE → INDEX boundary
- `Chunk` — Atomic retrieval unit
- `RetrievalResult` — RECALL → ANSWER boundary
- `ConversationTurn` — Chat history

### Storage Layer

The `memex/db/` package provides the storage abstraction:

- `SQLiteDatabase` — Relational data, FTS5, connection pool
- `ChromaStore` — Vector embeddings (HNSW cosine)
- `KuzuGraph` — Entity-relationship graph (Cypher)

---

## Coding Standards

### Python Style

- **PEP 8** with 100-character line length (enforced by `ruff`)
- **Type hints** on all function signatures (enforced by `mypy --strict`)
- **Docstrings** on all public functions and classes (Google style)
- **No placeholders**: No `pass`, no `TODO`, no `NotImplementedError` in production code
- **No stubs**: Every function must have a real body with real logic

### Naming Conventions

| Type | Convention | Example |
|------|-----------|---------|
| Modules | `snake_case` | `hybrid_retrieval.py` |
| Classes | `PascalCase` | `HybridRetriever` |
| Functions | `snake_case` | `retrieve(query, top_k)` |
| Constants | `UPPER_SNAKE` | `DEFAULT_TOP_K` |
| Private methods | `_leading_underscore` | `_vector_signal()` |
| TOML keys | `snake_case` | `vector_weight` |

### Import Order

```python
# Standard library
from __future__ import annotations
import os
from pathlib import Path

# Third-party
import httpx
from fastapi import FastAPI

# First-party
from ..config.settings import Settings, get_settings
from ..observability.logging import get_logger
```

### Error Handling

```python
# GOOD: Specific exception with structured logging
try:
    result = self._chroma.query_vectors(embedding, n_results=10)
except Exception as e:
    logger.error("vector_query_failed", error=str(e))
    return {}

# BAD: Bare except, no logging
try:
    result = self._chroma.query_vectors(embedding, n_results=10)
except:
    pass
```

### Logging

Use structured logging via the `get_logger` helper:

```python
from ..observability.logging import get_logger

logger = get_logger("module.name")

logger.info("operation_completed", duration_ms=elapsed, count=len(results))
logger.error("operation_failed", error=str(e), document_id=doc_id)
logger.warning("slow_operation", duration_ms=elapsed, threshold_ms=1000)
```

---

## Commit Guidelines

### Format

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Types

| Type | Usage |
|------|-------|
| `feat` | New feature |
| `fix` | Bug fix |
| `refactor` | Code restructuring without behavior change |
| `test` | Adding or modifying tests |
| `docs` | Documentation changes |
| `chore` | Build, CI, or dependency changes |
| `perf` | Performance improvement |

### Scopes

Use pillar or package names: `ingest`, `parse`, `index`, `recall`, `answer`, `protect`, `api`, `db`, `config`, `tui`, `web`, `daemon`, `ci`

### Examples

```
feat(recall): add date range filtering to hybrid retrieval
fix(protect): handle empty content in entropy heuristic
refactor(db): extract FTS5 query escaping to standalone function
test(index): add chunker edge case tests for code content
docs(api): document SSE streaming endpoint parameters
chore(ci): pin Python 3.13 in CI pipeline
```

---

## Pull Request Process

### Before Submitting

1. **All tests pass**: `pytest tests/ -v` (150/150)
2. **Linting clean**: `ruff check memex/ tests/`
3. **Type checks pass**: `mypy memex/ --ignore-missing-imports`
4. **Invariant tests pass**: `pytest tests/invariants/ -v` (30/30)
5. **New code has tests**: Every new function needs a test
6. **No SSOT violations**: Config values come from addenda TOML files only

### PR Template

```markdown
## Description
[What does this PR do?]

## Type of Change
- [ ] feat: New feature
- [ ] fix: Bug fix
- [ ] refactor: Code restructuring
- [ ] test: Test changes
- [ ] docs: Documentation
- [ ] chore: Build/CI

## Pillar Affected
- [ ] INGEST
- [ ] PARSE
- [ ] INDEX
- [ ] RECALL
- [ ] ANSWER
- [ ] PROTECT
- [ ] API
- [ ] DB
- [ ] Config
- [ ] Other: ___

## Testing
- [ ] All 150 existing tests pass
- [ ] New tests added for new code
- [ ] Invariant tests verified
- [ ] Manual testing performed

## Checklist
- [ ] No `TODO`, `pass`, or `NotImplementedError` in production code
- [ ] All config values from addenda TOML (SSOT)
- [ ] Structured logging used (not print statements)
- [ ] Type hints on all public functions
- [ ] Docstrings on all public functions/classes
```

### Review Criteria

PRs are reviewed against:

1. **Correctness**: Does it do what it claims?
2. **Architecture fit**: Does it belong in the right pillar?
3. **SSOT compliance**: Are config values from addenda?
4. **Test coverage**: Are new paths tested?
5. **Security**: Does it maintain the trust model?
6. **Performance**: Does it respect SLO targets?

---

## Testing Requirements

### Invariant Tests

The 30 invariant tests (`INV-001` through `INV-030`) are **blocking** — they must always pass. If your change breaks an invariant, the PR will not be merged.

Key invariants:

| ID | Category | What it enforces |
|----|----------|-----------------|
| INV-001 to INV-005 | Security | Loopback-only, no remote connections |
| INV-006 to INV-012 | Redaction | All 7 patterns work, entropy heuristic, innocuous text preserved |
| INV-013 to INV-018 | Forget | All stores cleared, audit log, orphan cleanup |
| INV-019 to INV-022 | Retrieval | Weights sum to 1.0, decay in [0,1], score ordering |
| INV-023 to INV-025 | Ingestion | Queue limits, dedup, priority ordering |
| INV-026 to INV-030 | Config | All addenda parse, no duplicates, all files exist |

### Writing Tests

```python
# Unit test example
def test_chunker_respects_prose_budget():
    """INV-C: Chunker uses prose token budget from chunking.toml."""
    chunker = SmartChunker()
    chunks = chunker.chunk("doc-id", long_prose_text, ContentType.PLAIN)
    for chunk in chunks:
        assert chunk.token_count <= 450  # budget + overlap tolerance

# Invariant test example
@pytest.mark.invariant
def test_retrieval_weights_sum_to_one():
    """INV-019: Retrieval weights must sum to exactly 1.0."""
    weights = load_retrieval_weights()
    hw = weights["hybrid_retrieval"]
    total = hw["vector_weight"] + hw["keyword_weight"] + hw["graph_weight"] + hw["temporal_weight"]
    assert total == 1.0, f"Weight sum is {total}, expected 1.0"
```

### Test Fixtures

Use the shared fixtures in `tests/conftest.py`:

```python
def test_my_feature(sqlite_db):
    """Uses the ephemeral SQLite fixture."""
    sqlite_db.insert_document(...)
    results = sqlite_db.list_documents()
    assert len(results) == 1
```

---

## Configuration SSOT Rules

### The Rule

**All operational constants must be defined in addenda TOML files.** Never hardcode values in Python.

### Addenda Files

| File | What goes here |
|------|---------------|
| `retrieval_weights.toml` | Retrieval signal weights, decay parameters, top-k limits |
| `chunking.toml` | Token budgets per content type, context window size |
| `redaction_patterns.toml` | Regex patterns, entropy thresholds, excluded domains |
| `retention.toml` | TTLs, queue depth, purge intervals, retry limits |
| `slos.toml` | SLO targets and alert thresholds |

### Loading Pattern

```python
from ..config.settings import load_retrieval_weights

# GOOD: Load from addenda
weights = load_retrieval_weights()
vector_weight = weights["hybrid_retrieval"]["vector_weight"]

# BAD: Hardcoded
vector_weight = 0.40  # ← NEVER do this
```

### Adding a New Config Value

1. Add the value to the appropriate addenda TOML file
2. Add a loader function in `memex/config/settings.py` if needed
3. Load the value in the consuming module
4. Add an invariant test to verify it exists and is valid

---

## Adding New Features

### New Ingestor

1. Create a new file in `memex/ingest/`
2. Extend `BaseIngestor` from `memex/ingest/base.py`
3. Implement `start()` and `stop()` methods
4. Push `RawDocument` instances to the queue
5. Register in `memex/daemon.py` → `start_ingestors()`
6. Add unit tests + invariant tests

### New Parser

1. Create a new file in `memex/parse/`
2. Extend `BaseParser` from `memex/parse/base.py`
3. Implement `parse(document_id, raw_bytes, filename)` → `ParsedDocument`
4. Register in `memex/parse/dispatcher.py` → content-type mapping
5. Add unit tests with sample content

### New Redaction Pattern

1. Add the pattern entry to `memex/config/redaction_patterns.toml`
2. Include `name`, `pattern`, `replacement`, `test_fixture`, `innocuous`
3. The `Redactor` automatically loads all patterns from the TOML file
4. Add tests: one for the fixture (should redact), one for innocuous (should not)

### New API Endpoint

1. Add the route in the appropriate `memex/api/routes/*.py` file
2. Use `_run_sync(func, *args, **kwargs)` via `run_in_executor` for sync operations
3. Document with a docstring
4. Add integration test in `tests/integration/test_api.py`
5. Update this README's API Reference table

---

## Bug Reports

When filing a bug report, please include:

1. **MEMEX version**: `python -c "import memex; print(memex.__version__)"`
2. **Python version**: `python --version`
3. **OS**: macOS / Linux / Windows + version
4. **Ollama status**: `curl http://localhost:11434/api/tags`
5. **`memex doctor` output**: Full output of the health check
6. **Relevant logs**: From `~/.memex/logs/`
7. **Steps to reproduce**: Minimal, reproducible steps
8. **Expected vs actual behavior**

---

## Release Process

1. Update `__version__` in `memex/__init__.py` and `pyproject.toml`
2. Update `CHANGELOG.md` with the new version entry
3. Ensure all 150 tests pass
4. Ensure CI pipeline is green
5. Create a git tag: `git tag v2.x.x`
6. Push tag: `git push origin v2.x.x`
7. Create GitHub release with changelog notes

---

Thank you for contributing to MEMEX! 🧠
