"""
Redaction invariant tests.

INV-005: Every pattern in Addendum D correctly redacts a known fixture
INV-006: No Addendum D pattern false-positives on common innocuous strings
"""

import pytest


class TestRedactionPatterns:
    """INV-005 & INV-006: Secret redaction correctness."""

    def test_inv005_all_patterns_redact_fixtures(self, redactor):
        """INV-005: Every pattern correctly redacts its test fixture."""
        results = redactor.verify_patterns()
        for pattern_name, passed in results.items():
            assert passed, f"Pattern '{pattern_name}' failed to redact its test fixture"

    def test_inv006_no_false_positives(self, redactor):
        """INV-006: No pattern false-positives on innocuous strings."""
        results = redactor.verify_no_false_positives()
        for pattern_name, passed in results.items():
            assert passed, f"Pattern '{pattern_name}' false-positived on innocuous string"

    def test_inv005_openai_key_redaction(self, redactor):
        """INV-005: OpenAI key is redacted."""
        text = "My key is sk-aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcdefghij12 and keep it safe"
        result = redactor.redact(text)
        assert "[REDACTED:openai_key]" in result
        assert "sk-aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcdefghij12" not in result

    def test_inv005_github_pat_redaction(self, redactor):
        """INV-005: GitHub PAT is redacted."""
        text = "export GITHUB_TOKEN=ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789"
        result = redactor.redact(text)
        assert "[REDACTED:github_pat]" in result
        assert "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789" not in result

    def test_inv005_aws_key_redaction(self, redactor):
        """INV-005: AWS access key is redacted."""
        text = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
        result = redactor.redact(text)
        assert "[REDACTED:aws_access_key]" in result
        assert "AKIAIOSFODNN7EXAMPLE" not in result

    def test_inv005_private_key_redaction(self, redactor):
        """INV-005: Private key header is redacted."""
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA"
        result = redactor.redact(text)
        assert "[REDACTED:private_key]" in result
        assert "BEGIN RSA PRIVATE KEY" not in result

    def test_inv005_bearer_token_redaction(self, redactor):
        """INV-005: Bearer token is redacted."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = redactor.redact(text)
        assert "[REDACTED:bearer_token]" in result

    def test_inv005_db_connection_string_redaction(self, redactor):
        """INV-005: Database connection string is redacted."""
        text = "DATABASE_URL=postgres://user:password@localhost:5432/mydb"
        result = redactor.redact(text)
        assert "[REDACTED:db_connection_string]" in result
        assert "password@" not in result

    def test_inv006_innocuous_text_unchanged(self, redactor):
        """INV-006: Innocuous text passes through unchanged."""
        texts = [
            "asking a question is fine",
            "github is a platform",
            "aws is a cloud provider",
            "-----BEGIN PUBLIC KEY-----",
            "bearer of bad news",
            "postgres is a database",
            "the year 1234567890",
        ]
        for text in texts:
            result = redactor.redact(text)
            assert "[REDACTED:" not in result, f"False positive on: '{text}'"

    def test_inv005_empty_string_no_error(self, redactor):
        """INV-005: Empty string doesn't crash."""
        result = redactor.redact("")
        assert result == ""

    def test_inv005_multiple_secrets_in_one_text(self, redactor):
        """INV-005: Multiple secrets in one text are all redacted."""
        text = (
            "Key: sk-aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcdefghij12 "
            "Token: ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789 "
            "AWS: AKIAIOSFODNN7EXAMPLE"
        )
        result = redactor.redact(text)
        assert result.count("[REDACTED:") >= 3

    def test_inv005_excluded_domains_loaded(self, redactor):
        """INV-005: Excluded domains list is loaded from Addendum D."""
        domains = redactor.get_excluded_domains()
        assert len(domains) > 0
        assert "chase.com" in domains
        assert "okta.com" in domains
        assert "localhost" in domains
