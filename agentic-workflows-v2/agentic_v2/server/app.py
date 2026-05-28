"""FastAPI application factory for the Agentic Workflows V2 server.

Provides :func:`create_app`, which assembles the FastAPI instance with:

* **CORS middleware** -- origins configurable via ``AGENTIC_CORS_ORIGINS`` env var
  (comma-separated), defaulting to common localhost development ports.
* **API key authentication** -- opt-in via ``AGENTIC_API_KEY`` env var
  (see :mod:`~agentic_v2.server.auth`).
* **Route registration** -- health, agents, workflows (under ``/api/``), plus
  the WebSocket streaming endpoint at ``/ws/execution/{run_id}``.
* **SPA static serving** -- when the built React frontend exists under
  ``ui/dist/``, static assets are served at ``/assets/`` and all remaining
  paths fall through to ``index.html`` (client-side routing).
* **Lifespan handler** -- on startup, probes available LLM providers and
  updates tier defaults for both the LangGraph and native DAG engines;
  on shutdown, flushes OpenTelemetry spans.

A module-level ``app`` instance is created for use by ``uvicorn`` or the
``agentic serve`` CLI command.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..integrations.otel import is_tracing_enabled, shutdown_tracing
from . import websocket
from .auth import APIKeyMiddleware, _get_api_key, get_allowed_origins
from .routes import agents, evaluation_routes, health, runs, workflows

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Built frontend assets directory
UI_DIST_DIR = Path(__file__).resolve().parent.parent.parent / "ui" / "dist"
UI_DIST_DIR_RESOLVED = UI_DIST_DIR.resolve()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage server startup and shutdown lifecycle.

    Startup:
        Probes all configured LLM providers (GitHub Models, OpenAI,
        Anthropic, Gemini, Ollama) and updates the tier-to-model
        default mappings for both the LangGraph and native engines.

    Shutdown:
        Flushes and shuts down OpenTelemetry tracing if enabled.

    Yields:
        Control to the FastAPI event loop for the duration of the
        server's lifetime.
    """
    logger.info("Starting Agentic Workflows V2 Server")

    # Warn if API key auth is not configured
    if not _get_api_key():
        logger.warning(
            "AGENTIC_API_KEY is not set — all API routes are publicly accessible. "
            "Set this env var to enable authentication."
        )

    # Probe available LLM providers and update tier defaults for both engines
    try:
        from ..langchain.models import probe_and_update_tier_defaults

        summary = probe_and_update_tier_defaults()
        logger.info(
            "LLM providers: available=%s, unavailable=%s",
            summary["available_providers"],
            summary["unavailable_providers"],
        )
    except ImportError:
        logger.warning("LangChain extras not installed — skipping LLM provider probe")

    # Initialize sanitization middleware
    # Enforcement mode: dry_run=False blocks/redacts unsafe content
    try:
        from ..middleware.sanitization import SanitizationMiddleware

        app.state.sanitization = SanitizationMiddleware.default(dry_run=False)
        logger.info("Sanitization middleware initialized (dry_run=False)")
    except Exception:
        logger.exception("Failed to initialize sanitization middleware")
        app.state.sanitization = None

    if is_tracing_enabled():
        logger.info("OpenTelemetry tracing is enabled")
    yield
    logger.info("Shutting down Agentic Workflows V2 Server")
    shutdown_tracing()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Assembles middleware (CORS, API key auth), registers API route groups
    under ``/api/``, mounts the WebSocket endpoint, and optionally serves
    the built React SPA from ``ui/dist/``.

    Returns:
        A fully configured ``FastAPI`` instance ready for ``uvicorn``.
    """
    app = FastAPI(
        title="Agentic Workflows V2 API",
        description="REST API for multi-model AI workflow orchestration",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_allowed_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "X-API-Key", "Content-Type", "Accept"],
    )

    # API key authentication (opt-in via AGENTIC_API_KEY env var)
    app.add_middleware(APIKeyMiddleware)

    # Sanitization middleware (wraps app.state.sanitization set in lifespan)
    from .middleware import SanitizationASGIMiddleware

    app.add_middleware(SanitizationASGIMiddleware)

    # Include routes
    app.include_router(health.router, prefix="/api")
    app.include_router(agents.router, prefix="/api")
    app.include_router(workflows.router, prefix="/api")
    app.include_router(evaluation_routes.router, prefix="/api")
    app.include_router(runs.router, prefix="/api")
    app.include_router(websocket.router)

    # Serve built frontend in production (after API routes so they take priority)
    if UI_DIST_DIR.exists():
        # Serve static assets (JS, CSS, etc.)
        app.mount(
            "/assets", StaticFiles(directory=str(UI_DIST_DIR / "assets")), name="assets"
        )

        # SPA fallback: serve index.html for all non-API, non-asset routes
        index_html = UI_DIST_DIR / "index.html"

        @app.get("/{path:path}")
        async def spa_fallback(request: Request, path: str):
            # Serve actual files if they exist in dist/, but prevent directory traversal
            if path:
                candidate_path = (UI_DIST_DIR_RESOLVED / path).resolve()
                # Ensure the resolved candidate path is within the UI_DIST_DIR_RESOLVED tree
                if (
                    candidate_path == UI_DIST_DIR_RESOLVED
                    or UI_DIST_DIR_RESOLVED in candidate_path.parents
                ) and candidate_path.is_file():
                    return FileResponse(candidate_path)
            return FileResponse(index_html)

        logger.info("Serving UI from %s", UI_DIST_DIR)

    return app


# Create global app instance
app = create_app()
