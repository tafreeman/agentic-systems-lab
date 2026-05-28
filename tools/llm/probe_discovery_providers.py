"""Per-provider probe functions for model discovery.

Each function probes one provider and returns a result dict suitable for
insertion into ``discovered["providers"][key]``.  All functions are
pure (no side-effects on shared state) so they can be called
independently or tested in isolation.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

from tools.llm.llm_client import LLMClient
from tools.llm.probe_config import (
    AI_GALLERY_CACHE_DIR,
    AITK_HOME_DIR,
    AITK_MODELINFO_FILE,
    AITK_MODELS_DIR,
    AITK_MODELS_TASK_TYPE,
    AITK_MS_SUBDIR,
    AITK_SUFFIX_CPU,
    AITK_SUFFIX_GENERIC_CPU,
    AITK_SUFFIX_GENERIC_GPU,
    AITK_SUFFIX_GPU,
    AITK_TRAILING_CHARS,
    AZURE_SLOT_RANGE,
    CACHE_BASE_DIR,
    DOTNET_CLI_ARG_PROJECT,
    ENDPOINT_TRUNCATION_LENGTH,
    ENV_ANTHROPIC_API_KEY,
    ENV_AZURE_FOUNDRY_API_KEY,
    ENV_AZURE_FOUNDRY_ENDPOINT_PREFIX,
    ENV_AZURE_OPENAI_API_KEY,
    ENV_AZURE_OPENAI_DEPLOYMENT,
    ENV_AZURE_OPENAI_ENDPOINT,
    ENV_GEMINI_API_KEY,
    ENV_GH_TOKEN,
    ENV_GITHUB_TOKEN,
    ENV_GOOGLE_API_KEY,
    ENV_LMSTUDIO_HOST,
    ENV_LOCAL_AI_API_BASE_URL,
    ENV_LOCAL_OPENAI_BASE_URL,
    ENV_OLLAMA_HOST,
    ENV_OPENAI_API_BASE,
    ENV_OPENAI_API_KEY,
    ENV_OPENAI_BASE_URL,
    ERROR_BRIEF_LENGTH,
    GH_CLI_OUTPUT_MODELS_LIMIT,
    LMSTUDIO_DEFAULT_HOST,
    LOCAL_SERVER_COMMON_PORTS,
    OLLAMA_API_TAGS_ENDPOINT,
    OLLAMA_DEFAULT_HOST,
    PATH_SEPARATOR,
    PLATFORM_WINDOWS,
    PREFIX_AITK,
    PREFIX_CLAUDE,
    PREFIX_GEMINI,
    PREFIX_GITHUB,
    PREFIX_LMSTUDIO,
    PREFIX_LOCAL,
    PREFIX_LOCAL_API,
    PREFIX_OLLAMA,
    PREFIX_OPENAI,
    TAB_SEPARATOR,
    TIMEOUT_CLOUD_HTTP,
    TIMEOUT_GH_AUTH,
    TIMEOUT_GH_MODELS_LIST,
    TIMEOUT_OLLAMA_HTTP,
    TIMEOUT_WINDOWS_AI_BRIDGE,
    WINDOWS_AI_BRIDGE_DIR,
    WINDOWS_AI_BRIDGE_PROJECT,
    WINDOWS_AI_CLI_ARG_INFO,
    WINDOWS_AI_MODEL_ID,
)

logger = logging.getLogger(__name__)


def _probe_local_onnx(verbose: bool = False) -> dict[str, Any]:
    """Probe local ONNX models from the AI Gallery cache."""
    import shutil

    ai_gallery = Path.home() / CACHE_BASE_DIR / AI_GALLERY_CACHE_DIR
    local_models: list[str] = []
    local_missing: list[str] = []

    try:
        from tools.llm.llm_client import LLMClient

        for key, model_path in LLMClient.LOCAL_MODELS.items():
            top_dir = str(model_path).split(PATH_SEPARATOR)[0]
            if ai_gallery.exists() and (ai_gallery / top_dir).exists():
                local_models.append(f"{PREFIX_LOCAL}{key}")
            else:
                local_missing.append(f"{PREFIX_LOCAL}{key}")
    except Exception as e:
        if verbose:
            logger.error("  Error: %s", e)

    return {
        "available": local_models,
        "missing": local_missing,
        "count": len(local_models),
        "path": str(ai_gallery),
    }


def _probe_github_models() -> dict[str, Any]:
    """Probe GitHub Models via the gh CLI."""
    import shutil

    gh_models: list[str] = []
    gh_error = None
    gh_authenticated = False

    if shutil.which("gh"):
        try:
            auth_check = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_GH_AUTH,
            )
            gh_authenticated = auth_check.returncode == 0
        except Exception:
            pass

        if not gh_authenticated:
            gh_authenticated = bool(
                os.getenv(ENV_GITHUB_TOKEN) or os.getenv(ENV_GH_TOKEN)
            )

    if gh_authenticated:
        try:
            result = subprocess.run(
                ["gh", "models", "list"],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_GH_MODELS_LIST,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        parts = line.split(TAB_SEPARATOR)
                        if parts:
                            model_id = parts[0].strip()
                            if model_id:
                                gh_models.append(f"{PREFIX_GITHUB}{model_id}")
            else:
                gh_error = (
                    result.stderr[:ERROR_BRIEF_LENGTH]
                    if result.stderr
                    else "Unknown error"
                )
        except Exception as e:
            gh_error = str(e)
    else:
        gh_error = "gh CLI not available or not authenticated (run: gh auth login)"

    return {
        "available": gh_models,
        "count": len(gh_models),
        "error": gh_error,
    }


def _probe_ollama() -> dict[str, Any]:
    """Probe Ollama for locally running models."""
    ollama_host = os.getenv(ENV_OLLAMA_HOST, OLLAMA_DEFAULT_HOST)
    ollama_models: list[str] = []
    ollama_error = None

    try:
        req = urllib.request.Request(
            f"{ollama_host}{OLLAMA_API_TAGS_ENDPOINT}",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_OLLAMA_HTTP) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            ollama_models = [
                f"{PREFIX_OLLAMA}{m.get('name', '')}" for m in data.get("models", [])
            ]
    except Exception:
        ollama_error = f"Ollama not reachable at {ollama_host}"

    return {
        "available": ollama_models,
        "count": len(ollama_models),
        "host": ollama_host,
        "error": ollama_error,
    }


def _probe_azure_foundry() -> dict[str, Any]:
    """Probe Azure Foundry configuration."""
    foundry_configured = bool(os.getenv(ENV_AZURE_FOUNDRY_API_KEY))
    foundry_endpoints: list[str] = []
    for k, v in os.environ.items():
        if k.startswith(ENV_AZURE_FOUNDRY_ENDPOINT_PREFIX) and v:
            foundry_endpoints.append(v)

    return {
        "configured": foundry_configured and bool(foundry_endpoints),
        "endpoints": foundry_endpoints,
        "notes": "Azure Foundry models require explicit model IDs (azure-foundry:model-name)",
    }


def _probe_azure_openai() -> dict[str, Any]:
    """Probe Azure OpenAI slot configuration."""
    azure_slots: list[dict[str, Any]] = []
    for i in range(AZURE_SLOT_RANGE):
        ep = os.getenv(f"{ENV_AZURE_OPENAI_ENDPOINT}_{i}")
        key = os.getenv(f"{ENV_AZURE_OPENAI_API_KEY}_{i}")
        deployment = os.getenv(f"{ENV_AZURE_OPENAI_DEPLOYMENT}_{i}")
        if ep and key:
            azure_slots.append(
                {
                    "slot": i,
                    "endpoint": (
                        ep[:ENDPOINT_TRUNCATION_LENGTH] + "..."
                        if len(ep) > ENDPOINT_TRUNCATION_LENGTH
                        else ep
                    ),
                    "deployment": deployment,
                }
            )

    if os.getenv(ENV_AZURE_OPENAI_ENDPOINT) and os.getenv(ENV_AZURE_OPENAI_API_KEY):
        azure_slots.append(
            {
                "slot": "default",
                "endpoint": os.getenv(ENV_AZURE_OPENAI_ENDPOINT, "")[
                    :ENDPOINT_TRUNCATION_LENGTH
                ],
                "deployment": os.getenv(ENV_AZURE_OPENAI_DEPLOYMENT),
            }
        )

    return {
        "configured": bool(azure_slots),
        "slots": azure_slots,
        "notes": "Use azure-openai:deployment-name to specify model",
    }


def _probe_openai() -> dict[str, Any]:
    """Probe OpenAI direct API for available models."""
    openai_configured = bool(os.getenv(ENV_OPENAI_API_KEY))
    openai_models: list[str] = []

    if openai_configured:
        try:
            openai_models = [
                f"{PREFIX_OPENAI}{m}" for m in LLMClient.list_openai_models()[:20]
            ]
        except Exception:
            openai_models = [
                f"{PREFIX_OPENAI}gpt-4o",
                f"{PREFIX_OPENAI}gpt-4o-mini",
                f"{PREFIX_OPENAI}gpt-4-turbo",
            ]

    return {
        "configured": openai_configured,
        "available": openai_models,
        "count": len(openai_models),
    }


def _probe_gemini() -> dict[str, Any]:
    """Probe Google Gemini API for available models."""
    gemini_key = os.getenv(ENV_GEMINI_API_KEY) or os.getenv(ENV_GOOGLE_API_KEY)
    gemini_configured = bool(gemini_key)
    gemini_models: list[str] = []
    gemini_error = None

    if gemini_configured:
        try:
            url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=50"
            req = urllib.request.Request(
                url,
                headers={"Accept": "application/json", "x-goog-api-key": gemini_key},
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT_CLOUD_HTTP) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for m in data.get("models", []):
                    name = m.get("name", "")
                    if name.startswith("models/"):
                        short = name.replace("models/", "")
                        gemini_models.append(f"{PREFIX_GEMINI}{short}")
        except Exception as e:
            gemini_error = str(e)[:ERROR_BRIEF_LENGTH]
            gemini_models = [
                f"{PREFIX_GEMINI}gemini-2.5-flash",
                f"{PREFIX_GEMINI}gemini-2.0-flash",
                f"{PREFIX_GEMINI}gemini-2.0-flash-lite",
            ]
    else:
        gemini_error = "No GEMINI_API_KEY or GOOGLE_API_KEY environment variable"

    gemini_keys_found: list[str] = []
    for i in range(10):
        k = os.getenv(f"GEMINI_API_KEY_{i}")
        if k:
            gemini_keys_found.append(f"GEMINI_API_KEY_{i}")

    return {
        "configured": gemini_configured,
        "available": gemini_models,
        "count": len(gemini_models),
        "rotation_keys": gemini_keys_found,
        "error": gemini_error,
    }


def _probe_anthropic() -> dict[str, Any]:
    """Probe Anthropic Claude API for available models."""
    anthropic_key = os.getenv(ENV_ANTHROPIC_API_KEY)
    anthropic_configured = bool(anthropic_key)
    anthropic_models: list[str] = []
    anthropic_error = None

    if anthropic_configured:
        try:
            url = "https://api.anthropic.com/v1/models?limit=50"
            req = urllib.request.Request(
                url,
                headers={
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT_CLOUD_HTTP) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for m in data.get("data", []):
                    model_id = m.get("id", "")
                    if model_id:
                        anthropic_models.append(f"{PREFIX_CLAUDE}{model_id}")
        except Exception as e:
            anthropic_error = str(e)[:ERROR_BRIEF_LENGTH]
            anthropic_models = [
                f"{PREFIX_CLAUDE}claude-sonnet-4-20250514",
                f"{PREFIX_CLAUDE}claude-haiku-4-20250414",
            ]
    else:
        anthropic_error = "No ANTHROPIC_API_KEY environment variable"

    anthropic_keys_found: list[str] = []
    for i in range(10):
        k = os.getenv(f"ANTHROPIC_API_KEY_{i}")
        if k:
            anthropic_keys_found.append(f"ANTHROPIC_API_KEY_{i}")

    return {
        "configured": anthropic_configured,
        "available": anthropic_models,
        "count": len(anthropic_models),
        "rotation_keys": anthropic_keys_found,
        "error": anthropic_error,
    }


def _probe_windows_ai(bridge_dir: Path) -> dict[str, Any]:
    """Probe Windows AI (Phi Silica) via the .NET bridge project."""
    import shutil

    windows_ai_available = False
    windows_ai_error = None
    windows_ai_ready_state = None

    if sys.platform == PLATFORM_WINDOWS and shutil.which("dotnet"):
        bridge_proj = bridge_dir / WINDOWS_AI_BRIDGE_DIR / WINDOWS_AI_BRIDGE_PROJECT
        if bridge_proj.exists():
            try:
                result = subprocess.run(
                    [
                        "dotnet",
                        "run",
                        DOTNET_CLI_ARG_PROJECT,
                        str(bridge_proj),
                        "--",
                        WINDOWS_AI_CLI_ARG_INFO,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=TIMEOUT_WINDOWS_AI_BRIDGE,
                    cwd=str(bridge_proj.parent),
                )
                stdout = (result.stdout or "").strip()
                stderr = (result.stderr or "").strip()

                info = None
                if stdout:
                    try:
                        info = json.loads(stdout)
                    except Exception:
                        info = None

                if isinstance(info, dict):
                    windows_ai_available = bool(info.get("available", False))
                    windows_ai_ready_state = info.get("readyState")
                    if not windows_ai_available:
                        windows_ai_error = info.get("error") or stderr or "Unknown"
                else:
                    windows_ai_error = stderr or stdout or "Bridge did not return JSON"
            except Exception as e:
                windows_ai_error = str(e)
        else:
            windows_ai_error = "Bridge project not found"
    else:
        windows_ai_error = "Windows only / dotnet not available"

    return {
        "available": windows_ai_available,
        "readyState": windows_ai_ready_state,
        "models": [WINDOWS_AI_MODEL_ID] if windows_ai_available else [],
        "error": windows_ai_error,
    }


def _probe_aitk() -> dict[str, Any]:
    """Probe AI Toolkit local ONNX models from VS Code AI Toolkit."""
    aitk_base = Path.home() / AITK_HOME_DIR
    aitk_models_dir = aitk_base / AITK_MODELS_DIR
    aitk_modelinfo = aitk_models_dir / AITK_MODELINFO_FILE

    aitk_models: list[str] = []
    aitk_catalog: list[str] = []
    aitk_error = None

    if not aitk_base.exists():
        aitk_error = "AI Toolkit not installed (run: code --install-extension ms-windows-ai-studio.windows-ai-studio)"
    elif not aitk_models_dir.exists():
        aitk_error = "No AI Toolkit models downloaded"
    else:
        downloaded: list[str] = []
        for subdir in aitk_models_dir.iterdir():
            if subdir.is_dir() and subdir.name != AITK_MS_SUBDIR:
                downloaded.append(subdir.name)
        ms_dir = aitk_models_dir / AITK_MS_SUBDIR
        if ms_dir.exists():
            for subdir in ms_dir.iterdir():
                if subdir.is_dir():
                    downloaded.append(subdir.name)

        for d in downloaded:
            simple_name = d.lower()
            for suffix in [
                AITK_SUFFIX_GENERIC_CPU,
                AITK_SUFFIX_GENERIC_GPU,
                AITK_SUFFIX_CPU,
                AITK_SUFFIX_GPU,
            ]:
                if suffix in simple_name:
                    simple_name = simple_name.split(suffix)[0]
            while simple_name and simple_name[-1].isdigit():
                simple_name = simple_name.rstrip(AITK_TRAILING_CHARS)
            aitk_models.append(f"{PREFIX_AITK}{simple_name}")

        aitk_models = list(dict.fromkeys(aitk_models))

        if aitk_modelinfo.exists():
            try:
                info = json.loads(aitk_modelinfo.read_text(encoding="utf-8"))
                for m in info.get("models", []):
                    if m.get("task") == AITK_MODELS_TASK_TYPE:
                        alias = m.get("alias", "")
                        if alias:
                            catalog_id = f"{PREFIX_AITK}{alias}"
                            if catalog_id not in aitk_models:
                                aitk_catalog.append(catalog_id)
            except Exception:
                pass

    return {
        "available": aitk_models,
        "count": len(aitk_models),
        "catalog": aitk_catalog[:GH_CLI_OUTPUT_MODELS_LIMIT],
        "path": str(aitk_models_dir) if aitk_models_dir.exists() else None,
        "error": aitk_error,
        "notes": "FREE local ONNX models via VS Code AI Toolkit (NOT cloud/paid)",
    }


def _probe_lmstudio() -> dict[str, Any]:
    """Probe LM Studio OpenAI-compatible local server."""
    lmstudio_host = os.getenv(ENV_LMSTUDIO_HOST, LMSTUDIO_DEFAULT_HOST)
    lmstudio_models: list[str] = []
    lmstudio_error = None
    lmstudio_reachable = False

    try:
        lm_url = f"{lmstudio_host.rstrip('/')}/v1/models"
        req = urllib.request.Request(lm_url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for m in data.get("data", []):
                mid = m.get("id", "") if isinstance(m, dict) else ""
                if mid:
                    lmstudio_models.append(f"{PREFIX_LMSTUDIO}{mid}")
            lmstudio_reachable = True
    except Exception as e:
        lmstudio_error = f"LM Studio not reachable at {lmstudio_host}: {str(e)[:100]}"

    return {
        "configured": lmstudio_reachable,
        "host": lmstudio_host,
        "reachable": lmstudio_reachable,
        "available": lmstudio_models,
        "count": len(lmstudio_models),
        "error": lmstudio_error,
        "notes": (
            "Queries OpenAI-compatible API (/v1/models) since native REST "
            "(/api/v1/chat) lacks Custom Tool support. Override host with "
            "LMSTUDIO_HOST."
        ),
    }


def _probe_local_openai_compatible(lmstudio_host: str = "") -> dict[str, Any]:
    """Probe generic OpenAI-compatible local servers (LocalAI, text-gen-webui, etc.)."""
    local_api_base = (
        os.getenv(ENV_OPENAI_BASE_URL)
        or os.getenv(ENV_OPENAI_API_BASE)
        or os.getenv(ENV_LOCAL_AI_API_BASE_URL)
        or os.getenv(ENV_LOCAL_OPENAI_BASE_URL)
    )

    local_api_models: list[str] = []
    local_api_error = None
    local_api_host: str | None = local_api_base
    local_api_reachable = False

    if local_api_base:
        try:
            la_url = f"{local_api_base.rstrip('/')}/v1/models"
            req = urllib.request.Request(la_url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for m in data.get("data", []):
                    mid = m.get("id", "") if isinstance(m, dict) else ""
                    if mid:
                        local_api_models.append(f"{PREFIX_LOCAL_API}{mid}")
                local_api_reachable = True
        except Exception as e:
            local_api_error = (
                f"Local API not reachable at {local_api_base}: {str(e)[:100]}"
            )
    else:
        for port in LOCAL_SERVER_COMMON_PORTS:
            if lmstudio_host and f":{port}" in lmstudio_host:
                continue
            try:
                scan_url = f"http://localhost:{port}/v1/models"
                req = urllib.request.Request(
                    scan_url, headers={"Accept": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=1) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    for m in data.get("data", []):
                        mid = m.get("id", "") if isinstance(m, dict) else ""
                        if mid:
                            local_api_models.append(f"{PREFIX_LOCAL_API}{mid}")
                    if local_api_models:
                        local_api_host = f"http://localhost:{port}"
                        local_api_reachable = True
                        break
            except Exception:
                continue
        if not local_api_reachable:
            local_api_error = "No local API server found (set OPENAI_BASE_URL or LOCAL_AI_API_BASE_URL)"

    return {
        "configured": local_api_reachable,
        "host": local_api_host,
        "reachable": local_api_reachable,
        "available": local_api_models,
        "count": len(local_api_models),
        "error": local_api_error,
        "notes": "Any OpenAI-compatible local server (LocalAI, AMD ROCm, text-gen-webui, etc.)",
    }
