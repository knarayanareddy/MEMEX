"""Integration tests for the full pipeline."""

import pytest

from memex.config.settings import DocumentStatus
from memex.parse.dispatcher import ParserDispatcher
from memex.index.chunker import SmartChunker
from memex.protect.redactor import Redactor


class TestFullPipeline:
    """End-to-end pipeline test: ingest → parse → redact → chunk."""

    def test_text_document_pipeline(self, sqlite_db):
        """Plain text goes through the full pipeline."""
        # Ingest
        doc_id = sqlite_db.insert_document(
            source_type="filesystem",
            source_path="/test/readme.txt",
            raw_content=b"Hello World\n\nThis is a test document about Python.",
            checksum="pipeline_test_1",
        )
        assert doc_id is not None

        # Parse
        dispatcher = ParserDispatcher()
        parsed = dispatcher.parse(
            document_id=doc_id,
            raw_bytes=b"Hello World\n\nThis is a test document about Python.",
            filename="readme.txt",
        )
        assert parsed.clean_content is not None
        assert "Hello World" in parsed.clean_content

        # Redact
        redactor = Redactor()
        clean = redactor.redact(parsed.clean_content)
        assert "Python" in clean  # Not a secret

        # Update parsed
        sqlite_db.update_document_parsed(
            doc_id, clean, parsed.content_type.value, parsed.word_count
        )

        # Chunk
        chunker = SmartChunker()
        chunks = chunker.chunk(doc_id, clean, parsed.content_type)
        assert len(chunks) >= 1

        # Store chunks
        for chunk in chunks:
            chunk_id = sqlite_db.insert_chunk(
                document_id=doc_id,
                content=chunk.content,
                token_count=chunk.token_count,
                chunk_index=chunk.chunk_index,
                total_chunks=chunk.total_chunks,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
            )
            assert chunk_id is not None

        # Verify
        stored_chunks = sqlite_db.get_chunks_for_document(doc_id)
        assert len(stored_chunks) == len(chunks)

        doc = sqlite_db.get_document(doc_id)
        assert doc["status"] == "PARSED"
        assert doc["content_type"] == "plain"

    def test_code_document_pipeline(self, sqlite_db):
        """Code goes through the pipeline with symbol extraction."""
        code = b'def greet(name):\n    """Greet someone."""\n    return f"Hello {name}"\n'

        doc_id = sqlite_db.insert_document("fs", "/test/app.py", code, "pipeline_code_1")

        dispatcher = ParserDispatcher()
        parsed = dispatcher.parse(doc_id, code, filename="app.py")
        assert parsed.content_type.value == "code"
        assert parsed.language == "python"

        # Code parser should include symbols
        assert "greet" in parsed.clean_content

    def test_secret_redaction_in_pipeline(self, sqlite_db):
        """Secrets are redacted before storage."""
        text = b"My API key is sk-aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcdefghij12 be careful"

        doc_id = sqlite_db.insert_document("fs", "/secrets.txt", text, "pipeline_secret_1")

        dispatcher = ParserDispatcher()
        parsed = dispatcher.parse(doc_id, text, filename="secrets.txt")

        redactor = Redactor()
        clean = redactor.redact(parsed.clean_content)

        assert "[REDACTED:openai_key]" in clean
        assert "sk-aBcDeFgH" not in clean

        # Verify redacted content is stored
        sqlite_db.update_document_parsed(doc_id, clean, "plain", 10)
        doc = sqlite_db.get_document(doc_id)
        assert "[REDACTED:openai_key]" in doc["clean_content"]

    def test_fts_search_after_indexing(self, sqlite_db):
        """Chunks are searchable via FTS after indexing."""
        doc_id = sqlite_db.insert_document(
            "fs", "/unique_topic.txt",
            b"Quantum computing uses qubits",
            "fts_test_unique_1",
        )
        sqlite_db.update_document_parsed(
            doc_id, "Quantum computing uses qubits for parallel processing", "plain", 7
        )
        # Insert a chunk (FTS on chunks)
        sqlite_db.insert_chunk(doc_id, "Quantum computing uses qubits for parallel processing", 7, 0, 1, 0, 52)

        results = sqlite_db.fts_search("quantum computing")
        assert len(results) > 0

    def test_entity_extraction_flow(self, sqlite_db):
        """Entities can be stored and queried."""
        doc_id = sqlite_db.insert_document("fs", "/t", b"x", "entity_flow_1")
        chunk_id = sqlite_db.insert_chunk(doc_id, "Python is great", 3, 0, 1, 0, 16)

        entity_id = sqlite_db.upsert_entity("Python", "CONCEPT")
        sqlite_db.insert_entity_mention(
            entity_id, doc_id, chunk_id, "Python", 0, 0.95
        )

        entities = sqlite_db.search_entities("Python")
        assert len(entities) >= 1
        assert entities[0]["canonical_name"] == "Python"
        assert entities[0]["mention_count"] >= 1
