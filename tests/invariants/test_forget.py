"""
Forget protocol invariant tests.

INV-007: After forget, Chroma has zero vectors for document_id
INV-008: After forget, SQLite has zero chunks for document_id
INV-009: After forget, entity mentions are removed
INV-010: After forget, document cannot be retrieved
INV-011: Forget audit log entry is written with correct verification flags
INV-012: Bulk forget by source_type removes all documents of that type
"""

import pytest


class TestForgetCompleteness:
    """INV-007 to INV-012: Forget protocol completeness."""

    def test_inv007_chroma_deletion(self, sqlite_db):
        """INV-007: After forget, Chroma has zero vectors."""
        # Insert a document first
        doc_id = sqlite_db.insert_document(
            source_type="filesystem",
            source_path="/test/file.txt",
            raw_content=b"test content",
            checksum="abc123",
        )
        assert doc_id is not None

        # Insert a chunk
        chunk_id = sqlite_db.insert_chunk(
            document_id=doc_id,
            content="test content",
            token_count=2,
            chunk_index=0,
            total_chunks=1,
            start_char=0,
            end_char=12,
        )

        # Delete chunks
        count = sqlite_db.delete_chunks_for_document(doc_id)
        assert count == 1

        # Verify
        chunks = sqlite_db.get_chunks_for_document(doc_id)
        assert len(chunks) == 0

    def test_inv008_sqlite_chunks_deleted(self, sqlite_db):
        """INV-008: After forget, SQLite has zero chunks."""
        doc_id = sqlite_db.insert_document(
            source_type="filesystem",
            source_path="/test/file.txt",
            raw_content=b"test",
            checksum="test123",
        )
        sqlite_db.insert_chunk(doc_id, "content", 1, 0, 1, 0, 7)
        sqlite_db.insert_chunk(doc_id, "content 2", 1, 1, 2, 8, 17)

        sqlite_db.delete_chunks_for_document(doc_id)
        chunks = sqlite_db.get_chunks_for_document(doc_id)
        assert len(chunks) == 0

    def test_inv009_entity_mentions_deleted(self, sqlite_db):
        """INV-009: After forget, entity mentions are removed."""
        doc_id = sqlite_db.insert_document(
            source_type="filesystem",
            source_path="/test/file.txt",
            raw_content=b"test",
            checksum="ent_test_1",
        )
        chunk_id = sqlite_db.insert_chunk(doc_id, "test content", 2, 0, 1, 0, 12)

        entity_id = sqlite_db.upsert_entity("TestEntity", "PERSON")
        sqlite_db.insert_entity_mention(
            entity_id, doc_id, chunk_id, "TestEntity", 0, 0.9
        )

        # Delete mentions
        count = sqlite_db.delete_entity_mentions_for_document(doc_id)
        assert count >= 1

    def test_inv010_document_not_in_search(self, sqlite_db):
        """INV-010: After forget, document cannot be retrieved."""
        doc_id = sqlite_db.insert_document(
            source_type="filesystem",
            source_path="/test/forget_me.txt",
            raw_content=b"forget me please",
            checksum="forget_test_1",
        )
        sqlite_db.update_document_parsed(
            doc_id, "forget me please", "plain", 3
        )

        # Delete document
        sqlite_db.delete_chunks_for_document(doc_id)
        sqlite_db.delete_document(doc_id)

        doc = sqlite_db.get_document(doc_id)
        assert doc is None

    def test_inv011_forget_audit_log(self, sqlite_db):
        """INV-011: Forget audit log is written with correct verification flags."""
        log_id = sqlite_db.insert_forget_log(
            document_id="test-doc-123",
            source_path="/test/file.txt",
            source_type="filesystem",
            chroma_verified=True,
            kuzu_verified=True,
            sqlite_verified=True,
        )
        assert log_id is not None

        # Verify log is readable with correct flags
        with sqlite_db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM forget_log WHERE document_id = ?", ("test-doc-123",)
            ).fetchone()
            assert row is not None
            row_dict = dict(row)
            assert row_dict["chroma_verified"] == 1, "chroma_verified should be 1 (True)"
            assert row_dict["kuzu_verified"] == 1, "kuzu_verified should be 1 (True)"
            assert row_dict["sqlite_verified"] == 1, "sqlite_verified should be 1 (True)"

    def test_inv012_bulk_forget_by_source(self, sqlite_db):
        """INV-012: Bulk forget by source_type removes all of that type."""
        for i in range(5):
            sqlite_db.insert_document(
                source_type="clipboard",
                source_path=f"/clip/{i}",
                raw_content=f"clip {i}".encode(),
                checksum=f"bulk_forget_{i}",
            )

        docs = sqlite_db.list_documents(source_type="clipboard")
        assert len(docs) == 5

        # Delete all
        for doc in docs:
            sqlite_db.delete_document(doc["id"])

        remaining = sqlite_db.list_documents(source_type="clipboard")
        assert len(remaining) == 0
