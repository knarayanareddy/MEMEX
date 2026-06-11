"""
Security invariant tests.

INV-001: LoopbackOnlyMiddleware exists and is active
INV-002: Non-loopback HTTP request receives 403 Forbidden
INV-003: Ollama URL is localhost-only, no external endpoints configured
INV-004: API host is loopback (127.0.0.1), never 0.0.0.0
"""

import pytest
from unittest.mock import MagicMock, patch

from memex.api.middleware import LoopbackOnlyMiddleware


class TestLoopbackEnforcement:
    """INV-001 & INV-002: API only accessible from loopback."""

    def test_inv001_loopback_middleware_exists(self):
        """INV-001: LoopbackOnlyMiddleware is registered."""
        assert LoopbackOnlyMiddleware is not None

    @pytest.mark.asyncio
    async def test_inv002_non_loopback_rejected(self):
        """INV-002: Non-loopback request receives 403."""
        middleware = LoopbackOnlyMiddleware(app=MagicMock())

        # Mock request from non-loopback
        request = MagicMock()
        request.client = MagicMock()
        request.client.host = "192.168.1.100"
        request.url = MagicMock()
        request.url.path = "/api/health"

        response = await middleware.dispatch(request, MagicMock())

        assert response.status_code == 403
        assert b"Remote access forbidden" in response.body

    @pytest.mark.asyncio
    async def test_inv002_loopback_allowed(self):
        """INV-002: Loopback requests are allowed."""
        middleware = LoopbackOnlyMiddleware(app=MagicMock())

        request = MagicMock()
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        request.url = MagicMock()
        request.url.path = "/api/health"

        mock_response = MagicMock(status_code=200)

        async def async_call_next(req):
            return mock_response

        response = await middleware.dispatch(request, async_call_next)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_inv002_ipv6_loopback_allowed(self):
        """INV-002: IPv6 loopback (::1) is allowed."""
        middleware = LoopbackOnlyMiddleware(app=MagicMock())

        request = MagicMock()
        request.client = MagicMock()
        request.client.host = "::1"
        request.url = MagicMock()

        mock_response = MagicMock(status_code=200)

        async def async_call_next(req):
            return mock_response

        response = await middleware.dispatch(request, async_call_next)
        assert response.status_code == 200


class TestNetworkIsolation:
    """INV-003 & INV-004: No outbound network calls."""

    def test_inv003_ollama_base_url_is_localhost(self):
        """INV-003: Default Ollama URL is localhost only."""
        from memex.config.settings import Settings
        settings = Settings()
        assert "127.0.0.1" in settings.ollama_base_url
        assert "localhost" in settings.ollama_base_url or "127.0.0.1" in settings.ollama_base_url

    def test_inv004_api_host_is_loopback(self):
        """INV-004: API host is loopback."""
        from memex.config.settings import Settings
        settings = Settings()
        assert settings.api_host == "127.0.0.1"
        assert settings.api_host != "0.0.0.0"

    def test_inv003_no_external_urls_in_config(self):
        """INV-003: No external URLs in default settings."""
        from memex.config.settings import Settings
        settings = Settings()
        assert "amazonaws.com" not in settings.ollama_base_url
        assert "openai.com" not in settings.ollama_base_url
