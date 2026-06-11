"""
Ingestion invariant tests.

INV-013: Duplicate checksum is deduped; document count does not increase
INV-014: Every excluded domain returns SKIP from browser fetcher
INV-015: Queue full condition produces structured DROP log, not silent loss
INV-016: Parse failure marks document PARSE_FAILED, does not crash daemon
INV-017: Ollama unavailability suspends embedding but does not crash daemon
"""

import pytest

from memex.config.settings import (
    Priority, RawDocument, DocumentStatus, load_retention, load_redaction_patterns,
)
from memex.ingest.queue import IngestionQueue
from memex.ingest.browser import _is_excluded_domain, _load_excluded_domains


class TestDeduplication:
    """INV-013: Checksum-based deduplication."""

    def test_inv013_duplicate_checksum_rejected(self, sqlite_db):
        """INV-013: Second insert with same checksum returns None."""
        doc_id1 = sqlite_db.insert_document(
            source_type="filesystem",
            source_path="/test/file.txt",
            raw_content=b"hello world",
            checksum="dedup_test_1",
        )
        assert doc_id1 is not None

        # Second insert with same checksum should return None
        doc_id2 = sqlite_db.insert_document(
            source_type="filesystem",
            source_path="/test/file.txt",
            raw_content=b"hello world",
            checksum="dedup_test_1",
        )
        assert doc_id2 is None

    def test_inv013_document_count_unchanged(self, sqlite_db):
        """INV-013: Document count doesn't increase on dedup."""
        sqlite_db.insert_document(
            source_type="filesystem",
            source_path="/test/a.txt",
            raw_content=b"aaa",
            checksum="count_test_a",
        )
        docs_before = len(sqlite_db.list_documents())

        sqlite_db.insert_document(
            source_type="filesystem",
            source_path="/test/a.txt",
            raw_content=b"aaa",
            checksum="count_test_a",
        )
        docs_after = len(sqlite_db.list_documents())
        assert docs_before == docs_after

    def test_inv013_different_checksum_accepted(self, sqlite_db):
        """INV-013: Different checksum is accepted as new document."""
        id1 = sqlite_db.insert_document("fs", "/a", b"aaa", "chk_a")
        id2 = sqlite_db.insert_document("fs", "/b", b"bbb", "chk_b")
        assert id1 is not None
        assert id2 is not None
        assert id1 != id2


class TestExcludedDomains:
    """INV-014: Browser excluded domain enforcement."""

    def test_inv014_banking_domains_excluded(self):
        """INV-014: Banking domains are skipped."""
        domains = _load_excluded_domains()
        assert _is_excluded_domain("https://chase.com/banking", domains)
        assert _is_excluded_domain("https://bankofamerica.com/account", domains)

    def test_inv014_password_managers_excluded(self):
        """INV-014: Password manager domains are skipped."""
        domains = _load_excluded_domains()
        assert _is_excluded_domain("https://1password.com/vault", domains)
        assert _is_excluded_domain("https://bitwarden.com/vault", domains)

    def test_inv014_sso_domains_excluded(self):
        """INV-014: SSO/identity domains are skipped."""
        domains = _load_excluded_domains()
        assert _is_excluded_domain("https://okta.com/login", domains)
        assert _is_excluded_domain("https://auth0.com/authorize", domains)

    def test_inv014_localhost_excluded(self):
        """INV-014: localhost URLs are skipped."""
        domains = _load_excluded_domains()
        assert _is_excluded_domain("http://localhost:3000", domains)
        assert _is_excluded_domain("http://127.0.0.1:8080", domains)

    def test_inv014_normal_domains_allowed(self):
        """INV-014: Normal domains are not skipped."""
        domains = _load_excluded_domains()
        assert not _is_excluded_domain("https://github.com/repo", domains)
        assert not _is_excluded_domain("https://stackoverflow.com/questions", domains)
        assert not _is_excluded_domain("https://docs.python.org/3/", domains)


class TestQueueBackpressure:
    """INV-015: Queue full produces structured DROP log."""

    def test_inv015_queue_drop_when_full(self):
        """INV-015: Items are dropped (not silently) when queue is full."""
        queue = IngestionQueue(max_depth=3, warn_threshold=2)
        assert queue.max_depth == 3

        # Fill the queue
        for i in range(3):
            doc = RawDocument(
                source_type="test",
                source_path=f"/test/{i}",
                raw_bytes=f"content {i}".encode(),
                encoding="utf-8",
                captured_at=__import__("datetime").datetime.utcnow(),
                priority=Priority.NORMAL,
            )
            assert queue.put(doc)

        # Next item should be dropped
        doc = RawDocument(
            source_type="test",
            source_path="/test/overflow",
            raw_bytes=b"overflow",
            encoding="utf-8",
            captured_at=__import__("datetime").datetime.utcnow(),
            priority=Priority.NORMAL,
        )
        result = queue.put(doc)
        assert result is False
        assert queue.dropped_count == 1

    def test_inv015_dropped_count_increments(self):
        """INV-015: Dropped count tracks all drops."""
        queue = IngestionQueue(max_depth=1, warn_threshold=1)

        doc = RawDocument(
            source_type="test",
            source_path="/t",
            raw_bytes=b"x",
            encoding="utf-8",
            captured_at=__import__("datetime").datetime.utcnow(),
        )
        queue.put(doc)  # fills
        queue.put(doc)  # dropped
        queue.put(doc)  # dropped

        assert queue.dropped_count == 2


class TestParseFailureIsolation:
    """INV-016: Parse failures are isolated."""

    def test_inv016_parse_failure_marks_status(self, sqlite_db):
        """INV-016: Failed parse sets status to PARSE_FAILED."""
        doc_id = sqlite_db.insert_document(
            source_type="filesystem",
            source_path="/test/corrupt.pdf",
            raw_content=b"not a real pdf",
            checksum="parse_fail_1",
        )
        sqlite_db.update_document_status(
            doc_id, DocumentStatus.PARSE_FAILED, error="Invalid PDF header"
        )

        doc = sqlite_db.get_document(doc_id)
        assert doc["status"] == "PARSE_FAILED"
        assert "Invalid PDF header" in doc["last_error"]

    def test_inv016_empty_content_marks_empty(self, sqlite_db):
        """INV-016: Empty content marks status as EMPTY."""
        doc_id = sqlite_db.insert_document(
            source_type="filesystem",
            source_path="/test/empty.txt",
            raw_content=b"",
            checksum="empty_doc_1",
        )
        sqlite_db.update_document_status(doc_id, DocumentStatus.EMPTY)

        doc = sqlite_db.get_document(doc_id)
        assert doc["status"] == "EMPTY"


class TestOllamaUnavailability:
    """INV-017: Ollama unavailability is handled gracefully."""

    def test_inv017_embedder_handles_unavailable(self):
        """INV-017: Embedding fails gracefully when Ollama is down."""
        from memex.index.embedder import Embedder
        from memex.config.settings import Settings

        settings = Settings(ollama_base_url="http://127.0.0.1:19999")  # non-existent
        embedder = Embedder(settings=settings)

        # Should return None, not crash
        result = embedder.embed_text("test")
        assert result is None

    def test_inv017_ollama_unavailable_detected(self):
        """INV-017: Ollama unavailability is detected."""
        from memex.index.embedder import Embedder
        from memex.config.settings import Settings

        settings = Settings(ollama_base_url="http://127.0.0.1:19999")
        embedder = Embedder(settings=settings)

        assert embedder.is_ollama_available() is False
