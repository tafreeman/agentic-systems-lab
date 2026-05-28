"""API key authentication middleware for the Agentic server.

Implements a single-key bearer-token gate using Starlette's
``BaseHTTPMiddleware``.

Authentication behavior:
    * When ``AGENTIC_API_KEY`` is set in the environment, every HTTP
      request whose path starts with ``/api/`` (except public prefixes
      like ``/api/health``, ``/docs``, ``/openapi.json``, ``/redoc``)
      must supply the key via ``Authorization: Bearer <key>`` or the
      ``X-API-Key: <key>`` header.  Token comparison uses
      :func:`secrets.compare_digest` to prevent timing side-channels.
    * When the env var is **not** set, the middleware is a no-op and all
      requests are allowed (local development mode).
    * Non-API routes (UI static files, WebSocket upgrade) bypass
      authentication entirely so the React frontend can load without
      credentials.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlparse

from fastapi.responses import JSONResponse
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)

from ..models.secrets import SecretProvider, get_secret

if TYPE_CHECKING:
    from fastapi import Request, WebSocket

logger = logging.getLogger(__name__)

# Paths that bypass authentication
_PUBLIC_PREFIXES = ("/api/health", "/docs", "/openapi.json", "/redoc")
_DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8010",
    "http://127.0.0.1:8010",
)


@dataclass(frozen=True)
class AuthToken:
    """Resolved authentication token and its transport."""

    value: str
    source: Literal["authorization", "x-api-key", "query"]

    @property
    def is_deprecated_transport(self) -> bool:
        """Query-string tokens are a compatibility fallback only."""
        return self.source == "query"


def _get_api_key(provider: SecretProvider | None = None) -> str | None:
    """Read the API key from the environment on each call.

    This allows key rotation without a full server restart.
    """
    return get_secret("AGENTIC_API_KEY", provider=provider)


def get_allowed_origins(provider: SecretProvider | None = None) -> list[str]:
    """Return configured browser origins for CORS and WebSocket validation."""
    raw = get_secret("AGENTIC_CORS_ORIGINS", provider=provider)
    if raw:
        return [_normalize_origin(item) for item in raw.split(",") if item.strip()]
    return list(_DEFAULT_CORS_ORIGINS)


def is_public_path(path: str) -> bool:
    """Return True when *path* should bypass API key authentication."""
    if not path.startswith("/api/"):
        return True
    return any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES)


def extract_http_token(request: Request) -> AuthToken | None:
    """Extract an API key from HTTP headers."""
    return _extract_token_from_headers(request.headers)


def extract_websocket_token(websocket: WebSocket) -> AuthToken | None:
    """Extract an API key from WebSocket headers."""
    return _extract_token_from_headers(websocket.headers)


def websocket_uses_query_token(websocket: WebSocket) -> bool:
    """Return True when a WebSocket handshake still carries a query token."""
    return bool((websocket.query_params.get("token") or "").strip())


def is_token_authorized(token: str | None, api_key: str | None) -> bool:
    """Compare *token* with the configured API key using constant time."""
    if api_key is None:
        return True
    return token is not None and secrets.compare_digest(token, api_key)


def is_websocket_origin_allowed(
    websocket: WebSocket, allowed_origins: list[str] | None = None
) -> bool:
    """Validate browser origins for WebSocket handshakes.

    Non-browser clients often omit the Origin header; those requests are
    allowed. Browser requests must either come from an explicitly
    allowed origin, use a wildcard allowlist, or match the current Host
    header exactly.
    """
    origin = _normalize_origin(websocket.headers.get("origin"))
    if origin is None:
        return True

    host = websocket.headers.get("host", "")
    if _origin_matches_host(origin, host):
        return True

    for allowed in allowed_origins or get_allowed_origins():
        if allowed == "*" or _normalize_origin(allowed) == origin:
            return True
    return False


def build_auth_error_response() -> JSONResponse:
    """Return the standard API auth failure payload."""
    return JSONResponse(
        status_code=401,
        content={"detail": "Invalid or missing API key"},
    )


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that enforces bearer-token authentication on ``/api/``
    routes.

    When ``AGENTIC_API_KEY`` is not set, all requests pass through unchanged.
    Otherwise, requests to protected paths must include a valid token via
    ``Authorization: Bearer <key>`` or ``X-API-Key: <key>``.  Invalid or
    missing tokens receive a ``401`` JSON response.

    Attributes:
        Inherits from ``BaseHTTPMiddleware``; no additional instance state.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        api_key = _get_api_key()
        if api_key is None:
            return await call_next(request)

        path = request.url.path

        # Allow public endpoints and non-API routes (UI static files)
        if is_public_path(path):
            return await call_next(request)

        # Check for API key in headers
        token = extract_http_token(request)
        if token is None or not is_token_authorized(token.value, api_key):
            client_host = request.client.host if request.client else "unknown"
            logger.warning("Authentication failed for %s from %s", path, client_host)
            return build_auth_error_response()

        return await call_next(request)


def _extract_token(request: Request) -> str | None:
    """Backward-compatible token extraction helper for tests."""
    token = extract_http_token(request)
    return token.value if token is not None else None


def _extract_token_from_headers(headers) -> AuthToken | None:
    """Extract API key from Authorization or X-API-Key header."""
    # Try Authorization: Bearer <key>
    auth_header = headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return AuthToken(value=token, source="authorization")

    # Try X-API-Key header
    api_key_header = headers.get("x-api-key")
    if api_key_header:
        token = api_key_header.strip()
        if token:
            return AuthToken(value=token, source="x-api-key")

    return None


def _normalize_origin(origin: str | None) -> str | None:
    if origin is None:
        return None
    normalized = origin.strip().rstrip("/")
    return normalized or None


def _origin_matches_host(origin: str, host: str) -> bool:
    """Return True when *origin* targets the same host as the request."""
    parsed_origin = urlparse(origin)
    if not parsed_origin.hostname:
        return False

    origin_scheme = parsed_origin.scheme or "http"
    origin_host = parsed_origin.hostname.lower()
    origin_port = parsed_origin.port or _default_port(origin_scheme)

    parsed_host = urlparse(f"//{host}")
    if not parsed_host.hostname:
        return False

    host_name = parsed_host.hostname.lower()
    host_port = parsed_host.port or _default_port(origin_scheme)
    return origin_host == host_name and origin_port == host_port


def _default_port(scheme: str) -> int | None:
    if scheme in {"http", "ws"}:
        return 80
    if scheme in {"https", "wss"}:
        return 443
    return None
