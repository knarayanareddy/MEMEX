"""
Content-aware smart chunker for MEMEX.

Dispatches by content_type to a chunking strategy with configurable
token budgets from Addendum C.
"""

from __future__ import annotations

import re
import uuid
from typing import Optional

from ..config.settings import Chunk, ContentType, load_chunking
from ..observability.logging import get_logger

logger = get_logger("index.chunker")

# Rough estimate: 1 token ≈ 4 characters
_CHARS_PER_TOKEN = 4


class SmartChunker:
    """Content-aware chunker that dispatches by content type."""

    def __init__(self) -> None:
        config = load_chunking()
        self._budgets = config.get("chunk_budgets", {})
        self._context = config.get("context_window", {})

    def chunk(self, document_id: str, content: str, content_type: ContentType) -> list[Chunk]:
        """Split content into chunks based on content type.

        Args:
            document_id: Parent document ID.
            content: Clean text content.
            content_type: Type of content (prose, code, etc.).

        Returns:
            List of Chunk objects with positional metadata.
        """
        if not content or not content.strip():
            return []

        if content_type == ContentType.CODE:
            chunks = self._chunk_code(document_id, content)
        elif content_type == ContentType.EMAIL:
            chunks = self._chunk_email(document_id, content)
        elif content_type == ContentType.PDF:
            chunks = self._chunk_prose(document_id, content, "pdf")
        elif content_type == ContentType.IMAGE:
            chunks = self._chunk_prose(document_id, content, "image_ocr")
        else:
            chunks = self._chunk_prose(document_id, content, "prose")

        total = len(chunks)
        for i, chunk in enumerate(chunks):
            chunk.total_chunks = total

        logger.debug(
            "chunking_complete",
            document_id=document_id,
            content_type=content_type.value,
            chunk_count=total,
        )
        return chunks

    def _chunk_prose(self, doc_id: str, content: str, prefix: str) -> list[Chunk]:
        """Chunk prose content at paragraph boundaries."""
        target_tokens = self._budgets.get(f"{prefix}_tokens", 400)
        overlap_tokens = self._budgets.get(f"{prefix}_overlap_tokens", 50)

        target_chars = target_tokens * _CHARS_PER_TOKEN
        overlap_chars = overlap_tokens * _CHARS_PER_TOKEN

        # Split at paragraph boundaries
        paragraphs = re.split(r'\n\s*\n', content)
        return self._merge_paragraphs(doc_id, paragraphs, target_chars, overlap_chars)

    def _chunk_code(self, doc_id: str, content: str) -> list[Chunk]:
        """Chunk code at function/class boundaries."""
        target_tokens = self._budgets.get("code_tokens", 300)
        overlap_tokens = self._budgets.get("code_overlap_tokens", 30)

        target_chars = target_tokens * _CHARS_PER_TOKEN
        overlap_chars = overlap_tokens * _CHARS_PER_TOKEN

        # Split at blank lines or function/class boundaries
        blocks = re.split(r'\n(?=(?:def |class |function |async |pub |fn |impl ))', content)
        if len(blocks) <= 1:
            # Fallback: split at double newlines
            blocks = re.split(r'\n\s*\n', content)

        return self._merge_paragraphs(doc_id, blocks, target_chars, overlap_chars)

    def _chunk_email(self, doc_id: str, content: str) -> list[Chunk]:
        """Chunk email content."""
        target_tokens = self._budgets.get("email_tokens", 200)
        overlap_tokens = self._budgets.get("email_overlap_tokens", 20)

        target_chars = target_tokens * _CHARS_PER_TOKEN
        overlap_chars = overlap_tokens * _CHARS_PER_TOKEN

        paragraphs = re.split(r'\n\s*\n', content)
        return self._merge_paragraphs(doc_id, paragraphs, target_chars, overlap_chars)

    def _merge_paragraphs(
        self,
        doc_id: str,
        paragraphs: list[str],
        target_chars: int,
        overlap_chars: int,
    ) -> list[Chunk]:
        """Merge paragraphs into chunks respecting target size."""
        chunks: list[Chunk] = []
        current_text = ""
        current_start = 0
        chunk_index = 0
        char_position = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                char_position += 1  # Account for the split
                continue

            if len(current_text) + len(para) + 2 > target_chars and current_text:
                # Emit current chunk
                chunk = Chunk(
                    chunk_id=str(uuid.uuid4()),
                    document_id=doc_id,
                    content=current_text.strip(),
                    token_count=max(1, len(current_text) // _CHARS_PER_TOKEN),
                    chunk_index=chunk_index,
                    start_char=current_start,
                    end_char=current_start + len(current_text),
                )
                chunks.append(chunk)
                chunk_index += 1

                # Start new chunk with overlap
                if overlap_chars > 0 and len(current_text) > overlap_chars:
                    overlap_text = current_text[-overlap_chars:]
                    current_text = overlap_text + "\n\n" + para
                else:
                    current_text = para
                current_start = char_position
            else:
                if current_text:
                    current_text += "\n\n" + para
                else:
                    current_text = para
                    current_start = char_position

            char_position += len(para) + 2

        # Final chunk
        if current_text.strip():
            chunk = Chunk(
                chunk_id=str(uuid.uuid4()),
                document_id=doc_id,
                content=current_text.strip(),
                token_count=max(1, len(current_text) // _CHARS_PER_TOKEN),
                chunk_index=chunk_index,
                start_char=current_start,
                end_char=current_start + len(current_text),
            )
            chunks.append(chunk)

        return chunks

    @property
    def max_context_tokens(self) -> int:
        """Maximum context tokens for LLM prompt (from Addendum C)."""
        return self._context.get("max_context_tokens", 6000)

    @property
    def conversation_history_turns(self) -> int:
        """Number of conversation history turns to include."""
        return self._context.get("conversation_history_turns", 6)
