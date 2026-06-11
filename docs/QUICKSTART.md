# MEMEX Quick Reference Card

> Keep this handy for daily MEMEX usage.

---

## CLI Commands

```bash
memex init                # First-time setup
memex doctor              # Health check
memex start               # Start daemon
memex status              # Check daemon status
memex chat                # Launch TUI
```

## API Quick Reference

```bash
# Health
curl http://localhost:7700/api/health

# Search
curl "http://localhost:7700/api/memory/search?q=your+query&limit=10"

# Chat
curl -X POST http://localhost:7700/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What did I work on last week?"}'

# Stream chat
curl -N http://localhost:7700/api/chat/stream?message=hello

# Timeline
curl "http://localhost:7700/api/memory/timeline?limit=20"

# Forget
curl -X DELETE http://localhost:7700/api/memory/{document_id}

# Stats
curl http://localhost:7700/api/stats

# Entities
curl "http://localhost:7700/api/graph/entities?q=Python"

# Relations
curl "http://localhost:7700/api/graph/relations?entity=Python"
```

## File Locations

| Path | Purpose |
|------|---------|
| `~/.memex/config.toml` | User configuration |
| `~/.memex/data/memex.db` | SQLite database |
| `~/.memex/data/chroma/` | ChromaDB vectors |
| `~/.memex/data/kuzu/` | KuzuDB graph |
| `~/.memex/logs/` | Application logs |

## Environment Variables

```bash
MEMEX_DATA_DIR=~/.memex          # Data directory
MEMEX_LOG_LEVEL=INFO             # Log level (DEBUG, INFO, WARN, ERROR)
MEMEX_API_PORT=7700              # API port
MEMEX_OLLAMA_URL=http://127.0.0.1:11434  # Ollama URL
```

## Docker

```bash
docker compose up -d              # Start
docker compose logs -f memex      # Logs
docker compose down               # Stop
docker compose restart            # Restart
```

## Testing

```bash
pytest tests/                     # All tests
pytest tests/invariants/ -v       # 30 invariants
pytest tests/unit/ -v             # Unit tests
pytest tests/integration/ -v      # Integration tests
pytest tests/ --cov=memex         # With coverage
pytest -k "test_name" -v          # Specific test
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Command not found | `pip install -e .` |
| Ollama not reachable | `ollama serve` |
| Missing models | `ollama pull nomic-embed-text && ollama pull llama3:8b` |
| Permission denied | `chmod 700 ~/.memex` |
| Port in use | Change `api_port` in config |
| Slow responses | Check Ollama has ≥4 GB RAM |

## Key Weights

| Signal | Weight |
|--------|--------|
| Vector | 0.40 |
| Keyword | 0.30 |
| Graph | 0.20 |
| Temporal | 0.10 |

## Chunk Budgets

| Type | Tokens |
|------|--------|
| Prose | 400 |
| Code | 300 |
| Email | 200 |
| PDF | 400 |
