"""Plain text parser with encoding detection."""

from __future__ import annotations

from ..config.settings import ContentType, ParsedDocument
from ..observability.logging import get_logger
from .base import BaseParser, ParserError

logger = get_logger("parse.plain")


class PlainParser(BaseParser):
    """Plain text parser with automatic encoding detection."""

    content_type = ContentType.PLAIN

    def parse(self, raw_bytes: bytes, filename: str = "") -> ParsedDocument:
        """Decode raw bytes to text with encoding detection."""
        # Try UTF-8 first
        text = None
        encoding = "utf-8"

        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            pass

        # Try chardet detection
        if text is None:
            try:
                import chardet
                result = chardet.detect(raw_bytes)
                if result and result.get("encoding"):
                    encoding = result["encoding"]
                    text = raw_bytes.decode(encoding, errors="replace")
            except ImportError:
                pass

        # Final fallback: Latin-1 (never fails)
        if text is None:
            encoding = "latin-1"
            text = raw_bytes.decode("latin-1")

        if not text.strip():
            raise ParserError("Empty text content after decode")

        return ParsedDocument(
            document_id="",
            clean_content=text.strip(),
            content_type=ContentType.PLAIN,
            parse_metadata={"encoding": encoding},
        )
