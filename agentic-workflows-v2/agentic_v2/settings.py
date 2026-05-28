"""Centralised application settings.

All environment variable reads for agentic_v2 core modules go through this
module.  Uses pydantic-settings so the app fails fast at startup when a
required variable is missing, and so that precedence is documented in one
place.

Precedence (highest to lowest):
1. Actual environment variables (``os.environ``)
2. ``.env`` file at the repo root (loaded by pydantic-settings automatically)
3. Defaults defined on the ``Settings`` class

Usage::

    from agentic_v2.settings import get_settings

    settings = get_settings()
    if settings.agentic_tracing:
        ...
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_TRUE_LITERALS = frozenset({"1", "true", "yes", "on"})
_FALSE_LITERALS = frozenset({"", "0", "false", "no", "off"})


class Settings(BaseSettings):
    """Typed application settings sourced from environment variables.

    Precedence: env vars > .env file > field defaults.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- OTEL / tracing ---
    agentic_tracing: bool = Field(default=False, description="Enable OTLP tracing")
    agentic_trace_sensitive: bool = Field(
        default=False, description="Include prompt/response content in traces"
    )
    otel_exporter_otlp_endpoint: str = Field(
        default="http://localhost:4317", description="OTLP exporter endpoint"
    )
    otel_exporter_otlp_protocol: str = Field(
        default="grpc", description="OTLP protocol: grpc or http/protobuf"
    )
    otel_service_name: str = Field(
        default="agentic-workflows-v2", description="Service name for traces"
    )

    # --- Agent loader ---
    agentic_external_agents_dir: str | None = Field(
        default=None, description="Directory containing external agent definitions"
    )

    # --- Runtime ---
    shell: str = Field(default="/bin/bash", description="Shell for subprocess execution")

    # --- LLM placeholder mode ---
    agentic_no_llm: bool = Field(
        default=False,
        description=(
            "When true, get_client() and get_chat_model() both install a "
            "deterministic placeholder so demos and CI can run without API "
            "keys. The native-engine path (get_client()) has no extra "
            "dependencies. The LangChain-adapter path (get_chat_model()) "
            "still requires the [langchain] install extra — without it, "
            "get_chat_model() raises ImportError even under the flag. "
            "Accepted string values (case-insensitive): '1'/'true'/'yes'/"
            "'on' are True; ''/'0'/'false'/'no'/'off' are False; unknown "
            "values are coerced to False with a logged warning. See "
            "docs/NO_LLM_MODE.md."
        ),
    )

    @field_validator("agentic_no_llm", mode="before")
    @classmethod
    def _coerce_no_llm_flag(cls, v: Any) -> bool:
        """Normalise ``AGENTIC_NO_LLM`` env values.

        Pydantic's default bool parser raises ``ValidationError`` on
        unusual strings (``"2"``, stray whitespace, ``"yes"`` in some
        versions), which would surface as an opaque traceback at the
        first LLM call.  We accept the conservative set of literals
        documented in the field description and coerce everything else
        to ``False`` with a warning so operators find out via the log,
        not via a crash (Sprint B #5 follow-up review P2).
        """
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        s = str(v).strip().lower()
        if s in _TRUE_LITERALS:
            return True
        if s in _FALSE_LITERALS:
            return False
        logger.warning(
            "AGENTIC_NO_LLM=%r not recognised; treating as False. "
            "Accepted: %s (True) or %s (False).",
            v,
            sorted(_TRUE_LITERALS),
            sorted(_FALSE_LITERALS),
        )
        return False

    # --- Tool: file operations ---
    agentic_file_base_dir: str | None = Field(
        default=None, description="Base directory for file operations (sandbox root)"
    )

    # --- Tool: HTTP operations ---
    agentic_block_private_ips: bool = Field(
        default=False, description="Block HTTP requests to private/loopback IPs"
    )

    # --- Tool: memory operations ---
    agentic_memory_path: str | None = Field(
        default=None, description="Path to persistent memory store"
    )

    # --- MCP ---
    max_mcp_output_tokens: int | None = Field(
        default=None, description="Token budget cap for MCP tool output"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()
