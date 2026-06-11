"""PDF parser using pdfminer.six (ADR-007)."""

from __future__ import annotations

import io

from ..config.settings import ContentType, ParsedDocument
from ..observability.logging import get_logger
from .base import BaseParser, ParserError

logger = get_logger("parse.pdf")


class PDFParser(BaseParser):
    """PDF text extraction using pdfminer.six."""

    content_type = ContentType.PDF

    @property
    def supported_extensions(self) -> set[str]:
        return {".pdf"}

    def parse(self, raw_bytes: bytes, filename: str = "") -> ParsedDocument:
        """Extract text from PDF bytes."""
        try:
            from pdfminer.high_level import extract_text

            text = extract_text(io.BytesIO(raw_bytes))

            if not text or not text.strip():
                raise ParserError("PDF produced empty text (possibly scanned/image-only)")

            # Clean up extracted text
            clean_content = self._clean_text(text)

            return ParsedDocument(
                document_id="",  # Set by dispatcher
                clean_content=clean_content,
                content_type=ContentType.PDF,
                parse_metadata={"page_count": self._estimate_pages(text)},
            )

        except ImportError:
            raise ParserError("pdfminer.six not installed", parser_name="PDFParser")
        except ParserError:
            raise
        except Exception as e:
            raise ParserError(f"PDF parse error: {e}", parser_name="PDFParser") from e

    @staticmethod
    def _clean_text(text: str) -> str:
        """Clean extracted PDF text."""
        # Remove excessive whitespace while preserving structure
        lines = text.split("\n")
        cleaned_lines = []
        for line in lines:
            cleaned = " ".join(line.split())
            if cleaned:
                cleaned_lines.append(cleaned)
        return "\n".join(cleaned_lines)

    @staticmethod
    def _estimate_pages(text: str) -> int:
        """Rough page count estimate."""
        # Average PDF page has ~3000 chars
        return max(1, len(text) // 3000)
