"""
Secret redactor for MEMEX.

Runs AFTER parsing, BEFORE chunking/storage.
Loads patterns exclusively from Addendum D.
Replaces matched text with [REDACTED:{pattern_name}].
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from ..config.settings import load_redaction_patterns
from ..observability.logging import get_logger

logger = get_logger("protect.redactor")


class Redactor:
    """Secret pattern redactor.

    Loads all patterns from Addendum D (redaction_patterns.toml).
    Each pattern has: name, regex, replacement, test_fixture, innocuous.
    Also implements entropy-based heuristic detection.
    """

    def __init__(self) -> None:
        config = load_redaction_patterns()
        self._patterns = config.get("patterns", [])
        self._entropy_config = config.get("entropy_heuristic", {})
        self._compiled_patterns: list[dict[str, Any]] = []

        for pattern_def in self._patterns:
            try:
                compiled = re.compile(pattern_def["pattern"])
                self._compiled_patterns.append({
                    "compiled": compiled,
                    "name": pattern_def["name"],
                    "replacement": pattern_def["replacement"],
                    "test_fixture": pattern_def.get("test_fixture", ""),
                    "innocuous": pattern_def.get("innocuous", ""),
                })
            except re.error as e:
                logger.error("regex_compile_error", pattern=pattern_def["name"], error=str(e))

    def redact(self, text: str) -> str:
        """Redact secret patterns in text.

        Args:
            text: Clean content text.

        Returns:
            Text with secrets replaced by [REDACTED:name] markers.
        """
        if not text:
            return text

        redacted = text

        for pattern in self._compiled_patterns:
            matches = pattern["compiled"].findall(redacted)
            if matches:
                redacted = pattern["compiled"].sub(pattern["replacement"], redacted)
                logger.info(
                    "redaction_applied",
                    pattern_name=pattern["name"],
                    match_count=len(matches),
                )

        # Entropy heuristic
        if self._entropy_config.get("enabled", False):
            redacted = self._entropy_redact(redacted)

        return redacted

    def _entropy_redact(self, text: str) -> str:
        """Detect high-entropy strings that may be secrets."""
        min_length = self._entropy_config.get("min_length", 20)
        threshold = self._entropy_config.get("entropy_threshold", 4.5)
        context_chars = self._entropy_config.get("context_window_chars", 30)

        # Find potential secret strings (alphanumeric + special chars)
        candidates = re.findall(r'[A-Za-z0-9+/=_\-]{20,}', text)

        for candidate in candidates:
            if len(candidate) < min_length:
                continue

            # Compute Shannon entropy
            entropy = self._shannon_entropy(candidate)
            if entropy >= threshold:
                # Check surrounding context for secret indicators
                idx = text.find(candidate)
                if idx >= 0:
                    start = max(0, idx - context_chars)
                    end = min(len(text), idx + len(candidate) + context_chars)
                    context = text[start:end].lower()

                    secret_indicators = ["key=", "secret=", "token=", "password=", "api_key", "auth"]
                    if any(indicator in context for indicator in secret_indicators):
                        text = text.replace(candidate, "[REDACTED:high_entropy_secret]")
                        logger.info("redaction_applied", pattern_name="high_entropy_secret")

        return text

    @staticmethod
    def _shannon_entropy(text: str) -> float:
        """Calculate Shannon entropy of a string."""
        if not text:
            return 0.0
        counts = Counter(text)
        length = len(text)
        entropy = 0.0
        for count in counts.values():
            p = count / length
            if p > 0:
                entropy -= p * math.log2(p)
        return entropy

    def verify_patterns(self) -> dict[str, bool]:
        """Verify all patterns correctly redact their test fixtures.

        Returns dict of pattern_name → True/False.
        """
        results = {}
        for pattern in self._compiled_patterns:
            fixture = pattern["test_fixture"]
            if fixture:
                redacted = pattern["compiled"].sub(pattern["replacement"], fixture)
                results[pattern["name"]] = "[REDACTED:" in redacted
        return results

    def verify_no_false_positives(self) -> dict[str, bool]:
        """Verify patterns don't false-positive on innocuous strings."""
        results = {}
        for pattern in self._compiled_patterns:
            innocuous = pattern["innocuous"]
            if innocuous:
                redacted = pattern["compiled"].sub(pattern["replacement"], innocuous)
                results[pattern["name"]] = "[REDACTED:" not in redacted
        return results

    def get_excluded_domains(self) -> set[str]:
        """Get browser excluded domains from Addendum D."""
        config = load_redaction_patterns()
        return set(config.get("browser_excluded_domains", {}).get("domains", []))
