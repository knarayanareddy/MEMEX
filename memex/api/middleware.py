"""
Middleware for MEMEX API.

- Loopback-only enforcement
- Request timing
- Request ID injection
"""

from __future__ import annotations

import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ..observability.logging import get_logger

logger = get_logger("api.middleware")


class LoopbackOnlyMiddleware(BaseHTTPMiddleware):
    """Reject any request from non-loopback addresses.

    INV-001: API server never binds to non-loopback.
    INV-002: Non-loopback HTTP request receives 403.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_host = request.client.host if request.client else "unknown"

        # Allow loopback and test client
        allowed = ("127.0.0.1", "::1", "localhost", "testclient")
        if client_host not in allowed:
            logger.warning(
                "non_loopback_request_rejected",
                client_host=client_host,
                path=str(request.url.path),
            )
            return Response(
                content="Remote access forbidden",
                status_code=403,
                media_type="text/plain",
            )

        return await call_next(request)


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Add request timing and request ID to all responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())[:8]
        start = time.monotonic()

        response = await call_next(request)

        duration_ms = (time.monotonic() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Duration-Ms"] = f"{duration_ms:.2f}"

        return response
