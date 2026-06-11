"""Markdown parser using markdown-it-py."""

from __future__ import annotations

from ..config.settings import ContentType, ParsedDocument
from ..observability.logging import get_logger
from .base import BaseParser, ParserError

logger = get_logger("parse.markdown")


class MarkdownParser(BaseParser):
    """Markdown parser — converts to plain text via markdown-it-py."""

    content_type = ContentType.MARKDOWN

    @property
    def supported_extensions(self) -> set[str]:
        return {".md", ".markdown"}

    def parse(self, raw_bytes: bytes, filename: str = "") -> ParsedDocument:
        """Parse markdown to plain text."""
        try:
            text = raw_bytes.decode("utf-8", errors="replace")

            try:
                from markdown_it import MarkdownIt
                md = MarkdownIt()
                tokens = md.parse(text)

                # Extract text from tokens
                clean_parts = []
                for token in tokens:
                    if token.type in ("inline", "text"):
                        clean_parts.append(token.content)
                    elif token.type == "heading_open":
                        clean_parts.append("")  # Add blank line before headings
                    elif token.type == "fence":
                        # Keep code blocks as-is
                        clean_parts.append(f"```\n{token.content}\n```")

                clean_content = "\n".join(p for p in clean_parts if p is not None)
            except ImportError:
                # Fallback: just use raw markdown as text
                clean_content = text

            clean_content = clean_content.strip()
            if not clean_content:
                raise ParserError("Empty markdown content after parse")

            return ParsedDocument(
                document_id="",
                clean_content=clean_content,
                content_type=ContentType.MARKDOWN,
            )

        except Exception as e:
            raise ParserError(f"Markdown parse error: {e}", parser_name="MarkdownParser") from e
