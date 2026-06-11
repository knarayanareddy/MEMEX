"""Code parser with tree-sitter enrichment.

Extracts docstrings, symbol index, and code body.
Order: docstrings → symbol index → raw code.

FIX: Gracefully handles tree-sitter unavailability instead of crashing.
"""

from __future__ import annotations

import re
from typing import Optional

from ..config.settings import ContentType, ParsedDocument
from ..observability.logging import get_logger
from .base import BaseParser, ParserError

logger = get_logger("parse.code")

# Language detection from extension
_EXT_TO_LANG: dict[str, str] = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".tsx": "tsx", ".jsx": "jsx", ".java": "java", ".go": "go",
    ".rs": "rust", ".cpp": "cpp", ".c": "c", ".h": "c",
    ".cs": "c_sharp", ".rb": "ruby", ".php": "php",
    ".swift": "swift", ".kt": "kotlin", ".scala": "scala",
    ".sh": "bash", ".bash": "bash", ".zsh": "bash",
    ".sql": "sql", ".r": "r", ".jl": "julia",
}

# Track whether tree-sitter is available at import time
_TREESITTER_AVAILABLE: bool = False
_TREESITTER_LANGUAGE_CACHE: dict[str, any] = {}

try:
    import tree_sitter
    _TREESITTER_AVAILABLE = True
    logger.info("tree_sitter_available", version=getattr(tree_sitter, "__version__", "unknown"))
except ImportError:
    logger.info("tree_sitter_not_available", fallback="regex")

# Try to get individual language grammars
def _get_language(lang: str) -> Optional[object]:
    """Try to load a tree-sitter Language for the given lang.

    Tries multiple import strategies:
      1. tree_sitter_languages (separate package)
      2. tree_sitter.Language with bundled grammars
      3. Direct .so/.dylib language files
    """
    if lang in _TREESITTER_LANGUAGE_CACHE:
        return _TREESITTER_LANGUAGE_CACHE[lang]

    # Strategy 1: tree_sitter_languages package
    try:
        import tree_sitter_languages
        lang_obj = tree_sitter_languages.get_language(lang)
        _TREESITTER_LANGUAGE_CACHE[lang] = lang_obj
        return lang_obj
    except (ImportError, Exception):
        pass

    # Strategy 2: tree_sitter.Language with built-in lookup
    try:
        import tree_sitter
        if hasattr(tree_sitter, "Language"):
            # New API: tree_sitter.Language looks up by name
            lang_obj = tree_sitter.Language(lang)
            _TREESITTER_LANGUAGE_CACHE[lang] = lang_obj
            return lang_obj
    except Exception:
        pass

    return None


def _get_parser(lang: str) -> Optional[object]:
    """Get a tree-sitter Parser for the given language, or None."""
    if not _TREESITTER_AVAILABLE:
        return None

    try:
        import tree_sitter as ts

        # New API (0.21+): Parser() then set_language
        parser = ts.Parser()

        lang_obj = _get_language(lang)
        if lang_obj is not None:
            try:
                parser.language = lang_obj
            except AttributeError:
                # Older API
                parser.set_language(lang_obj)
            return parser
    except Exception:
        pass

    return None


class CodeParser(BaseParser):
    """Code parser with tree-sitter symbol extraction.

    Falls back gracefully to regex extraction when tree-sitter or
    language grammars are unavailable.
    """

    content_type = ContentType.CODE

    @property
    def supported_extensions(self) -> set[str]:
        return set(_EXT_TO_LANG.keys())

    def parse(self, raw_bytes: bytes, filename: str = "") -> ParsedDocument:
        """Parse source code with symbol extraction."""
        try:
            source = raw_bytes.decode("utf-8", errors="replace")
            language = self._detect_language(filename)

            # Try tree-sitter enrichment, fall back to regex
            docstrings: list[str] = []
            symbols: list[str] = []

            parser = _get_parser(language)
            if parser is not None:
                docstrings, symbols = self._extract_with_treesitter(source, language, parser)
                logger.debug(
                    "treesitter_extraction_ok",
                    language=language,
                    symbols=len(symbols),
                    docstrings=len(docstrings),
                )
            else:
                symbols = self._regex_extract_symbols(source, language)
                docstrings = self._regex_extract_docstrings(source, language)
                logger.debug(
                    "regex_fallback_extraction",
                    language=language,
                    symbols=len(symbols),
                )

            # Build clean_content: docstrings → symbols → code
            parts = []
            if docstrings:
                parts.append("## Documentation\n" + "\n".join(docstrings))
            if symbols:
                parts.append("## Symbols\n" + "\n".join(symbols))
            parts.append(source)

            clean_content = "\n\n".join(parts)

            return ParsedDocument(
                document_id="",
                clean_content=clean_content,
                content_type=ContentType.CODE,
                language=language,
                parse_metadata={
                    "top_symbols": symbols[:20] if symbols else [],
                    "language": language,
                    "line_count": source.count("\n") + 1,
                    "treesitter_used": parser is not None,
                },
            )

        except Exception as e:
            raise ParserError(f"Code parse error: {e}", parser_name="CodeParser") from e

    @staticmethod
    def _detect_language(filename: str) -> str:
        """Detect programming language from filename."""
        import os
        _, ext = os.path.splitext(filename.lower())
        return _EXT_TO_LANG.get(ext, "unknown")

    def _extract_with_treesitter(
        self, source: str, language: str, parser
    ) -> tuple[list[str], list[str]]:
        """Extract docstrings and symbols using tree-sitter."""
        docstrings: list[str] = []
        symbols: list[str] = []

        try:
            tree = parser.parse(source.encode("utf-8"))
            if tree and tree.root_node:
                self._walk_tree(tree.root_node, source, docstrings, symbols, language)
        except Exception as e:
            logger.debug("treesitter_walk_error", error=str(e))
            # Fall through to regex
            symbols = self._regex_extract_symbols(source, language)
            docstrings = self._regex_extract_docstrings(source, language)

        return docstrings, symbols

    @staticmethod
    def _walk_tree(node, source: str, docstrings: list, symbols: list, language: str) -> None:
        """Recursively walk tree-sitter AST to extract symbols and docstrings."""
        if not hasattr(node, 'type') or not hasattr(node, 'children'):
            return

        # Function/method/class definitions
        if node.type in (
            "function_definition", "method_definition",
            "function_declaration", "method_declaration",
            "arrow_function", "class_definition",
            "class_declaration", "decorated_definition",
        ):
            for child in node.children:
                if child.type in ("identifier", "name", "property_identifier"):
                    name = source[child.start_byte:child.end_byte]
                    symbols.append(name)
                # Extract docstrings (Python string as first child of body)
                if child.type == "block" and language == "python":
                    for stmt in child.children:
                        if stmt.type == "expression_statement":
                            for expr in stmt.children:
                                if expr.type == "string":
                                    doc = source[expr.start_byte:expr.end_byte]
                                    docstrings.append(doc.strip('"\'').strip())
                            break

            for child in node.children:
                if child.type in ("block", "body", "statement_block"):
                    CodeParser._walk_tree(child, source, docstrings, symbols, language)

        for child in node.children:
            if child.type not in (
                "function_definition", "method_definition",
                "function_declaration", "method_declaration",
                "arrow_function", "class_definition",
                "class_declaration", "decorated_definition",
            ):
                CodeParser._walk_tree(child, source, docstrings, symbols, language)

    @staticmethod
    def _regex_extract_symbols(source: str, language: str) -> list[str]:
        """Fallback regex-based symbol extraction."""
        symbols: list[str] = []

        if language == "python":
            for m in re.finditer(r'^(?:async\s+)?def\s+(\w+)', source, re.MULTILINE):
                symbols.append(m.group(1))
            for m in re.finditer(r'^class\s+(\w+)', source, re.MULTILINE):
                symbols.append(m.group(1))
        else:
            for m in re.finditer(
                r'(?:function|def|class|fn|struct|impl|interface|pub fn)\s+(\w+)', source
            ):
                symbols.append(m.group(1))

        return symbols

    @staticmethod
    def _regex_extract_docstrings(source: str, language: str) -> list[str]:
        """Fallback regex-based docstring extraction."""
        if language == "python":
            return re.findall(r'"""([\s\S]*?)"""', source)
        return re.findall(r'/\*\*?([\s\S]*?)\*/', source)
