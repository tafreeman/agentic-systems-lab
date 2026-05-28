"""Tests for the fail-closed ``SanitizationASGIMiddleware`` ASGI wrapper.

These are adversarial regression tests for Sprint 1 Ticket 01: the middleware
must return HTTP 500 (not silently pass through) when a registered detector
raises an unexpected exception.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from agentic_v2.server.middleware import SanitizationASGIMiddleware


class _ExplodingDetector:
    """Stub sanitizer whose ``process`` always raises — simulates a detector bug."""

    async def process(self, text: str, metadata: dict[str, Any]) -> None:
        raise RuntimeError("detector exploded")


async def _echo(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


def _make_app(detector: Any) -> Starlette:
    app = Starlette(routes=[Route("/run", _echo, methods=["POST"])])
    app.state.sanitization = detector
    app.add_middleware(SanitizationASGIMiddleware)
    return app


async def test_exploding_detector_returns_500() -> None:
    """A detector that raises must trigger fail-closed HTTP 500, not pass-through."""
    app = _make_app(_ExplodingDetector())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/run",
            json={"workflow": "test"},
            headers={"content-type": "application/json"},
        )
    assert response.status_code == 500
    assert response.json()["detail"] == "Internal sanitization error"


async def test_no_sanitizer_passes_through() -> None:
    """When sanitizer is not mounted, requests pass through normally."""
    app = _make_app(None)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/run",
            json={"workflow": "test"},
            headers={"content-type": "application/json"},
        )
    assert response.status_code == 200


async def test_non_json_content_type_bypasses_sanitizer() -> None:
    """Non-JSON content types must bypass the detector (and thus not explode)."""
    app = _make_app(_ExplodingDetector())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/run",
            content=b"plain text body",
            headers={"content-type": "text/plain"},
        )
    assert response.status_code == 200


async def test_fail_open_escape_hatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """With AGENTIC_SANITIZER_FAIL_OPEN=1, detector errors fall back to pass-through."""
    monkeypatch.setenv("AGENTIC_SANITIZER_FAIL_OPEN", "1")
    app = _make_app(_ExplodingDetector())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/run",
            json={"workflow": "test"},
            headers={"content-type": "application/json"},
        )
    assert response.status_code == 200
