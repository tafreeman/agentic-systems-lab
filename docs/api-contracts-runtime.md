# API Contracts — Runtime Backend

**Package:** `agentic-workflows-v2`
**Base URL:** `http://localhost:8010`
**OpenAPI spec:** `/openapi.json` | **Swagger UI:** `/docs` | **ReDoc:** `/redoc`

---

## Table of Contents

1. [Authentication](#authentication)
2. [REST Endpoints](#rest-endpoints)
   - [Health](#health)
   - [Agents](#agents)
   - [Workflows](#workflows)
   - [Runs](#runs)
   - [Evaluation](#evaluation)
3. [WebSocket Streaming](#websocket-streaming)
4. [Server-Sent Events (SSE)](#server-sent-events-sse)
5. [SPA Fallback](#spa-fallback)
6. [Error Responses](#error-responses)
7. [Rate Limiting and Safety](#rate-limiting-and-safety)

---

## Authentication

### Mechanism

Authentication uses a single shared API key configured via the `AGENTIC_API_KEY` environment variable.

| Header | Format | Example |
|--------|--------|---------|
| `Authorization` | `Bearer <key>` | `Authorization: Bearer sk-abc123` |
| `X-API-Key` | `<key>` | `X-API-Key: sk-abc123` |

Either header is accepted. Key comparison uses `secrets.compare_digest()` to prevent timing attacks.

### Open Mode

When `AGENTIC_API_KEY` is unset, the server operates in **open mode**: all endpoints accept requests without authentication. Open mode is intended for local development only and must not be used in production.

### Public Paths

The following paths bypass authentication and are always accessible:

- `GET /api/health`
- `GET /docs`
- `GET /openapi.json`
- `GET /redoc`

### Auth Errors

| Status | Body | Condition |
|--------|------|-----------|
| `401 Unauthorized` | `{"detail": "Missing API key"}` | No auth header provided |
| `403 Forbidden` | `{"detail": "Invalid API key"}` | Key present but incorrect |

---

## REST Endpoints

All endpoints are prefixed with `/api/`. Request and response bodies are JSON (`Content-Type: application/json`) unless noted.

---

### Health

#### `GET /api/health`

Liveness probe. Returns server status and version. No authentication required.

**Request:** No body, no parameters.

**Response `200 OK`:**

```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | `string` | Always `"ok"` when the service is reachable |
| `version` | `string` | Package version from build metadata |

---

### Agents

#### `GET /api/agents`

Returns all agents declared in the active agent configuration files. Requires authentication.

**Request:** No body, no parameters.

**Response `200 OK` (`ListAgentsResponse`):**

```json
{
  "agents": [
    {
      "name": "coder",
      "description": "Generates and refactors source code",
      "capabilities": ["code_generation", "refactoring"],
      "model_tier": "standard"
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `agents` | `AgentInfo[]` | Array of agent descriptors |
| `agents[].name` | `string` | Unique agent identifier |
| `agents[].description` | `string` | Human-readable description |
| `agents[].capabilities` | `string[]` | List of declared capability keys |
| `agents[].model_tier` | `string` | LLM routing tier (`fast`, `standard`, `powerful`) |

---

### Workflows

#### `GET /api/workflows`

Lists all available workflow names discovered from `workflows/definitions/`. Requires authentication.

**Request:** No body, no parameters.

**Response `200 OK` (`ListWorkflowsResponse`):**

```json
{
  "workflows": ["code-review", "research", "multi-agent-collab"]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `workflows` | `string[]` | Workflow names (filename stem, no `.yaml` extension) |

---

#### `GET /api/adapters`

Lists all registered execution engine adapters. Requires authentication.

**Request:** No body, no parameters.

**Response `200 OK`:**

```json
{
  "adapters": [
    {
      "name": "native",
      "description": "Native DAG executor (Kahn's algorithm)",
      "available": true
    },
    {
      "name": "langchain",
      "description": "LangGraph state machine engine",
      "available": true
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `adapters` | `object[]` | Registered adapter descriptors |
| `adapters[].name` | `string` | Adapter key used in `WorkflowRunRequest.adapter` |
| `adapters[].available` | `boolean` | `false` if the optional dependency is not installed |

---

#### `GET /api/workflows/{name}/dag`

Returns the DAG topology for a workflow for use by the UI graph canvas. Requires authentication.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `string` | Workflow name (matches YAML filename stem) |

**Response `200 OK` (`DAGResponse`):**

```json
{
  "nodes": [
    { "id": "step-1", "label": "Coder", "type": "agent", "agent": "coder" }
  ],
  "edges": [
    { "source": "step-1", "target": "step-2" }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `nodes` | `DAGNodeModel[]` | Workflow step nodes |
| `nodes[].id` | `string` | Step identifier from YAML |
| `nodes[].label` | `string` | Display name |
| `nodes[].type` | `string` | Node type (e.g., `agent`, `gateway`) |
| `nodes[].agent` | `string \| null` | Agent assigned to this step |
| `edges` | `DAGEdgeModel[]` | Dependency edges |
| `edges[].source` | `string` | Source step `id` |
| `edges[].target` | `string` | Target step `id` |

**Error `404 Not Found`:** Workflow name not found.

---

#### `GET /api/workflows/{name}/capabilities`

Returns the declared input/output schema capabilities for a workflow. Requires authentication.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `string` | Workflow name |

**Response `200 OK`:**

```json
{
  "workflow": "code-review",
  "capabilities": {
    "inputs": { "code": "string", "language": "string" },
    "outputs": { "review": "string", "issues": "array" }
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `workflow` | `string` | Workflow name |
| `capabilities` | `object` | Nested `inputs` and `outputs` field maps |

---

#### `GET /api/workflows/{name}/editor`

Returns the raw YAML source of a workflow definition for in-browser editing. Requires authentication.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `string` | Workflow name |

**Response `200 OK` (`WorkflowEditorResponse`):**

```json
{
  "name": "code-review",
  "yaml_content": "name: code-review\nsteps:\n  ...",
  "is_valid": true,
  "validation_errors": []
}
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | `string` | Workflow name |
| `yaml_content` | `string` | Raw YAML text |
| `is_valid` | `boolean` | Whether the current YAML passes schema validation |
| `validation_errors` | `string[]` | Validation error messages when `is_valid` is `false` |

**Error `404 Not Found`:** Workflow not found.

---

#### `PUT /api/workflows/{name}`

Validates and persists a workflow YAML definition. Requires authentication.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `string` | Workflow name (must match the `name` field inside the YAML body) |

**Request Body (`WorkflowEditorRequest`):**

```json
{
  "name": "code-review",
  "yaml_content": "name: code-review\nsteps:\n  ..."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` | Yes | Workflow name |
| `yaml_content` | `string` | Yes | Full YAML text to validate and persist |

**Response `200 OK`:** Same shape as `GET /api/workflows/{name}/editor`.

**Error `422 Unprocessable Entity`:** YAML parse error or schema validation failure. The `validation_errors` array in the response body contains details.

---

#### `POST /api/workflows/validate`

Validates a workflow YAML definition without persisting it. Intended for real-time editor feedback. Requires authentication.

**Request Body:** Same as `WorkflowEditorRequest`.

**Response `200 OK` (`WorkflowValidationResponse`):**

```json
{
  "is_valid": false,
  "errors": [
    "Step 'step-2' references unknown agent 'unknown-agent'"
  ],
  "warnings": []
}
```

| Field | Type | Description |
|-------|------|-------------|
| `is_valid` | `boolean` | `true` if no blocking errors were found |
| `errors` | `string[]` | Blocking validation errors |
| `warnings` | `string[]` | Non-blocking advisory messages |

---

#### `POST /api/run`

Dispatches a workflow execution as a background task and returns immediately with a `run_id` for tracking. Requires authentication.

**Request Body (`WorkflowRunRequest`):**

```json
{
  "workflow": "code-review",
  "inputs": { "code": "def foo(): pass", "language": "python" },
  "adapter": "native",
  "run_id": null
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `workflow` | `string` | Yes | — | Workflow name to execute |
| `inputs` | `object` | Yes | — | Key-value input mapping passed to the first step |
| `adapter` | `string` | No | `"native"` | Execution engine adapter name |
| `run_id` | `string \| null` | No | Auto-generated UUID | Client-supplied run identifier for idempotency |

**Response `202 Accepted` (`WorkflowRunResponse`):**

```json
{
  "run_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "status": "queued"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | `string` | UUID identifying this execution |
| `status` | `string` | Initial status (`"queued"`) |

**Error `404 Not Found`:** Workflow not found.
**Error `409 Conflict`:** A run with the supplied `run_id` is already active.

---

### Runs

#### `GET /api/runs`

Lists past run log summaries. Requires authentication.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `workflow` | `string` | — | Filter by workflow name (optional) |
| `limit` | `integer` | `50` | Maximum number of results to return |

**Response `200 OK`:** Array of `RunSummaryModel`.

```json
[
  {
    "run_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "workflow": "code-review",
    "status": "success",
    "started_at": "2026-04-16T10:00:00Z",
    "completed_at": "2026-04-16T10:00:45Z",
    "duration_ms": 45000,
    "step_count": 3,
    "error": null
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | `string` | Unique run identifier |
| `workflow` | `string` | Workflow name |
| `status` | `string` | Final status: `success`, `failed`, or `running` |
| `started_at` | `string` | ISO 8601 start timestamp |
| `completed_at` | `string \| null` | ISO 8601 completion timestamp; `null` if still running |
| `duration_ms` | `integer \| null` | Total wall-clock duration in milliseconds |
| `step_count` | `integer` | Number of steps executed |
| `error` | `string \| null` | Error message when `status` is `"failed"` |

---

#### `GET /api/runs/summary`

Returns aggregate statistics across all runs, optionally filtered by workflow. Requires authentication.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `workflow` | `string` | Filter by workflow name (optional) |

**Response `200 OK` (`RunsSummaryResponse`):**

```json
{
  "total_runs": 120,
  "successful_runs": 105,
  "failed_runs": 15,
  "success_rate": 0.875,
  "avg_duration_ms": 32400,
  "workflows": ["code-review", "research"]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `total_runs` | `integer` | Total number of runs in scope |
| `successful_runs` | `integer` | Count of runs with `status == "success"` |
| `failed_runs` | `integer` | Count of runs with `status == "failed"` |
| `success_rate` | `float` | Fraction of successful runs (0.0–1.0) |
| `avg_duration_ms` | `float \| null` | Mean wall-clock duration across completed runs |
| `workflows` | `string[]` | Distinct workflow names in scope |

---

#### `GET /api/runs/{filename}`

Returns the full detail of a single run log file. The `filename` parameter is the JSON log filename stored on disk (typically `{run_id}.json`). Requires authentication.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `filename` | `string` | Run log filename (e.g., `f47ac10b.json`) |

**Response `200 OK`:** Full `WorkflowResultModel` JSON, including all step results, outputs, and metadata.

**Error `404 Not Found`:** Log file not found.
**Security note:** The server applies path containment to prevent directory traversal.

---

#### `GET /api/runs/{run_id}/stream`

Opens a Server-Sent Events stream for live execution progress of the specified run. Buffered events are replayed before live events begin. See [Server-Sent Events](#server-sent-events-sse) for event types. Requires authentication.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `run_id` | `string` | Run UUID to subscribe to |

**Authentication note:** Because browser `EventSource` cannot set custom headers, this endpoint also accepts a `token` query parameter as a fallback:

```
GET /api/runs/{run_id}/stream?token=<api-key>
```

**Response:** `text/event-stream` (HTTP 200, chunked transfer encoding).

If the run has already completed, all buffered events are replayed in order before the stream closes naturally.

---

### Evaluation

#### `GET /api/eval/datasets`

Lists available evaluation datasets, optionally filtered by workflow. Requires authentication.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `workflow` | `string` | Filter datasets compatible with this workflow (optional) |

**Response `200 OK` (`ListEvaluationDatasetsResponse`):**

```json
{
  "datasets": [
    {
      "id": "python-snippets-v1",
      "name": "Python Snippets v1",
      "description": "100 Python code samples for review evaluation",
      "sample_count": 100,
      "compatible_workflows": ["code-review"]
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `datasets` | `EvaluationDatasetOption[]` | Available dataset descriptors |
| `datasets[].id` | `string` | Dataset identifier |
| `datasets[].name` | `string` | Human-readable display name |
| `datasets[].description` | `string` | Short description of dataset content |
| `datasets[].sample_count` | `integer` | Number of samples in the dataset |
| `datasets[].compatible_workflows` | `string[]` | Workflows this dataset targets |

---

#### `GET /api/workflows/{name}/preview-dataset-inputs`

Previews the resolved input mapping for a specific dataset sample before running it. Used by the UI to confirm dataset-to-workflow field alignment. Requires authentication.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `string` | Workflow name |

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `dataset_source` | `string` | Yes | Dataset source identifier |
| `dataset_id` | `string` | Yes | Dataset ID within the source |
| `sample_index` | `integer` | No | Zero-based sample index (default `0`) |

**Response `200 OK`:** JSON object mapping workflow input field names to resolved sample values.

```json
{
  "code": "def greet(name):\n    return f'Hello, {name}'",
  "language": "python"
}
```

---

## WebSocket Streaming

### Endpoint

```
WS /ws/execution/{run_id}
```

Provides real-time execution event streaming for a workflow run. On connection, the server replays buffered events (up to the last 500) before emitting live events. This allows late-joining clients — such as a browser tab reloaded mid-run — to recover the full run history without re-executing.

### Authentication

Since browser WebSocket APIs support custom headers only via subprotocol negotiation, authentication is accepted via multiple mechanisms:

| Mechanism | How |
|-----------|-----|
| `Authorization` header | `Bearer <key>` |
| `X-API-Key` header | `<key>` |
| `?token` query parameter | `?token=<key>` (browser fallback) |

### Connection Lifecycle

1. Client connects to `WS /ws/execution/{run_id}`.
2. Server immediately replays all buffered events (up to 500) in chronological order.
3. Server streams live events until the run completes.
4. Server sends a final `workflow_end` event and closes the connection with a normal close frame.

### Message Format

Each WebSocket message is a JSON-serialized event object:

```json
{
  "event": "step_end",
  "data": {
    "step_id": "step-1",
    "status": "success",
    "duration_ms": 1240,
    "output": { "review": "LGTM" }
  },
  "timestamp": "2026-04-16T10:00:12Z"
}
```

See the [SSE Events](#sse-events) table for all event types and their payload fields.

---

## Server-Sent Events (SSE)

### Transport

`GET /api/runs/{run_id}/stream` delivers events as `text/event-stream`. Each event follows the standard SSE wire format:

```
event: step_end
data: {"step_id":"step-1","status":"success","duration_ms":1240}

```

A blank line terminates each event. The `keepalive` event is sent approximately every 15 seconds to prevent proxy and load balancer timeout disconnections.

### SSE Events

| Event | Payload Fields | Description |
|-------|---------------|-------------|
| `workflow_start` | `run_id`, `workflow`, `adapter`, `started_at` | Emitted once when execution begins |
| `step_start` | `step_id`, `agent`, `inputs` | Emitted when a step begins execution |
| `step_end` | `step_id`, `status`, `output`, `duration_ms`, `error` | Emitted when a step completes (success or failure) |
| `workflow_end` | `run_id`, `status`, `duration_ms`, `outputs` | Emitted once when the entire workflow finishes |
| `evaluation_start` | `run_id`, `evaluator`, `rubric` | Emitted when an evaluation pass begins |
| `evaluation_complete` | `run_id`, `scores`, `summary` | Emitted when evaluation scoring is complete |
| `error` | `code`, `message`, `step_id` | Emitted on unrecoverable execution error |
| `keepalive` | _(empty data field)_ | Periodic heartbeat every ~15 seconds |

### Replay Buffer

Both the SSE stream and the WebSocket endpoint maintain an in-process circular buffer of the last **500 events** per run. This buffer persists for the lifetime of the server process. There is no external message broker — event history beyond what is buffered in memory is available only by reading the persisted JSON run-log file via `GET /api/runs/{filename}`.

---

## SPA Fallback

For any request path that does not match a defined API endpoint, the server attempts to serve the compiled frontend application:

```
GET /{path:path}  →  ui/dist/index.html
```

This catch-all route is active only when `ui/dist/index.html` exists on the filesystem. If the file is absent (e.g., in a backend-only deployment), unmatched paths return `404 Not Found`.

This pattern enables client-side routing in the React SPA without requiring server-side route configuration for each UI page.

---

## Error Responses

All error responses use FastAPI's standard JSON error envelope:

```json
{
  "detail": "Human-readable error message"
}
```

For `422 Unprocessable Entity` (request body validation failures), FastAPI returns a structured body with per-field details:

```json
{
  "detail": [
    {
      "loc": ["body", "workflow"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### Status Code Reference

| Code | Meaning |
|------|---------|
| `200 OK` | Request succeeded |
| `202 Accepted` | Asynchronous task dispatched successfully |
| `400 Bad Request` | Malformed request body |
| `401 Unauthorized` | Authentication header missing |
| `403 Forbidden` | Invalid API key |
| `404 Not Found` | Requested resource does not exist |
| `409 Conflict` | Duplicate run ID conflict |
| `422 Unprocessable Entity` | Request schema or YAML validation failure |
| `500 Internal Server Error` | Unexpected server-side error |

---

## Rate Limiting and Safety

The runtime server does not enforce HTTP-level rate limiting at the application layer. In production, rate limiting should be applied at the reverse proxy or API gateway tier (e.g., nginx, AWS API Gateway, Cloudflare).

The following safety controls are enforced at the application layer:

| Control | Mechanism |
|---------|-----------|
| Input sanitization | All request bodies pass through a 5-detector middleware pipeline (secrets, PII, prompt injection, Unicode normalization, content classification) before reaching route handlers |
| Path containment | Run log file access (`GET /api/runs/{filename}`) enforces directory boundary checks to prevent traversal attacks |
| Private IP blocking | Outbound HTTP requests initiated by workflow tools block RFC 1918 and loopback addresses |
| Tool safety defaults | All 11 built-in tool modules default to `DENY` for high-risk operations; workflows must explicitly allowlist operations (e.g., `shell`, `git`, `file_delete`) per step in the YAML definition |
| Timing-safe key comparison | API key validation uses `secrets.compare_digest()` to mitigate timing-based key enumeration |
