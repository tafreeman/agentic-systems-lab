# Architecture: agentic-systems-lab-tools

## Executive Summary

`agentic-systems-lab-tools` (v0.1.0) is the shared utility layer for the monorepo. It provides a multi-provider LLM client abstraction (10 providers), a disk-backed response cache, model probing and discovery, benchmark infrastructure, a structured error taxonomy, a research library builder, and script bootstrap helpers. It is consumed by `agentic-v2-eval` and by the `agentic-workflows-v2` runtime.

The design follows a **static facade + provider adapters + two-level cache** pattern. Callers never instantiate a client object; they call `LLMClient.generate_text(...)` as a static method. The method dispatches to one of ten provider backends based on a name prefix in the model string. A 24-hour, SHA-256-keyed disk cache sits in front of all provider calls when enabled.

The package is the `uv` workspace root. Members `agentic-workflows-v2` and `agentic-v2-eval` declare it as a workspace dependency.

---

## Technology Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| Language | Python | 3.11+ |
| Build backend | hatchling | `pyproject.toml` as single config source |
| Workspace manager | uv | Workspace root; members: agentic-workflows-v2, agentic-v2-eval |
| Config / rubric parsing | PyYAML | — |
| HTTP (async) | aiohttp | Async provider backends |
| Data validation | pydantic v2 | `model_dump()` / `model_validate()` — not `.dict()` / `.parse_obj()` |
| OpenAI SDK | openai | OpenAI and Azure OpenAI providers |
| Anthropic SDK | anthropic | Claude provider |
| Numeric | numpy | Upper bound `< 3` for semver safety |
| Optional: Google | google-generativeai | Gemini provider |
| Optional: ONNX | onnxruntime-genai | Local ONNX model inference |
| Optional: Windows AI | winrt-runtime | Phi Silica NPU (Copilot+ PC) |

---

## Package Structure

```
tools/
├── llm/                          # 20 modules — LLM client and provider layer
│   ├── llm_client.py             # LLMClient static facade
│   ├── provider_adapters.py      # Dispatch table; all provider adapter classes
│   ├── probe_providers.py        # Model availability probing (all providers)
│   ├── probe_providers_cloud.py  # Cloud-specific probe logic
│   ├── probe_providers_local.py  # Local model probe logic
│   ├── probe_discovery.py        # Cross-provider discovery orchestration
│   ├── probe_discovery_providers.py  # Per-provider discovery helpers
│   ├── probe_config.py           # Probe configuration dataclasses
│   ├── model_probe.py            # ModelProbe class with persistent JSON cache
│   ├── model_inventory.py        # Model inventory management
│   ├── model_locks.py            # Concurrency locks for model loading
│   ├── local_model.py            # ONNX model wrapper
│   ├── local_models.py           # Local model registry
│   ├── local_model_cli.py        # CLI for local model operations
│   ├── local_model_discovery.py  # Auto-detect models from ~/.cache/aigallery
│   ├── model_bakeoff.py          # Multi-model comparison runner
│   ├── bakeoff_tasks.py          # Bakeoff task definitions
│   ├── bakeoff_reporting.py      # Bakeoff result formatting
│   ├── rank_models.py            # Score-based model ranking
│   ├── langchain_adapter.py      # LangChain adapter bridge
│   └── windows_ai.py             # Windows AI (Phi Silica NPU) integration
├── core/                         # 9 modules — shared utilities
│   ├── config.py                 # ModelConfig, PathConfig, Config dataclasses
│   ├── errors.py                 # ErrorCode StrEnum, LLMClientError, classify_error
│   ├── cache.py                  # ResponseCache (SHA-256, 24h TTL, disk-backed)
│   ├── response_cache.py         # Low-level cache read/write primitives
│   ├── _encoding.py              # Internal encoding helpers
│   ├── tool_init.py              # ToolInit bootstrap dataclass + with_retry decorator
│   ├── prompt_db.py              # Prompt template database
│   ├── local_media.py            # Local media file handling
│   └── model_availability.py    # Runtime model availability checks
├── agents/benchmarks/            # 11 modules — benchmark infrastructure
│   ├── registry.py               # BenchmarkRegistry + BENCHMARK_DEFINITIONS
│   ├── config.py                 # BenchmarkConfig dataclass + preset configs
│   ├── datasets.py               # Dataset loaders for each benchmark
│   ├── runner.py                 # BenchmarkRunner (sync)
│   ├── async_runner.py           # AsyncBenchmarkRunner
│   ├── llm_evaluator.py          # LLM-as-judge evaluator (5 weighted dimensions)
│   ├── scoring.py                # Score aggregation and grade assignment
│   ├── reporting.py              # Result formatters
│   ├── task.py                   # BenchmarkTask dataclass
│   ├── loader.py                 # load_benchmark() entry point
│   └── __init__.py               # Public API exports
├── research/                     # 2 modules — research library builder
│   ├── library_builder.py        # build_library() — scan, classify, consolidate
│   └── helpers.py                # URL classification, domain lists
└── tests/                        # 10 test modules — all mocked, no live LLM calls
```

---

## LLM Client

### Interface

```python
class LLMClient:
    @staticmethod
    def generate_text(
        model_name: str,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str: ...
```

`LLMClient` is a pure static-method facade. There is no instance state. Thread safety is delegated to the cache layer, which uses a `threading.Lock` on all read/write operations.

### Call Flow

```
Caller
  └─ LLMClient.generate_text(model_name, prompt, ...)  ← static facade
       ├─ ResponseCache.get(sha256_key)                  ← cache layer
       │    └─ hit → return cached response
       └─ miss → provider_adapters.dispatch(prefix, ...)
            ├─ local:*          → LocalONNXAdapter
            ├─ ollama:*         → OllamaRESTAdapter
            ├─ windows-ai:*     → WindowsAIAdapter (Phi Silica NPU)
            ├─ azure-foundry:*  → AzureFoundryAdapter
            ├─ azure-openai:*   → AzureOpenAIAdapter (slot failover)
            ├─ gh:*             → GitHubModelsAdapter (gh CLI subprocess)
            ├─ openai:*         → OpenAIAdapter
            ├─ gemini:*         → GeminiAdapter
            └─ claude:*         → AnthropicAdapter
```

### Provider Routing

The `model_name` string prefix selects the backend. Unknown prefixes raise `LLMClientError` with `ErrorCode.UNAVAILABLE_MODEL`.

| Prefix | Provider | Backend |
|--------|----------|---------|
| `local:*` | Local ONNX | `onnxruntime-genai`; auto-detects from `~/.cache/aigallery` or `LOCAL_MODEL_PATH` |
| `ollama:*` | Ollama REST | `urllib.request` to `localhost:11434` (default port) |
| `windows-ai:*` | Windows Copilot Runtime (Phi Silica NPU) | `winrt-runtime`; requires Windows 11 Copilot+ PC hardware |
| `azure-foundry:*` | Azure AI Foundry | `urllib.request`; env: `AZURE_FOUNDRY_ENDPOINT`, `AZURE_FOUNDRY_KEY` |
| `azure-openai:*` | Azure OpenAI Service | `openai.AzureOpenAI`; numbered slot failover (`AZURE_OPENAI_API_KEY_0` through `_n`) |
| `gh:*` | GitHub Models | `gh` CLI subprocess; env: `GITHUB_TOKEN`; maps 18+ friendly names to GitHub model IDs |
| `openai:*` | OpenAI | `openai.OpenAI` SDK; env: `OPENAI_API_KEY` |
| `gemini:*` | Google Gemini | `google.generativeai` SDK; env: `GEMINI_API_KEY` |
| `claude:*` | Anthropic Claude | `anthropic.Anthropic` SDK; env: `ANTHROPIC_API_KEY` |

### Remote Provider Gate

Remote providers (OpenAI, Anthropic, Gemini, Azure variants) are disabled by default to prevent accidental spend during local development and CI runs.

| Environment Variable | Default | Effect |
|---------------------|---------|--------|
| `PROMPTEVAL_ALLOW_REMOTE` | unset / `0` | Remote providers raise `LLMClientError(PERMISSION_DENIED)` |
| `PROMPTEVAL_ALLOW_REMOTE=1` | — | All ten providers are active |

Local providers (`local:*`, `ollama:*`, `windows-ai:*`, `gh:*`) are always allowed.

---

## Response Cache

| Property | Value |
|----------|-------|
| Key algorithm | SHA-256 of `(model_name, prompt, system_instruction, temperature, max_tokens)` |
| TTL | 24 hours |
| Storage location | `~/.cache/prompts-eval/responses/` |
| Max size | 500 MB (LRU eviction when exceeded) |
| Thread safety | `threading.Lock` on all read/write operations |
| Enable | `PROMPTS_CACHE_ENABLED=1` |
| Disable | Unset or `PROMPTS_CACHE_ENABLED=0` |

**Disk layout:**

```
~/.cache/prompts-eval/responses/
└── <sha256_hex>.json    # one file per unique (model, prompt, params) combination
```

Each cache entry is a JSON object containing `response`, `model`, `timestamp`, and `ttl_seconds` fields.

Disable the cache when running evaluations that intentionally test stochastic model behavior (for example, the `PatternEvaluator` 20-run median computation), or when exercising cache-miss code paths in tests.

---

## Model Probing (ModelProbe)

`ModelProbe` in `tools/llm/model_probe.py` provides runtime model availability probing with a persistent JSON backing cache.

- `probe(model_name)` — check whether a single model responds to a minimal prompt
- `discover_all_models()` — runs all provider probes in parallel and returns a consolidated list of available models
- Results are written to a JSON file under `~/.cache/prompts-eval/model_probe/` and reused across sessions until invalidated

Provider-specific probe logic lives in `probe_providers_cloud.py` and `probe_providers_local.py`, coordinated by `probe_discovery.py`.

---

## Error Taxonomy

`tools.core.errors` defines a `StrEnum` with ten values and helper functions.

| Code | Meaning | Retryable |
|------|---------|-----------|
| `SUCCESS` | No error | — |
| `UNAVAILABLE_MODEL` | Model not found or not loaded | No |
| `PERMISSION_DENIED` | Remote provider blocked by env gate | No |
| `RATE_LIMITED` | Provider rate limit exceeded | Yes |
| `TIMEOUT` | Request exceeded timeout | Yes |
| `PARSE_ERROR` | Could not parse LLM response | No |
| `FILE_NOT_FOUND` | Required file path does not exist | No |
| `INVALID_INPUT` | Input failed validation | No |
| `NETWORK_ERROR` | Network-level failure | Yes |
| `INTERNAL_ERROR` | Unexpected error in client code | No |

```python
class LLMClientError(RuntimeError):
    code: ErrorCode
    model: str              # model_name that was requested
    original_error: Exception | None
```

Helper functions:

- `classify_error(exc: Exception) -> ErrorCode` — inspects exception type and message to return the appropriate code
- `is_retryable(code: ErrorCode) -> bool` — returns `True` for `RATE_LIMITED`, `TIMEOUT`, `NETWORK_ERROR`, `PARSE_ERROR`
- `is_permanent(code: ErrorCode) -> bool` — convenience inverse of `is_retryable`

Transient error codes (retryable): `RATE_LIMITED`, `TIMEOUT`, `NETWORK_ERROR`, `PARSE_ERROR`.

---

## Config (tools.core.config)

```python
@dataclass
class ModelConfig:
    gen_model: str      # from GEN_MODEL env var
    rev_model: str      # from REV_MODEL env var
    ref_model: str      # from REF_MODEL env var

@dataclass
class PathConfig:
    cache_dir: Path
    model_dir: Path
    output_dir: Path

@dataclass
class Config:
    models: ModelConfig
    paths: PathConfig
```

`default_config()` reads `GEN_MODEL`, `REV_MODEL`, `REF_MODEL` environment variables and returns a `Config` instance. Defaults are applied for unset variables so the package is usable out of the box for local-only providers.

---

## ToolInit and with_retry

`ToolInit` is a dataclass for script bootstrap. It performs startup environment and path checks and writes structured JSONL log entries.

```python
@dataclass
class ToolInit:
    check_env: list[str]        # required env var names
    check_models: list[str]     # required model prefixes to verify
    check_paths: list[str]      # required file/dir paths
    log_file: str | None        # JSONL log path; None = no log
    exit_code: int              # 0 = success after all checks
```

`ToolInit.run()` validates all checks sequentially. On any failure it writes a JSONL error entry and raises `SystemExit` with a non-zero code.

### with_retry Decorator

```python
def with_retry(
    max_attempts: int = 3,
    backoff_base: float = 1.0,
    transient_only: bool = True,
) -> Callable: ...
```

Wraps a function with exponential backoff retry logic. When `transient_only=True` (default), retries only on errors where `is_retryable()` returns `True`. Permanent errors such as `PERMISSION_DENIED` are re-raised immediately without consuming retry budget.

---

## Benchmark Infrastructure

Located in `tools/agents/benchmarks/`. Provides a registry of 8 named benchmarks, an LLM-as-judge evaluator, preset run configurations, and both sync and async runners.

### Supported Benchmarks

| Benchmark ID | Task Count | Description |
|-------------|-----------|-------------|
| `swe-bench` | 2,294 | Full GitHub issue → patch set |
| `swe-bench-verified` | 500 | Manually verified subset |
| `swe-bench-lite` | 300 | Lightweight subset for fast iteration |
| `humaneval` | 164 | OpenAI function synthesis benchmark |
| `humaneval-plus` | 164 | Extended test cases for HumanEval |
| `mbpp` | 974 | Mostly Basic Python Problems |
| `mbpp-sanitized` | 427 | Cleaned subset of MBPP |
| `codeclash` | 100 | Competitive programming problems |
| `custom-local` | variable | User-provided local benchmark |

### BenchmarkTask

```python
@dataclass
class BenchmarkTask:
    task_id: str
    benchmark_id: str
    prompt: str
    instruction: str
    repo: str | None
    base_commit: str | None
    golden_patch: str | None
    test_cases: list[str]
    pass_criteria: str
```

### LLM-as-Judge Evaluator

The benchmark LLM evaluator (`llm_evaluator.py`) scores responses on a 0.0–10.0 scale with five weighted dimensions.

| Dimension | Weight |
|-----------|--------|
| Completeness | 0.25 |
| Correctness | 0.25 |
| Quality | 0.20 |
| Specificity | 0.15 |
| Alignment | 0.15 |

Grade thresholds: A (≥ 9.0), B (≥ 8.0), C (≥ 7.0), D (≥ 6.0), F (< 6.0).

### Preset Configurations

| Preset | Benchmarks Included | Use Case |
|--------|--------------------|-|
| `quick-test` | HumanEval (first 20 tasks) | Fast smoke test |
| `swe-bench-eval` | SWE-bench-verified | Standard SWE-bench run |
| `local-dev` | custom-local | Local iteration |
| `full-eval` | All benchmarks | Complete evaluation suite |

---

## Research Library Builder

`tools.research.library_builder` provides `build_library(sources: list[str]) -> ResearchLibrary`.

- Scans the repository for research materials (markdown files, notebooks, annotated references)
- Classifies source URLs against two domain lists:
  - **Approved domains (35+):** arxiv.org, acm.org, ieee.org, nature.com, openai.com, anthropic.com, huggingface.co, microsoft.com, and similar authoritative sources
  - **Caution domains:** unverified blogs, marketing sites
- Consolidates materials into a `ResearchLibrary` artifact with `coverage_score` and `source_quality_score` fields
- Research gating thresholds (used by evaluation pipelines): `coverage_score >= 0.80`, `source_quality_score >= 0.80`

Domain classification uses keyword heuristics and falls back to an LLM call for ambiguous URLs.

---

## Stable Public API

The following symbols form the cross-package boundary consumed by `agentic-v2-eval` and `agentic-workflows-v2`. They are stable and must not be removed or changed incompatibly.

| Symbol | Module | Description |
|--------|--------|-------------|
| `LLMClient` | `tools.llm.llm_client` | Static LLM facade |
| `LLMClientError` | `tools.llm.llm_client` | Base error class with `code` and `model` fields |
| `LangChainAdapter` | `tools.llm.langchain_adapter` | LangChain-compatible adapter wrapping `LLMClient` |
| `ModelProbe` | `tools.llm.model_probe` | Runtime model availability prober with persistent cache |
| `ErrorCode` | `tools.core.errors` | StrEnum of 10 error codes |
| `classify_error` | `tools.core.errors` | Map exception to `ErrorCode` |
| `is_retryable` | `tools.core.errors` | Check if error code is retryable |
| `ResponseCache` | `tools.core.cache` | Disk-backed SHA-256 response cache |
| `default_config` | `tools.core.config` | Return `Config` from environment variables |
| `init_tool` | `tools.core.tool_init` | Convenience wrapper for `ToolInit.run()` |
| `with_retry` | `tools.core.tool_init` | Exponential backoff retry decorator |
| `BenchmarkRegistry` | `tools.agents.benchmarks.registry` | Registry of all named benchmarks |
| `BenchmarkConfig` | `tools.agents.benchmarks.config` | Run configuration dataclass |
| `load_benchmark` | `tools.agents.benchmarks.loader` | Load tasks for a named benchmark |
| `BENCHMARK_DEFINITIONS` | `tools.agents.benchmarks.registry` | Dict of all registered benchmark metadata |

---

## Testing

| Property | Value |
|----------|-------|
| Test modules | 10 |
| Live LLM calls | None — all providers are mocked |
| asyncio mode | auto (pytest-asyncio) |

```bash
cd tools
pip install -e ".[dev]"
python -m pytest tests/ -v
python -m pytest tests/ --cov=tools --cov-report=term-missing
```

Static analysis:

```bash
mypy --strict tools/
ruff check tools/
```

All test doubles satisfy the same structural protocols as the real implementations, ensuring mocks remain in sync with the actual interface.

---

## Known Issues

### Bare Module Import Paths

**Affected files:** `tools/llm/llm_client.py`, `tools/core/cache.py`

These files contain bare module imports (`from cache import ...`, `from response_cache import ...`) that function when the files are executed directly from their containing directory but silently disable caching when the package is installed conventionally. The Python import resolver cannot find `cache` as a top-level module; the `try/except ImportError` catches the failure, and caching is skipped without any warning to the caller.

**Workaround:** Always install the package with `pip install -e .` (editable mode) from the `tools/` directory, or use the workspace `uv` install, which handles path resolution correctly.

**Fix required:** Change bare imports to relative imports (`from .cache import ...`, `from .response_cache import ...`).
