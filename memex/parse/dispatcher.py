"""
Parser dispatcher for MEMEX.

Routes raw documents to the appropriate parser based on content type
detection (extension, MIME type, magic bytes).
"""

from __future__ import annotations

import mimetypes
from datetime import datetime
from typing import Optional

from ..config.settings import ContentType, ParsedDocument
from ..observability.logging import get_logger
from .base import BaseParser, ParserError
from .pdf_parser import PDFParser
from .html_parser import HTMLParser
from .code_parser import CodeParser
from .email_parser import EmailParser
from .markdown_parser import MarkdownParser
from .plain_parser import PlainParser

logger = get_logger("parse.dispatcher")

# Extension → ContentType mapping
_EXTENSION_MAP: dict[str, ContentType] = {
    ".pdf": ContentType.PDF,
    ".html": ContentType.HTML,
    ".htm": ContentType.HTML,
    ".xhtml": ContentType.HTML,
    ".md": ContentType.MARKDOWN,
    ".markdown": ContentType.MARKDOWN,
    ".eml": ContentType.EMAIL,
    ".py": ContentType.CODE,
    ".js": ContentType.CODE,
    ".ts": ContentType.CODE,
    ".tsx": ContentType.CODE,
    ".jsx": ContentType.CODE,
    ".java": ContentType.CODE,
    ".go": ContentType.CODE,
    ".rs": ContentType.CODE,
    ".cpp": ContentType.CODE,
    ".c": ContentType.CODE,
    ".h": ContentType.CODE,
    ".hpp": ContentType.CODE,
    ".cs": ContentType.CODE,
    ".rb": ContentType.CODE,
    ".php": ContentType.CODE,
    ".swift": ContentType.CODE,
    ".kt": ContentType.CODE,
    ".scala": ContentType.CODE,
    ".sh": ContentType.CODE,
    ".bash": ContentType.CODE,
    ".zsh": ContentType.CODE,
    ".sql": ContentType.CODE,
    ".r": ContentType.CODE,
    ".jl": ContentType.CODE,
    ".yaml": ContentType.CODE,
    ".yml": ContentType.CODE,
    ".toml": ContentType.CODE,
    ".json": ContentType.CODE,
    ".xml": ContentType.CODE,
    ".png": ContentType.IMAGE,
    ".jpg": ContentType.IMAGE,
    ".jpeg": ContentType.IMAGE,
    ".gif": ContentType.IMAGE,
    ".bmp": ContentType.IMAGE,
    ".webp": ContentType.IMAGE,
}


class ParserDispatcher:
    """Routes documents to the appropriate parser."""

    def __init__(self) -> None:
        self._parsers: dict[ContentType, BaseParser] = {
            ContentType.PDF: PDFParser(),
            ContentType.HTML: HTMLParser(),
            ContentType.CODE: CodeParser(),
            ContentType.EMAIL: EmailParser(),
            ContentType.MARKDOWN: MarkdownParser(),
            ContentType.IMAGE: PlainParser(),  # OCR in Phase 2
            ContentType.PLAIN: PlainParser(),
        }

    def detect_content_type(self, filename: str, raw_bytes: bytes) -> ContentType:
        """Detect content type from filename and content."""
        import os
        _, ext = os.path.splitext(filename.lower())

        # Extension-based detection
        if ext in _EXTENSION_MAP:
            return _EXTENSION_MAP[ext]

        # MIME type detection
        mime_type, _ = mimetypes.guess_type(filename)
        if mime_type:
            if "html" in mime_type:
                return ContentType.HTML
            if "pdf" in mime_type:
                return ContentType.PDF
            if "image" in mime_type:
                return ContentType.IMAGE

        # Magic byte detection
        if raw_bytes:
            if raw_bytes[:4] == b"%PDF":
                return ContentType.PDF
            if raw_bytes[:5] == b"<!DOC" or raw_bytes[:1] == b"<":
                return ContentType.HTML

        return ContentType.PLAIN

    def parse(
        self,
        document_id: str,
        raw_bytes: bytes,
        filename: str = "",
        content_type_override: Optional[ContentType] = None,
    ) -> ParsedDocument:
        """Parse raw bytes into a ParsedDocument.

        Args:
            document_id: Document UUID.
            raw_bytes: Raw content bytes.
            filename: Original filename for type detection.
            content_type_override: Override detected content type.

        Returns:
            ParsedDocument with clean_content.

        Raises:
            ParserError: If parsing fails.
        """
        content_type = content_type_override or self.detect_content_type(filename, raw_bytes)

        parser = self._parsers.get(content_type, self._parsers[ContentType.PLAIN])

        try:
            doc = parser.parse(raw_bytes, filename)
            doc.document_id = document_id
            doc.content_type = content_type

            # Validate clean_content
            if not doc.clean_content or not doc.clean_content.strip():
                raise ParserError(
                    f"Empty clean_content after parse ({content_type.value})",
                    parser_name=type(parser).__name__,
                )

            logger.info(
                "parse_complete",
                document_id=document_id,
                content_type=content_type.value,
                word_count=doc.word_count,
            )
            return doc

        except ParserError:
            raise
        except Exception as e:
            logger.error(
                "parse_failed",
                document_id=document_id,
                content_type=content_type.value,
                error=str(e),
                parser=type(parser).__name__,
            )
            raise ParserError(str(e), parser_name=type(parser).__name__) from e
