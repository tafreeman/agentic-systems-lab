# Deep-Dive: Server (`agentic-workflows-v2/agentic_v2/server/`)

**Generated:** 2026-04-17
**Files analyzed:** 23
**Total LOC:** 6,589
**Target type:** folder
**Scan mode:** exhaustive

---

## Overview

The `server/` package is the HTTP/WebSocket/SSE boundary of the `agentic-workflows-v2` runtime. It wraps the execution engines, agent registry, and evaluation pipeline behind a FastAPI application that serves both the REST API and the Vite-built React SPA.

**Responsibilities:**
- HTTP API for workflows, agents, runs, datasets, evaluation (`routes/`)
- Async workflow execution and event broadcast (`execution.py`)
- WebSocket/SSE streaming hub with replay buffer (`websocket.py`)
- Auth (bearer + X-API-Key) with constant-time comparison (`auth.py`)
- Prompt sanitization middleware (`middleware/__init__.py`)
- Evaluation pipeline: hard gates → criterion scoring → optional LLM judge (`evaluation.py`, `evaluation_scoring.py`, `judge.py`, `scoring_*.py`)
- Dataset discovery, loading, matching, adaptation (`datasets.py`, `dataset_matching.py`)
- Pydantic request/response contracts (`models.py`)

---

## API Surface

### REST Endpoints (16)

| Method | Path | Auth | Purpose | Source |
|---|---|---|---|---|
| GET | `/api/health` | public | Liveness probe | `routes/health.py` |
| GET | `/api/agents` | optional | Agent discovery from YAML | `routes/agents.py` |
| GET | `/api/workflows` | optional | List available workflows | `routes/workflows.py` |
| GET | `/api/workflows/{name}/dag` | optional | DAG nodes/edges/schema | `routes/workflows.py` |
| GET | `/api/workflows/{name}/capabilities` | optional | Workflow I/O declarations | `routes/workflows.py` |
| GET | `/api/workflows/{name}/editor` | optional | Load workflow YAML | `routes/workflows.py` |
| PUT | `/api/workflows/{name}/editor` | optional | Save workflow YAML | `routes/workflows.py` |
| GET | `/api/adapters` | optional | List execution adapters | `routes/workflows.py` |
| POST | `/api/run` | optional | Execute workflow (async) | `routes/runs.py` |
| GET | `/api/runs` | optional | Paginated run history | `routes/runs.py` |
| GET | `/api/runs/summary` | optional | Aggregate run statistics | `routes/runs.py` |
| GET | `/api/runs/{filename}` | optional | Full run detail | `routes/runs.py` |
| GET | `/api/runs/{run_id}/stream` | optional | SSE event stream | `execution.py` |
| GET | `/api/eval/datasets` | optional | Repository + local dataset discovery | `routes/evaluation_routes.py` |
| GET | `/api/workflows/{name}/preview-dataset-inputs` | optional | Dataset-field mapping preview | `routes/evaluation_routes.py` |
| POST | `/api/eval/run` | optional | Evaluation run | `routes/evaluation_routes.py` |

### WebSocket

| Path | Auth | Purpose |
|---|---|---|
| `/ws/execution/{run_id}` | required (token + origin) | Real-time step/workflow/evaluation events |

### SSE

| Path | Auth | Purpose |
|---|---|---|
| `/api/runs/{run_id}/stream` | optional | Server-sent events mirroring WS stream |

---

## Module Inventory

### `__init__.py` — 7 LOC
- **Purpose:** Package marker; re-exports FastAPI app factory.
- **Exports:** `create_app` (re-export).
- **Used by:** `python -m uvicorn agentic_v2.server.app:app` entry.

### `app.py` — 171 LOC
- **Purpose:** FastAPI application factory. Wires CORS, auth dependency, sanitization middleware, router registration, SPA static serving, and lifespan for startup/shutdown.
- **Key exports:** `create_app() -> FastAPI`, `app` (module-level instance), `get_auth_dependency()`.
- **Imports:** `fastapi`, `fastapi.middleware.cors`, `..middleware.sanitization`, `.auth`, `.routes`, `..integrations.otel` (optional).
- **Used by:** uvicorn entry point; tests via `from agentic_v2.server.app import create_app`.
- **Implementation details:** conditional OTEL instrumentation; lifespan manages `WorkflowRunner` singleton creation; serves `ui/dist/` when built.
- **Side effects:** starts background tasks, opens OTEL exporters.
- **Risks:** global `_lc_runner` singleton — no re-init protection; SPA mount hides API 404s as HTML.
- **Verification:** `curl localhost:8010/api/health`; ensure `ui/dist` exists before building prod image.
- **Suggested tests:** lifespan startup/teardown, CORS preflight, SPA fallback routing.

### `auth.py` — 234 LOC
- **Purpose:** Bearer token + `X-API-Key` authentication dependency with constant-time comparison. Also validates WebSocket origin headers.
- **Key exports:** `AuthSettings`, `verify_token()`, `require_auth()` (FastAPI dependency), `validate_websocket_origin()`.
- **Imports:** `hmac`, `secrets`, `fastapi.Security`, `pydantic_settings`.
- **Implementation:** reads `AGENTIC_API_TOKEN` env; empty token disables auth (dev mode); uses `hmac.compare_digest` to prevent timing attacks.
- **Risks:** Origin whitelist from env — misconfig allows CSRF via WS.
- **Suggested tests:** timing-attack unit test (fixed latency); origin allow/deny matrix.

### `datasets.py` — 444 LOC
- **Purpose:** Dataset discovery and loading. Supports repository (HuggingFace/GitHub), local JSON files, and predefined eval sets. Flexible sample extraction from top-level list, or dict with `tasks`/`samples`/`items` keys.
- **Key exports:** `list_datasets()`, `load_dataset(name)`, `resolve_local_dataset(path)`, `DatasetDescriptor`.
- **Imports:** `httpx` (optional), `pathlib`, `json`.
- **Used by:** `routes/evaluation_routes.py`, `evaluation.py`.
- **Risks:** Path traversal possible if caller doesn't sanitize `name`; uses `is_within_base()` guard.
- **Suggested tests:** malformed JSON (non-list, non-dict), missing files, symlink escape, network failure for HF/GitHub.

### `dataset_matching.py` — 564 LOC
- **Purpose:** Heuristic field-name mapping between dataset sample fields and workflow input schema. E.g. `"file"` inputs search for `code_file`, `patch`, `path`. Handles type coercion (JSON parsing, stringifying) and file materialization (`.py`, `.txt`).
- **Key exports:** `match_sample_to_inputs(sample, schema)`, `materialize_file_input()`, `FieldMatch`.
- **Risks:** Silent failures if sample structure unexpected — prefer explicit field map in workflow YAML.
- **Suggested tests:** edge cases (nested fields, arrays, None values), file materialization with weird extensions, traversal attempts.

### `evaluation.py` — 144 LOC
- **Purpose:** Orchestrates the 3-stage evaluation pipeline: hard gates → criterion scoring → LLM judge. Thin glue layer.
- **Key exports:** `evaluate_workflow_result(result, criteria, judge)`, `EvaluationOutcome`.
- **Used by:** `execution.py`, `routes/evaluation_routes.py`.
- **Side effects:** Optional LLM call if judge configured.
- **Suggested tests:** pipeline ordering, short-circuit on hard-gate failure.

### `evaluation_scoring.py` — 762 LOC
- **Purpose:** Aggregation and grading. Weighted blend of criterion scores with advisory heuristics (similarity, efficiency). Maps to A/B/C/D/F grades. Includes multidimensional profiles.
- **Key exports:** `aggregate_scores()`, `compute_grade()`, `ScoringResult`, `GradeBand`.
- **Risks:** Any single hard-gate failure forces grade F — no partial credit.
- **Suggested tests:** grade boundary values (89.5, 79.5), hard-gate failure pinning, weighted blend correctness.

### `execution.py` — 520 LOC
- **Purpose:** Async workflow execution orchestrator. Handles LangGraph streaming, event broadcasting (step_start, step_end, workflow_end, evaluation_complete), SSE queues, result normalization, and run logging.
- **Key exports:** `execute_workflow_async()`, `stream_events(run_id)`, `_lc_runner` (global singleton).
- **Imports:** `..langchain.WorkflowRunner`, `..engine.context.ExecutionContext`, `..adapters`, `.websocket`, `.result_normalization`.
- **Risks:** Global `_lc_runner` singleton — not thread-safe; assumes single event loop.
- **Suggested tests:** concurrent run isolation, event ordering under load, adapter fallback.

### `judge.py` — 579 LOC
- **Purpose:** LLM-as-judge with anchored 1–5 Likert rubric. Positional bias mitigation via deterministic criteria shuffling. Optional pairwise consistency check. Strict JSON schema validation. Temperature clamped [0.0, 0.1].
- **Key exports:** `LLMJudge`, `judge_result()`, `detect_calibration_drift()`.
- **Imports:** `..models.client`, Pydantic for validation.
- **Risks:** Pairwise 2x LLM calls expensive; positional bias not fully eliminated.
- **Suggested tests:** calibration MAE on human-labeled fixtures, schema rejection of malformed judge output, shuffle determinism.

### `models.py` — 396 LOC
- **Purpose:** Pydantic v2 schemas for all REST contracts (request + response). Central source of truth for API types.
- **Key exports:** `RunRequest`, `RunResponse`, `WorkflowDescriptor`, `EvalRequest`, `JudgeConfig`, ~30 more.
- **Used by:** all `routes/` modules.
- **Risks:** Additive-only per CLAUDE.md — never remove fields.
- **Suggested tests:** schema round-trip, optional-field defaults, enum coverage.

### `multidimensional_scoring.py` — 549 LOC
- **Purpose:** Advanced multi-axis scoring profile: correctness, quality, efficiency, documentation. Supports custom weight profiles.
- **Key exports:** `MultidimensionalScorer`, `ScoringProfile`.
- **Used by:** `evaluation_scoring.py`.

### `normalization.py` — 35 LOC
- **Purpose:** Thin re-export facade for `result_normalization` (backward-compat).
- **Used by:** external imports referencing legacy path.

### `result_normalization.py` — 448 LOC
- **Purpose:** Converts runner-specific result shapes (LangChain, native engine) to contract `WorkflowResult`. Handles nested `AgentOutput`, tool traces, step metadata.
- **Key exports:** `normalize_langchain_result()`, `normalize_native_result()`.
- **Risks:** Breaking schema drift in runners → silent field loss; add schema version assertions.

### `scoring_criteria.py` — 487 LOC
- **Purpose:** Per-criterion 0–100 scoring from execution signals: success rate, text overlap, step failures, duration, output richness. 4 criterion families.
- **Key exports:** `CriterionScorer`, `score_correctness()`, `score_quality()`, `score_efficiency()`, `score_documentation()`.

### `scoring_profiles.py` — 139 LOC
- **Purpose:** Named scoring profiles (default, strict, lenient). Weight maps per criterion.
- **Key exports:** `PROFILES`, `get_profile(name)`.

### `websocket.py` — 261 LOC
- **Purpose:** Pub/sub hub. Bounded deque (500 events) for replay; async fan-out to WS + SSE subscribers.
- **Key exports:** `WebSocketHub`, `publish_event()`, `subscribe(run_id)`.
- **Risks:** Server restart loses history; deque truncation silently drops old events.
- **Suggested tests:** backpressure, subscriber drop mid-stream, replay correctness.

### `middleware/__init__.py` — 58 LOC
- **Purpose:** ASGI sanitization wrapper. Applies prompt-sanitization rules from `..middleware.sanitization`.
- **Risks:** May redact legitimate model code/pseudocode in prompts.

### `routes/__init__.py` — 14 LOC
- **Purpose:** Router aggregation. Exports `router` including health, agents, workflows, runs, evaluation.

### `routes/agents.py` — 74 LOC
- **Purpose:** `GET /api/agents` — enumerates agents from `prompts/*.md` with metadata (persona, capabilities).

### `routes/evaluation_routes.py` — 156 LOC
- **Purpose:** Evaluation endpoints — dataset listing, dataset preview mapping, evaluation run trigger.

### `routes/health.py` — 21 LOC
- **Purpose:** `GET /api/health` → `{"status": "ok", "version": ...}`.

### `routes/runs.py` — 191 LOC
- **Purpose:** Run history, pagination, filesystem-backed run log reading. Uses `is_within_base()` path guard.
- **Risks:** Path traversal via symlinks — ensure `resolve()` before `is_relative_to()`.

### `routes/workflows.py` — 335 LOC
- **Purpose:** Workflow discovery, DAG visualization, capabilities, YAML editor (GET/PUT), adapter listing.
- **Risks:** PUT endpoint writes YAML to disk — YAML injection risk if auth disabled.
- **Suggested tests:** YAML round-trip, invalid YAML rejection, adapter enumeration.

---

## Dependency Graph (within `server/`)

```
app.py
  ├─ routes/__init__.py
  │   ├─ routes/health.py
  │   ├─ routes/agents.py
  │   ├─ routes/workflows.py → models.py
  │   ├─ routes/runs.py → execution.py → websocket.py, result_normalization.py
  │   └─ routes/evaluation_routes.py → datasets.py, dataset_matching.py, evaluation.py
  ├─ auth.py
  ├─ middleware/__init__.py
  └─ websocket.py

evaluation.py
  ├─ evaluation_scoring.py
  │   ├─ scoring_criteria.py
  │   ├─ scoring_profiles.py
  │   └─ multidimensional_scoring.py
  └─ judge.py

normalization.py → result_normalization.py (shim)
```

No circular dependencies. `models.py` is leaf-shared by all route modules.

---

## Data Flow

**Inbound HTTP → response:**
1. Client → FastAPI → CORS → sanitization middleware → auth dependency → router.
2. Router validates request via `models.py` Pydantic schema.
3. For `POST /api/run`: handler kicks off `execute_workflow_async()` which returns run_id, then streams events via `websocket.py` hub.
4. `execution.py` invokes `WorkflowRunner` (LangChain) or native engine adapter.
5. Events flow: engine → `websocket.publish_event()` → deque + fan-out to all subscribers.
6. On completion: `result_normalization` → `evaluation.evaluate_workflow_result()` (if evaluation requested) → persisted to run log (`RunLogger`).

**Streaming:**
- WebSocket: client subscribes `/ws/execution/{run_id}` → auth/origin check → subscribe to hub → receive replay buffer + live events.
- SSE: `GET /api/runs/{run_id}/stream` → same hub, different transport.

---

## Integration Points

- **`..contracts`**: `WorkflowResult`, `AgentOutput`, `StepResult` (additive-only Pydantic models).
- **`..langchain`**: `WorkflowRunner` (LangGraph wrapper) — optional dependency.
- **`..engine.context`**: `ExecutionContext` for native DAG executor.
- **`..adapters`**: `AdapterRegistry` for pluggable execution backends.
- **`..models`**: `get_client()`, `get_secret()`, `SmartModelRouter`, model-tier resolution.
- **`..middleware.sanitization`**: prompt sanitization rules.
- **`..integrations.otel`**: OpenTelemetry tracing (optional).
- **External**: `tools.agents.benchmarks`, HuggingFace Datasets, GitHub raw files.

---

## Risks & Gotchas

1. **Global `_lc_runner` singleton** in `execution.py` — not thread-safe; presumes single-threaded event loop.
2. **In-memory event buffer** (`websocket.py`) — bounded deque; server restart loses history.
3. **Optional LangChain dependency** — many routes return 501 if `[langchain]` extras not installed.
4. **Heuristic field matching** (`dataset_matching.py`) — best-effort; surface mapping preview in UI.
5. **Hard-gate enforcement** (`evaluation_scoring.py`) — any single gate failure forces grade F.
6. **Judge pairwise consistency** — 2x LLM calls; doesn't fully eliminate positional bias.
7. **Path traversal** in `routes/runs.py` — relies on `is_within_base()`; resolve symlinks before check.
8. **Sanitization middleware** — may redact legitimate code/pseudocode in prompts.
9. **YAML editor PUT** (`routes/workflows.py`) — requires auth; YAML injection risk otherwise.
10. **Additive-only contracts** — `models.py` must never drop fields per project convention.

---

## Verification Steps

Before shipping changes to `server/`:

1. `pip install -e ".[dev,server,langchain]"` from `agentic-workflows-v2/`.
2. `python -m uvicorn agentic_v2.server.app:app --host 127.0.0.1 --port 8010` — confirm startup.
3. `curl http://127.0.0.1:8010/api/health` — expect `200 {"status":"ok"}`.
4. `curl http://127.0.0.1:8010/api/workflows` — expect non-empty list.
5. Run `python -m pytest tests/ -k "server or api or evaluation"` — full suite green.
6. Hit `POST /api/run` with a minimal workflow; confirm WS + SSE stream events.
7. `pre-commit run --all-files` — mypy strict, ruff, black.

---

## Suggested Tests

- **Auth**: timing-attack fixed-latency assert; malformed `Authorization` header rejection.
- **WebSocket**: concurrent subscribers, replay buffer correctness, origin whitelist.
- **Execution**: isolated run IDs under load (100+ concurrent `POST /api/run`).
- **Evaluation**: hard-gate strictness, grade band boundaries, judge calibration MAE.
- **Datasets**: malformed JSON, path traversal, symlink escape, HF/GitHub network failure.
- **Judge**: positional-bias regression test, schema rejection of malformed output.
- **Routes/runs**: pagination correctness, symlink traversal rejection.
- **Routes/workflows**: YAML round-trip, invalid YAML rejection.
- **Middleware**: sanitization preserves legitimate code blocks.
- **Result normalization**: schema version assertion on runner output drift.

---

## Related Code & Reuse Opportunities

- **`tools.agents.benchmarks.llm_evaluator`** mirrors judge.py rubric scoring — consider unifying.
- **`agentic_v2_eval.runners`** has parallel streaming runner — extract shared streaming abstraction.
- **`agentic_v2.adapters`** `AdapterRegistry` pattern is reusable for other plugin points (scorer backends, judge backends).
- **Event hub** in `websocket.py` could be generalized into `core/events.py` for non-HTTP pub/sub.
- **Path-guard** `is_within_base()` should be promoted to `core/paths.py` and unit-tested against symlink attacks.
- **Scoring profiles** are YAML-serializable — consider moving to `agentic-v2-eval/rubrics/`.
