"""HTML parser using readability-lxml."""

from __future__ import annotations

from ..config.settings import ContentType, ParsedDocument
from ..observability.logging import get_logger
from .base import BaseParser, ParserError

logger = get_logger("parse.html")


class HTMLParser(BaseParser):
    """HTML content extraction using readability-lxml."""

    content_type = ContentType.HTML

    @property
    def supported_extensions(self) -> set[str]:
        return {".html", ".htm", ".xhtml"}

    def parse(self, raw_bytes: bytes, filename: str = "") -> ParsedDocument:
        """Extract readable text from HTML."""
        try:
            from readability import Document
            from lxml.html import fromstring, tostring

            html = raw_bytes.decode("utf-8", errors="replace")

            doc = Document(html)
            title = doc.title()
            summary_html = doc.summary()

            # Strip remaining HTML tags
            tree = fromstring(summary_html)
            clean_text = tree.text_content().strip()

            if not clean_text:
                # Fallback: raw tag stripping
                import re
                clean_text = re.sub(r"<[^>]+>", " ", html)
                clean_text = " ".join(clean_text.split())

            # Prepend title
            if title:
                clean_text = f"{title}\n\n{clean_text}"

            return ParsedDocument(
                document_id="",
                clean_content=clean_text,
                content_type=ContentType.HTML,
                parse_metadata={"title": title},
            )

        except ImportError:
            raise ParserError("readability-lxml not installed", parser_name="HTMLParser")
        except Exception as e:
            raise ParserError(f"HTML parse error: {e}", parser_name="HTMLParser") from e
