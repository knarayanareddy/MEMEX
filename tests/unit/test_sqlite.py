"""Unit tests for SQLite database operations."""

import pytest

from memex.config.settings import DocumentStatus


class TestDocumentOperations:
    def test_insert_and_retrieve(self, sqlite_db):
        doc_id = sqlite_db.insert_document(
            source_type="filesystem",
            source_path="/test/doc.txt",
            raw_content=b"hello world",
            checksum="test_retrieve_1",
        )
        assert doc_id is not None

        doc = sqlite_db.get_document(doc_id)
        assert doc is not None
        assert doc["source_type"] == "filesystem"
        assert doc["source_path"] == "/test/doc.txt"
        assert doc["status"] == "PENDING"

    def test_update_status(self, sqlite_db):
        doc_id = sqlite_db.insert_document("fs", "/t", b"x", "stat_test_1")
        sqlite_db.update_document_status(doc_id, DocumentStatus.PARSED)

        doc = sqlite_db.get_document(doc_id)
        assert doc["status"] == "PARSED"

    def test_update_parsed_content(self, sqlite_db):
        doc_id = sqlite_db.insert_document("fs", "/t", b"x", "parse_test_1")
        sqlite_db.update_document_parsed(doc_id, "clean text", "plain", 2)

        doc = sqlite_db.get_document(doc_id)
        assert doc["clean_content"] == "clean text"
        assert doc["content_type"] == "plain"
        assert doc["word_count"] == 2

    def test_list_documents_pagination(self, sqlite_db):
        for i in range(10):
            sqlite_db.insert_document("fs", f"/t/{i}", b"x", f"page_test_{i}")

        page1 = sqlite_db.list_documents(limit=5, offset=0)
        page2 = sqlite_db.list_documents(limit=5, offset=5)
        assert len(page1) == 5
        assert len(page2) == 5
        assert page1[0]["id"] != page2[0]["id"]

    def test_list_documents_by_source(self, sqlite_db):
        sqlite_db.insert_document("browser", "/url1", b"x", "src_b_1")
        sqlite_db.insert_document("filesystem", "/file1", b"x", "src_f_1")

        browser_docs = sqlite_db.list_documents(source_type="browser")
        assert len(browser_docs) == 1
        assert browser_docs[0]["source_type"] == "browser"

    def test_purge_raw_content(self, sqlite_db):
        """Raw content is purged after TTL."""
        doc_id = sqlite_db.insert_document("fs", "/t", b"raw data", "purge_test_1")
        sqlite_db.update_document_parsed(doc_id, "clean", "plain", 1)

        # Manually set captured_at to 10 days ago
        with sqlite_db.connection() as conn:
            conn.execute(
                "UPDATE documents SET captured_at = datetime('now', '-10 days') WHERE id = ?",
                (doc_id,),
            )

        # Purge documents older than 7 days
        count = sqlite_db.purge_raw_content(7)
        assert count == 1

        doc = sqlite_db.get_document(doc_id)
        assert doc["raw_content"] is None
        assert doc["raw_purged_at"] is not None


class TestChunkOperations:
    def test_insert_and_get_chunks(self, sqlite_db):
        doc_id = sqlite_db.insert_document("fs", "/t", b"x", "chunk_test_1")

        c1 = sqlite_db.insert_chunk(doc_id, "chunk 1", 2, 0, 2, 0, 7)
        c2 = sqlite_db.insert_chunk(doc_id, "chunk 2", 2, 1, 2, 8, 15)

        chunks = sqlite_db.get_chunks_for_document(doc_id)
        assert len(chunks) == 2
        assert chunks[0]["chunk_index"] == 0
        assert chunks[1]["chunk_index"] == 1

    def test_delete_chunks(self, sqlite_db):
        doc_id = sqlite_db.insert_document("fs", "/t", b"x", "del_chunk_1")
        sqlite_db.insert_chunk(doc_id, "c1", 1, 0, 1, 0, 2)

        count = sqlite_db.delete_chunks_for_document(doc_id)
        assert count == 1

        chunks = sqlite_db.get_chunks_for_document(doc_id)
        assert len(chunks) == 0

    def test_update_chroma_id(self, sqlite_db):
        doc_id = sqlite_db.insert_document("fs", "/t", b"x", "chroma_test_1")
        chunk_id = sqlite_db.insert_chunk(doc_id, "c", 1, 0, 1, 0, 1)

        sqlite_db.update_chunk_chroma_id(chunk_id, "chroma_abc")
        chunk = sqlite_db.get_chunk_by_id(chunk_id)
        assert chunk["chroma_id"] == "chroma_abc"


class TestConversationOperations:
    def test_create_and_list_conversations(self, sqlite_db):
        sid = sqlite_db.create_conversation(title="Test Chat")
        assert sid is not None

        sessions = sqlite_db.list_conversations()
        assert len(sessions) == 1
        assert sessions[0]["title"] == "Test Chat"

    def test_add_turns(self, sqlite_db):
        sid = sqlite_db.create_conversation()
        sqlite_db.add_conversation_turn(sid, "user", "What is Python?")
        sqlite_db.add_conversation_turn(
            sid, "assistant", "Python is a language.",
            sources_cited=["chunk_1"],
        )

        history = sqlite_db.get_conversation_history(sid)
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"

    def test_delete_conversation(self, sqlite_db):
        sid = sqlite_db.create_conversation()
        sqlite_db.add_conversation_turn(sid, "user", "hi")

        success = sqlite_db.delete_conversation(sid)
        assert success

        sessions = sqlite_db.list_conversations()
        assert len(sessions) == 0


class TestStats:
    def test_get_stats(self, sqlite_db):
        sqlite_db.insert_document("filesystem", "/f1", b"x", "stat_f_1")
        sqlite_db.insert_document("browser", "/b1", b"x", "stat_b_1")

        stats = sqlite_db.get_stats()
        assert stats["total_documents"] == 2
        assert stats["by_source_type"]["filesystem"] == 1
        assert stats["by_source_type"]["browser"] == 1
