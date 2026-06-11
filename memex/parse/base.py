"""
Base parser interface for MEMEX.
"""

from __future__ import annotations

import abc
from typing import Optional

from ..config.settings import ContentType, ParsedDocument
from ..observability.logging import get_logger

logger = get_logger("parse.base")


class BaseParser(abc.ABC):
    """Abstract base class for content parsers."""

    content_type: ContentType = ContentType.PLAIN

    @abc.abstractmethod
    def parse(self, raw_bytes: bytes, filename: str = "") -> ParsedDocument:
        """Parse raw bytes into a ParsedDocument.

        Args:
            raw_bytes: Raw file content.
            filename: Original filename (for metadata).

        Returns:
            ParsedDocument with clean_content set.

        Raises:
            ParserError: On parse failure (caught by pipeline).
        """
        ...

    @property
    def supported_extensions(self) -> set[str]:
        """File extensions this parser handles."""
        return set()


class ParserError(Exception):
    """Raised when a parser fails."""
    def __init__(self, message: str, parser_name: str = ""):
        super().__init__(message)
        self.parser_name = parser_name
