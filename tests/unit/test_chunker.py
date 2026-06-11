"""Unit tests for chunking."""

import pytest

from memex.config.settings import ContentType
from memex.index.chunker import SmartChunker


class TestSmartChunker:
    def setup_method(self):
        self.chunker = SmartChunker()

    def test_prose_chunking(self):
        """Prose is chunked at paragraph boundaries."""
        content = "\n\n".join([
            f"Paragraph {i} with some content about topic {i}. "
            f"This is additional filler text to make the paragraph longer. "
            f"We need enough text to exceed the target chunk size for prose content. "
            f"Adding more words here to reach the threshold."
            for i in range(30)
        ])
        chunks = self.chunker.chunk("doc1", content, ContentType.PLAIN)
        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk.document_id == "doc1"
            assert chunk.total_chunks == len(chunks)

    def test_code_chunking(self):
        """Code is chunked at function boundaries."""
        code = "\n\n".join([
            f"def function_{i}():\n    \"\"\"Docstring for func {i}.\"\"\"\n    return {i}\n"
            for i in range(20)
        ])
        chunks = self.chunker.chunk("doc2", code, ContentType.CODE)
        assert len(chunks) >= 1

    def test_empty_content_returns_empty(self):
        """Empty content produces no chunks."""
        chunks = self.chunker.chunk("doc3", "", ContentType.PLAIN)
        assert chunks == []

    def test_short_content_single_chunk(self):
        """Short content fits in a single chunk."""
        chunks = self.chunker.chunk("doc4", "Short text.", ContentType.PLAIN)
        assert len(chunks) == 1
        assert chunks[0].content == "Short text."
        assert chunks[0].chunk_index == 0
        assert chunks[0].total_chunks == 1

    def test_chunks_have_ids(self):
        """Every chunk has a unique ID."""
        content = "\n\n".join([f"Paragraph {i} " * 20 for i in range(10)])
        chunks = self.chunker.chunk("doc5", content, ContentType.PLAIN)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids)), "Chunk IDs are not unique"

    def test_chunks_have_positions(self):
        """Chunks have valid start_char and end_char."""
        chunks = self.chunker.chunk("doc6", "Hello world paragraph one.\n\nSecond paragraph here.", ContentType.PLAIN)
        for chunk in chunks:
            assert chunk.start_char >= 0
            assert chunk.end_char > chunk.start_char

    def test_email_chunking(self):
        """Email content uses smaller chunks."""
        content = "\n\n".join([f"Email paragraph {i}." * 10 for i in range(10)])
        chunks = self.chunker.chunk("doc7", content, ContentType.EMAIL)
        assert len(chunks) >= 1

    def test_max_context_tokens(self):
        """Context window budget is sane."""
        assert self.chunker.max_context_tokens > 0
        assert self.chunker.max_context_tokens <= 100000

    def test_conversation_history_turns(self):
        """Conversation history setting is sane."""
        assert 1 <= self.chunker.conversation_history_turns <= 50
