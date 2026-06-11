"""Integration tests for the API layer."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from memex.api.app import create_app
from memex.config.settings import Settings


@pytest.fixture
def test_client(tmp_path):
    """Create a test client with ephemeral database."""
    settings = Settings(data_dir=tmp_path)
    settings.ensure_directories()

    from memex.db.sqlite import SQLiteDatabase
    from memex.db.chroma import ChromaStore
    from memex.db.kuzu import KuzuGraph

    sqlite = SQLiteDatabase(db_path=tmp_path / "data" / "test.db", settings=settings)
    sqlite.run_migrations()

    chroma = ChromaStore(
        chroma_path=tmp_path / "data" / "chroma",
        collection_name="test_vectors",
        settings=settings,
    )

    kuzu = KuzuGraph(kuzu_path=tmp_path / "data" / "kuzu", settings=settings)

    app = create_app(
        settings=settings,
        sqlite=sqlite,
        chroma=chroma,
        kuzu=kuzu,
    )

    return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_200(self, test_client):
        response = test_client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "daemon_running" in data

    def test_health_has_stores(self, test_client):
        response = test_client.get("/api/health")
        data = response.json()
        assert "stores" in data


class TestStatsEndpoint:
    def test_stats_returns_200(self, test_client):
        response = test_client.get("/api/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "total_documents" in data["data"]


class TestMemoryEndpoints:
    def test_timeline_empty(self, test_client):
        response = test_client.get("/api/memory/timeline")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_get_nonexistent_document(self, test_client):
        response = test_client.get("/api/memory/nonexistent-id")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "DOCUMENT_NOT_FOUND"


class TestChatEndpoints:
    def test_list_sessions_empty(self, test_client):
        response = test_client.get("/api/chat/sessions")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_delete_nonexistent_session(self, test_client):
        response = test_client.delete("/api/chat/sessions/nonexistent")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False


class TestGraphEndpoints:
    def test_list_entities_empty(self, test_client):
        response = test_client.get("/api/graph/entities")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_list_relations_empty(self, test_client):
        response = test_client.get("/api/graph/relations")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
