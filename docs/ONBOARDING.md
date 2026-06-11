# Developer Onboarding Guide

> Everything you need to know to start contributing to MEMEX.

---

## 30-Minute Setup

### Step 1: Clone and Install (5 min)

```bash
git clone https://github.com/knarayanareddy/MEMEX.git
cd MEMEX
pip install -e ".[dev]"
```

### Step 2: Install Ollama (5 min)

```bash
# macOS / Linux
curl -fsSL https://ollama.com/install.sh | sh
ollama pull nomic-embed-text
ollama pull llama3:8b
```

### Step 3: Initialize (2 min)

```bash
memex init      # Creates ~/.memex/ with default config
memex doctor    # Verify everything works
```

### Step 4: Run Tests (5 min)

```bash
pytest tests/ -v
```

All 150 tests should pass.

### Step 5: Run the Daemon (5 min)

```bash
memex start
```

In another terminal:
```bash
memex chat      # TUI
# or
curl http://localhost:7700/api/health
```

### Step 6: Explore the Code (8 min)

Start with these files in order:

1. `memex/__init__.py` — Version info
2. `memex/config/settings.py` — All data contracts and config loaders
3. `memex/daemon.py` — The orchestrator (entry point for understanding the pipeline)
4. `memex/ingest/queue.py` — How documents enter the system
5. `memex/parse/dispatcher.py` — How parsing is routed
6. `memex/recall/hybrid_retrieval.py` — The retrieval engine
7. `memex/protect/redactor.py` — How secrets are scrubbed
8. `memex/api/app.py` — How the API is wired

---

## Architecture Overview

MEMEX has a strict six-pillar architecture:

```
INGEST → PARSE → INDEX → RECALL → ANSWER
                                      ↕
                                   PROTECT
```

### Key Principles

1. **Data contracts define boundaries** — `RawDocument`, `ParsedDocument`, `Chunk`, `RetrievalResult`
2. **Config comes from TOML** — Never hardcode values; use addenda loaders
3. **Every function has real logic** — No `pass`, no `TODO`, no `NotImplementedError`
4. **All tests must pass** — 30 invariant tests are blocking

---

## Common Tasks

### Add a new content parser

1. Create `memex/parse/my_parser.py` extending `BaseParser`
2. Implement `parse(document_id, raw_bytes, filename) -> ParsedDocument`
3. Register in `memex/parse/dispatcher.py`'s extension mapping
4. Add tests in `tests/unit/test_parsers.py`

### Add a new API endpoint

1. Add the route in the appropriate `memex/api/routes/*.py`
2. Use `_run_sync(func, *args)` for all sync operations
3. Add integration test in `tests/integration/test_api.py`

### Add a new redaction pattern

1. Add to `memex/config/redaction_patterns.toml` (SSOT)
2. Include: `name`, `pattern`, `replacement`, `test_fixture`, `innocuous`
3. Redactor auto-loads all patterns — no code change needed
4. Add invariant test in `tests/invariants/test_redaction.py`

### Add a new config value

1. Add to the appropriate TOML addendum file
2. Load via the existing loader in `settings.py`
3. Add invariant test verifying it exists and is valid

---

## Code Navigation Map

```
Start here ───────→ memex/__main__.py (CLI)
                    │
                    ├── memex init ──→ __main__.cmd_init()
                    ├── memex doctor ──→ __main__.cmd_doctor()
                    ├── memex start ──→ memex/daemon.py → MEMEXDaemon.run()
                    │                      │
                    │                      ├── ingest/ (4 ingestors)
                    │                      ├── parse/ (6 parsers)
                    │                      ├── index/ (chunker, embedder, graph)
                    │                      ├── recall/ (hybrid retrieval)
                    │                      ├── answer/ (RAG chat)
                    │                      └── protect/ (redactor, forget)
                    │
                    ├── memex chat ──→ memex/tui/app.py (Textual TUI)
                    └── memex status ──→ HTTP GET /api/health
```

---

## Testing Strategy

```
tests/
├── invariants/       ← 30 blocking tests (must always pass)
│   ├── test_security.py       Network security
│   ├── test_redaction.py      Secret redaction
│   ├── test_forget.py         Hard delete
│   ├── test_retrieval.py      Retrieval weights
│   ├── test_ingestion.py      Queue behavior
│   └── test_config_hygiene.py Config SSOT
│
├── unit/             ← Component tests (fast, isolated)
│   ├── test_parsers.py        All 6 parsers
│   ├── test_chunker.py        Smart chunker
│   ├── test_redactor.py       Pattern + entropy
│   ├── test_sqlite.py         Schema, FTS5, migrations
│   ├── test_prompt.py         Citation extraction
│   └── test_production_fixes.py  Regression tests
│
└── integration/      ← End-to-end tests
    ├── test_pipeline.py       Full pipeline
    └── test_api.py            API endpoints
```

### Running Tests

```bash
pytest tests/                              # All 150 tests
pytest tests/invariants/ -v                # Invariant tests
pytest tests/unit/ -v                      # Unit tests
pytest tests/integration/ -v              # Integration tests
pytest tests/ -k "test_chunker" -v        # Specific tests
pytest tests/ --cov=memex --cov-report=term-missing  # With coverage
```

---

## Key Files Reference

| File | Why it matters |
|------|---------------|
| `memex/config/settings.py` | All data contracts (`RawDocument`, `Chunk`, etc.) and config loaders |
| `memex/daemon.py` | The orchestrator — connects all pillars |
| `memex/db/sqlite.py` | Schema, FTS5, connection pool, migrations |
| `memex/recall/hybrid_retrieval.py` | The 4-signal retrieval engine |
| `memex/protect/redactor.py` | Secret scrubbing before storage |
| `memex/protect/forget.py` | The 10-step atomic delete |
| `memex/api/app.py` | FastAPI factory with middleware |
| `memex/config/*.toml` | SSOT for all operational constants |

---

## Gotchas

1. **`RawDocument` needs `__lt__`** for `PriorityQueue` — it compares `priority.value`
2. **TestClient host is `"testclient"`** — must be in loopback allowlist
3. **FTS5 queries need escaping** — operators and special chars must be stripped
4. **SQLite `purge_raw_content(0)`** doesn't work because `datetime('now')` equals current time — set `captured_at` to past in tests
5. **Entity mentions have FK to chunks** — must insert chunk before mention
6. **All API routes must use `_run_sync`** — never block the event loop directly
7. **Config values come from TOML only** — hardcoded values are a code review rejection

---

*Welcome to MEMEX! 🧠*
