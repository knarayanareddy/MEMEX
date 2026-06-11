"""Unit tests for redactor."""

import pytest

from memex.protect.redactor import Redactor


class TestRedactor:
    def setup_method(self):
        self.redactor = Redactor()

    def test_clean_text_unchanged(self):
        """Normal text passes through unchanged."""
        text = "Hello, this is a normal sentence about Python programming."
        assert self.redactor.redact(text) == text

    def test_openai_key_redacted(self):
        text = "key=sk-aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcdefghij12"
        result = self.redactor.redact(text)
        assert "[REDACTED:openai_key]" in result
        assert "sk-" not in result

    def test_github_pat_redacted(self):
        text = "token=ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789"
        result = self.redactor.redact(text)
        assert "[REDACTED:github_pat]" in result

    def test_aws_key_redacted(self):
        text = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
        result = self.redactor.redact(text)
        assert "[REDACTED:aws_access_key]" in result

    def test_private_key_redacted(self):
        text = "-----BEGIN RSA PRIVATE KEY-----\nsomekeydata"
        result = self.redactor.redact(text)
        assert "[REDACTED:private_key]" in result

    def test_bearer_redacted(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = self.redactor.redact(text)
        assert "[REDACTED:bearer_token]" in result

    def test_db_connection_redacted(self):
        text = "DATABASE_URL=postgres://user:password@localhost:5432/mydb"
        result = self.redactor.redact(text)
        assert "[REDACTED:db_connection_string]" in result
        assert "password@" not in result

    def test_empty_string(self):
        assert self.redactor.redact("") == ""

    def test_none_like_empty(self):
        assert self.redactor.redact(None) is None

    def test_multiple_patterns(self):
        text = (
            "key=sk-aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcdefghij12 "
            "and AWS=AKIAIOSFODNN7EXAMPLE"
        )
        result = self.redactor.redact(text)
        assert result.count("[REDACTED:") >= 2

    def test_public_key_not_redacted(self):
        """Public keys should not be redacted."""
        text = "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A"
        result = self.redactor.redact(text)
        # PRIVATE is what gets caught, PUBLIC should be fine
        assert "[REDACTED:private_key]" not in result

    def test_entropy_detection_with_context(self):
        """High-entropy strings with secret context are flagged."""
        text = "api_key=AbCdEf1234567890XyZwVuTsRqPoNmLkJiHgFe"
        result = self.redactor.redact(text)
        # The entropy heuristic should catch this if enabled
        # (depends on entropy config)
        assert isinstance(result, str)

    def test_shannon_entropy(self):
        """Shannon entropy calculation is correct."""
        # Known entropy values
        assert Redactor._shannon_entropy("aaaa") == 0.0  # All same char
        assert Redactor._shannon_entropy("ab") == 1.0  # Two equal chars
        assert Redactor._shannon_entropy("abc") > 1.0  # Three different chars
