"""
Configuration hygiene invariant tests.

INV-025: No Addendum A weight values are hard-coded outside Addendum A
INV-026: No Addendum B day values are hard-coded outside Addendum B
INV-027: No Addendum C token budget values are hard-coded outside Addendum C
INV-028: Embedding model name is config-driven (not hardcoded)
INV-029: embed_model metadata is present on every Chroma vector upsert
INV-030: All addenda TOML files exist and parse without error
"""

import ast
import os
import re
from pathlib import Path

import pytest

# Source files to scan for hard-coded values
_SOURCE_DIR = Path(__file__).parent.parent.parent / "memex"
_CONFIG_DIR = _SOURCE_DIR / "config"


class TestConfigHygiene:
    """INV-025 to INV-030: Config value hygiene."""

    def _get_source_files(self) -> list[Path]:
        """Get all Python source files (excluding config/)."""
        files = []
        for py_file in _SOURCE_DIR.rglob("*.py"):
            if _CONFIG_DIR in py_file.parents:
                continue
            if "__pycache__" in str(py_file):
                continue
            files.append(py_file)
        return files

    def _search_sources(self, pattern: str) -> list[tuple[str, int]]:
        """Search source files for a pattern. Returns (file, line) matches."""
        results = []
        for f in self._get_source_files():
            for i, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
                if re.search(pattern, line) and "#" not in line.split(pattern)[0]:
                    results.append((str(f.relative_to(_SOURCE_DIR)), i))
        return results

    def test_inv025_no_hardcoded_weights(self):
        """INV-025: Retrieval weights not hard-coded outside config."""
        # 0.40, 0.30, 0.20, 0.10 are the canonical weights
        weight_patterns = [
            r'vector_weight\s*=\s*0\.40',
            r'keyword_weight\s*=\s*0\.30',
            r'graph_weight\s*=\s*0\.20',
            r'temporal_weight\s*=\s*0\.10',
        ]
        for pattern in weight_patterns:
            matches = self._search_sources(pattern)
            # Allow in settings.py (loading) but not elsewhere
            non_config = [m for m in matches if "settings.py" not in m[0]]
            assert len(non_config) == 0, f"Hard-coded weight found: {non_config}"

    def test_inv026_no_hardcoded_retention_days(self):
        """INV-026: Retention day values not hard-coded."""
        # The canonical raw_content purge is 7 days
        matches = self._search_sources(r'purge_after_days\s*=\s*7')
        non_config = [m for m in matches if "settings.py" not in m[0]]
        assert len(non_config) == 0, f"Hard-coded retention days: {non_config}"

    def test_inv027_no_hardcoded_chunk_budgets(self):
        """INV-027: Chunk token budgets not hard-coded."""
        matches = self._search_sources(r'prose_tokens\s*=\s*400')
        non_config = [m for m in matches if "settings.py" not in m[0]]
        assert len(non_config) == 0, f"Hard-coded chunk budget: {non_config}"

    def test_inv028_model_name_config_driven(self):
        """INV-028: Embedding model name is config-driven."""
        # Verify settings.py exposes model name from config
        from memex.config.settings import Settings
        settings = Settings()
        assert settings.embed_model is not None
        assert isinstance(settings.embed_model, str)
        assert len(settings.embed_model) > 0

    def test_inv029_chroma_metadata_includes_model(self):
        """INV-029: embed_model is in Chroma upsert metadata."""
        # Verify the embedder stores model info in metadata
        from memex.index.embedder import Embedder
        import inspect

        source = inspect.getsource(Embedder.embed_and_store)
        assert "embed_model" in source, "embed_model not in Chroma metadata"
        assert "embed_model_version" in source, "embed_model_version not in Chroma metadata"

    def test_inv030_addenda_files_exist_and_parse(self):
        """INV-030: All addenda TOML files exist and parse without error."""
        import toml

        required_files = [
            "retrieval_weights.toml",
            "retention.toml",
            "chunking.toml",
            "redaction_patterns.toml",
            "slos.toml",
        ]
        for filename in required_files:
            path = _CONFIG_DIR / filename
            assert path.exists(), f"Missing addendum file: {filename}"
            # Verify it parses
            data = toml.load(str(path))
            assert len(data) > 0, f"Empty addendum file: {filename}"
