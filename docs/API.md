# MEMEX API Documentation

> Complete REST API reference for MEMEX v2.0.0
> Base URL: `http://127.0.0.1:7700`

---

## General

### Authentication

None required. The API is bound to `127.0.0.1` and only accessible from the local machine.

### Content Type

All request/response bodies use `application/json` unless noted otherwise.

### Error Responses

All errors follow a consistent format:

```json
{
    "detail": "Human-readable error message"
}
```

| Status Code | Meaning |
|-------------|---------|
| 200 | Success |
| 400 | Bad request (invalid parameters) |
| 403 | Forbidden (non-loopback request) |
| 404 | Resource not found |
| 500 | Internal server error |

---

## Chat

### POST `/api/chat`

Send a message and receive a cited response.

**Request:**

```json
{
    "message": "How did I configure the CI pipeline?",
    "session_id": "optional-session-uuid"
}
```

**Response:**

```json
{
    "response": "Based on your notes, the CI pipeline uses GitHub Actions [Source 1] with four stages [Source 2]...",
    "session_id": "uuid-of-session",
    "sources": [
        {
            "chunk_id": "uuid",
            "document_id": "uuid",
            "content": "...",
            "score": 0.8542,
            "source_type": "filesystem",
            "source_path": "/home/user/project/.github/workflows/ci.yml"
        }
    ]
}
```

### GET `/api/chat/stream`

Server-Sent Events streaming chat endpoint.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `message` | string | Yes | The chat message |
| `session_id` | string | No | Continue existing session |

**Response:** `text/event-stream`

```
data: {"token": "Based"}
data: {"token": " on"}
data: {"token": " your"}
...
data: [DONE]
```

### GET `/api/chat/sessions`

List all chat sessions.

**Response:**

```json
[
    {
        "session_id": "uuid",
        "created_at": "2025-01-15T10:30:00",
        "turn_count": 5,
        "last_message": "How do I..."
    }
]
```

### GET `/api/chat/sessions/{session_id}`

Get full history for a session.

**Response:**

```json
{
    "session_id": "uuid",
    "turns": [
        {
            "role": "user",
            "content": "What did I work on?",
            "sources_cited": []
        },
        {
            "role": "assistant",
            "content": "You worked on...",
            "sources_cited": ["chunk-uuid-1", "chunk-uuid-2"]
        }
    ]
}
```

### DELETE `/api/chat/sessions/{session_id}`

Delete a chat session and all its turns.

**Response:**

```json
{
    "deleted": true,
    "session_id": "uuid"
}
```

---

## Memory

### GET `/api/memory/search`

Hybrid search across all indexed content.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `q` | string | required | Search query |
| `limit` | int | 20 | Max results (max 50) |
| `after` | ISO date | null | Only results after this date |
| `before` | ISO date | null | Only results before this date |
| `source_type` | string | null | Filter by source (filesystem, browser, terminal, clipboard) |

**Response:**

```json
{
    "results": [
        {
            "chunk_id": "uuid",
            "document_id": "uuid",
            "content": "Relevant text chunk...",
            "score": 0.8542,
            "vector_score": 0.92,
            "keyword_score": 0.78,
            "graph_score": 0.0,
            "temporal_score": 0.99,
            "source_type": "filesystem",
            "source_path": "/path/to/file.md",
            "captured_at": "2025-01-10T14:30:00",
            "citation_index": 1
        }
    ],
    "total": 15,
    "query": "deploy pipeline"
}
```

### GET `/api/memory/timeline`

Chronological listing of ingested documents.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 50 | Max documents |
| `offset` | int | 0 | Pagination offset |
| `source_type` | string | null | Filter by source |

**Response:**

```json
{
    "documents": [
        {
            "id": "uuid",
            "source_type": "filesystem",
            "source_path": "/path/to/file.py",
            "status": "INDEXED",
            "word_count": 450,
            "captured_at": "2025-01-15T10:00:00"
        }
    ],
    "total": 1234,
    "offset": 0,
    "limit": 50
}
```

### GET `/api/memory/{document_id}`

Get full details for a specific document.

**Response:**

```json
{
    "id": "uuid",
    "source_type": "filesystem",
    "source_path": "/path/to/file.py",
    "content_type": "code",
    "status": "INDEXED",
    "word_count": 450,
    "chunk_count": 3,
    "captured_at": "2025-01-15T10:00:00",
    "chunks": [
        {
            "id": "chunk-uuid",
            "content": "...",
            "token_count": 280,
            "chunk_index": 0,
            "total_chunks": 3
        }
    ]
}
```

### DELETE `/api/memory/{document_id}`

Hard forget — complete 10-step deletion across all stores.

**Response:**

```json
{
    "success": true,
    "document_id": "uuid",
    "chunks_deleted": 3,
    "stores_checked": ["chroma", "sqlite", "kuzu"]
}
```

---

## Graph

### GET `/api/graph/entities`

Search for entities in the knowledge graph.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `q` | string | required | Entity name search |
| `limit` | int | 20 | Max results |

**Response:**

```json
{
    "entities": [
        {
            "id": "uuid",
            "name": "Python",
            "type": "TECHNOLOGY",
            "mention_count": 42
        }
    ]
}
```

### GET `/api/graph/relations`

Get relationships for a specific entity.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `entity` | string | required | Entity name |
| `limit` | int | 20 | Max relations |

**Response:**

```json
{
    "entity": "Python",
    "relations": [
        {
            "target_entity": "FastAPI",
            "relation_type": "RELATED_TO",
            "confidence": 0.85,
            "source_document": "/path/to/file.py"
        }
    ]
}
```

---

## System

### GET `/api/health`

System health check.

**Response:**

```json
{
    "status": "healthy",
    "version": "2.0.0",
    "uptime_seconds": 86400,
    "stores": {
        "sqlite": "ok",
        "chroma": "ok",
        "kuzu": "ok",
        "ollama": "ok"
    },
    "models": {
        "embed": "nomic-embed-text",
        "chat": "llama3:8b"
    }
}
```

### GET `/api/stats`

Ingestion and indexing metrics.

**Response:**

```json
{
    "documents": {
        "total": 1234,
        "indexed": 1200,
        "pending": 15,
        "failed": 19
    },
    "chunks": {
        "total": 15678,
        "embedded": 15600
    },
    "entities": {
        "total": 890,
        "relations": 234
    },
    "sources": {
        "filesystem": 800,
        "browser": 300,
        "terminal": 100,
        "clipboard": 34
    }
}
```

### POST `/api/reindex`

Trigger a full re-index of all documents.

**Response:**

```json
{
    "status": "started",
    "message": "Re-indexing 1234 documents"
}
```

### GET `/api/models`

List active embedding models.

**Response:**

```json
{
    "active_model": {
        "name": "nomic-embed-text",
        "version": "1.5",
        "collection": "memex_vectors_v1",
        "vector_count": 15600
    },
    "available_models": [
        {
            "name": "nomic-embed-text",
            "version": "1.5",
            "registered_at": "2025-01-01T00:00:00"
        }
    ]
}
```

### GET `/api/logs/stream`

SSE stream of application logs.

**Response:** `text/event-stream`

```
data: {"log": "2025-01-15 10:30:00 [INFO] document_indexed document_id=abc123"}
data: {"log": "2025-01-15 10:30:01 [INFO] retrieval_complete query=test result_count=5"}
...
```

---

*This API documentation was generated for MEMEX v2.0.0.*
