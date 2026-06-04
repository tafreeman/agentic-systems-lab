# Runtime Architecture — `agentic-workflows-v2`

**Package:** `agentic-workflows-v2` | **Python:** 3.11+ | **Build:** hatchling

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Technology Stack](#technology-stack)
3. [High-Level Structure](#high-level-structure)
4. [Architectural Layers](#architectural-layers)
   - [Server Layer](#server-layer)
   - [Agents Layer](#agents-layer)
   - [Engine Layer](#engine-layer)
   - [Models Layer](#models-layer)
   - [Tools Layer](#tools-layer)
   - [RAG Pipeline](#rag-pipeline)
   - [Core Protocols](#core-protocols)
5. [Async Architecture](#async-architecture)
6. [Security Architecture](#security-architecture)
7. [Configuration System](#configuration-system)
8. [CLI](#cli)
9. [Source Map](#source-map)
10. [Key Design Decisions](#key-design-decisions)

---

## Executive Summary

The `agentic-workflows-v2` package is a production-grade multi-agent workflow runtime built for enterprise environments. It provides:

- **Native DAG executor** as the single strategic engine (Kahn's topological sort algorithm, [ADR-013](adr/ADR-013-foundation-native-dag.md)). A LangGraph state-machine adapter remains for backward compatibility behind the same adapter interface, but is deprecated, emits a `DeprecationWarning` on import, and is targeted for removal in v2.0 (2026-Q3).
- **8+ LLM provider support** with tier-based smart routing, circuit breakers, and fallback chains.
- **FastAPI server** with full WebSocket and SSE streaming, a 500-event replay buffer, and a React 19 dashboard.
- **Full RAG pipeline** including recursive chunking, content-hash deduplication, cosine similarity vector search, BM25 keyword indexing, RRF hybrid fusion, and token-budget assembly.
- **OpenTelemetry tracing** integrated throughout the execution pipeline.
- **3-layer security middleware** with a 5-detector input sanitization pipeline.
- **11 built-in tool modules** with DENY-by-default safety and per-step allowlisting.

The system serves dual purpose: an operational agentic AI platform and a reference implementation for production workflow operations.

---

## Technology Stack

| Category | Technology | Notes |
|----------|-----------|-------|
| Runtime | Python 3.11+ | Async-first via `asyncio` |
| Web framework | FastAPI | ASGI, async route handlers |
| Data validation | Pydantic v2 | All models use `model_dump()` / `model_validate()` |
| CLI | Typer | 7 commands |
| HTTP client | httpx / aiohttp | Async outbound requests from tools |
| Templating | Jinja2 | Prompt template rendering |
| LLM orchestration | LangChain / LangGraph | Optional; guarded by `try/except ImportError` |
| Tracing | OpenTelemetry | OTEL SDK; exporter configurable |
| Vector store | LanceDB | RAG persistent index |
| LLM routing | LiteLLM | Unified provider interface for 8+ backends |
| Frontend | React 19 + Vite 6 | Served from `ui/dist/` |
| Graph UI | @xyflow/react 12 | DAG visualization canvas |
| Data fetching | TanStack Query | Frontend cache and server state |
| Styling | Tailwind CSS | Utility-first |
| Pre-commit | black, isort, ruff, mypy, detect-secrets | Enforced on every commit |

---

## High-Level Structure

```
agentic-workflows-v2/
├── agentic_v2/
│   ├── server/              # FastAPI application, routes, auth, streaming
│   ├── agents/              # BaseAgent + 4 specialized agents + implementations/
│   ├── adapters/            # AdapterRegistry, ExecutionEngine backends
│   ├── core/                # Protocols, memory, context, contracts, errors
│   ├── engine/              # Native DAG executor (Kahn's algorithm)
│   ├── langchain/           # LangGraph execution engine (optional)
│   ├── models/              # LLM tier routing, provider backends, smart router
│   ├── rag/                 # Full RAG pipeline
│   ├── contracts/           # Pydantic I/O models (additive-only)
│   ├── prompts/             # 7 agent persona definitions (.md)
│   ├── tools/builtin/       # 11 built-in tool modules
│   ├── workflows/definitions/ # 6 YAML workflow definitions
│   ├── integrations/        # OpenTelemetry integration
│   └── middleware/          # Sanitization detectors
├── tests/                   # 100+ test files, pytest-asyncio auto mode
└── ui/                      # React 19 frontend
```

---

## Architectural Layers

### Server Layer

**Source:** `agentic_v2/server/`

The server layer is a FastAPI ASGI application. It owns the HTTP interface, authentication, streaming infrastructure, and background task dispatch.

#### Middleware Stack

Middleware is applied in the following order (outermost to innermost):

1. **CORS middleware** — Configures allowed origins, methods, and headers. Defaults permissive for local development; locked down via `AGENTIC_CORS_ORIGINS` in production.
2. **API key middleware** — Validates `Authorization: Bearer` or `X-API-Key` headers using `secrets.compare_digest()`. Passes through configured public paths without authentication.
3. **Sanitization middleware** — Runs all inbound request bodies through the 5-detector sanitization pipeline. Requests classified `BLOCKED` are rejected with `400 Bad Request` before reaching any route handler.

#### Route Modules

| Module | Responsibility |
|--------|---------------|
| `server/routes/health.py` | `/api/health` liveness endpoint |
| `server/routes/agents.py` | Agent listing |
| `server/routes/workflows.py` | Workflow CRUD, DAG, capabilities, editor |
| `server/routes/runs.py` | Run dispatch, list, summary, log retrieval |
| `server/routes/stream.py` | SSE streaming for live run events |
| `server/routes/eval.py` | Evaluation dataset listing and dataset preview |
| `server/websocket.py` | WebSocket handler with 500-event replay buffer |
| `server/execution.py` | Background task coordination, event publication |
| `server/auth.py` | API key dependency, `secrets.compare_digest` |
| `server/models.py` | All server-layer Pydantic request/response models |

#### Execution Dispatch

`POST /api/run` uses FastAPI `BackgroundTasks` to dispatch workflow execution without blocking the HTTP response. The execution coroutine publishes events to an `asyncio.Queue` which is consumed by both the SSE stream handler and the WebSocket handler.

#### SPA Integration

When `ui/dist/index.html` is present, a catch-all route (`GET /{path:path}`) serves the compiled React application, enabling client-side routing without server configuration per route.

---

### Agents Layer

**Source:** `agentic_v2/agents/`

#### `BaseAgent`

All agents inherit from `BaseAgent`. It provides:

- LLM client lifecycle management
- Message history management (`list[AgentMessage]`)
- Tool execution dispatch
- Structured logging via `loguru`
- OpenTelemetry span creation
- Retry logic with configurable backoff

#### Specialized Agents

| Agent | Class | Role |
|-------|-------|------|
| Coder | `CoderAgent` | Code generation, refactoring, debugging |
| Reviewer | `ReviewerAgent` | Code review, quality analysis, finding generation |
| Orchestrator | `OrchestratorAgent` | Workflow coordination, sub-task delegation |
| Architect | `ArchitectAgent` | System design decisions, ADR generation |

#### Capability Mixins

Agents can compose optional capabilities via mixins:

| Mixin | Capability |
|-------|-----------|
| `SupportsRAGMixin` | Augments prompts with RAG-retrieved context |
| `SupportsVerificationMixin` | Enables output verification and self-correction cycles |
| `SupportsStreamingMixin` | Emits token-level streaming events |

#### Persona Definitions

Each agent has a corresponding Markdown persona file in `agentic_v2/prompts/`. Persona files define: Expertise, Boundaries, Critical rules, and Output format. These are loaded at agent instantiation and injected as system prompt context.

#### Agent Implementations

Extended or domain-specific agent implementations live in `agents/implementations/` and inherit from one of the four base specializations.

---

### Engine Layer

**Source:** `agentic_v2/engine/`, `agentic_v2/langchain/`, `agentic_v2/adapters/`

#### Adapter Pattern

The `AdapterRegistry` singleton maps string adapter names to `ExecutionEngine` protocol implementations. Workflow execution always goes through the registry:

```python
engine = AdapterRegistry.get("native")
result = await engine.execute(workflow_definition, inputs)
```

Adapters are registered at startup. The `langchain` adapter is registered only when `langchain` and `langgraph` are importable (guarded by `try/except ImportError`).

#### Native DAG Executor

**Source:** `agentic_v2/engine/`

The native executor implements topological step ordering via **Kahn's algorithm**:

1. Parse the YAML workflow definition into a DAG.
2. Detect cycles; raise `WorkflowError` if any are found.
3. Compute in-degree for each step node.
4. Maintain a ready queue of nodes with in-degree zero.
5. Execute ready steps (respecting `depends_on` constraints) concurrently using `asyncio.gather`.
6. Decrement in-degrees of dependent nodes as steps complete; enqueue newly unblocked steps.
7. Collect `StepResult` objects and assemble the final `WorkflowResult`.

This approach achieves maximum step-level parallelism while respecting explicit dependencies. It has no external dependencies beyond the Python standard library and Pydantic.

#### LangGraph Engine (deprecated)

**Source:** `agentic_v2/langchain/`
**Status:** Deprecated per [ADR-013](adr/ADR-013-foundation-native-dag.md). Importing this module emits a `DeprecationWarning`; removal target is v2.0 (2026-Q3).

The LangGraph adapter wraps workflow definitions as LangGraph `StateGraph` state machines. Each step becomes a graph node; `depends_on` relationships become graph edges. Historically this engine was used when LangChain-specific features were required (built-in memory, tool-calling with LangChain tool wrappers, LangSmith tracing); new workflows should use the native engine.

The LangGraph adapter satisfies the same `ExecutionEngine` protocol as the native adapter, so the rest of the system is engine-agnostic for the remainder of the deprecation window.

---

### Models Layer

**Source:** `agentic_v2/models/`

#### Smart Router

`smart_router.py` is the central dispatch point for all LLM calls. It selects the appropriate provider and model based on a **tier** system:

| Tier | Intended Use | Example Models |
|------|-------------|----------------|
| `fast` | High-throughput, latency-sensitive tasks | GPT-4o-mini, Claude Haiku, Gemini Flash |
| `standard` | General-purpose agent tasks | GPT-4o, Claude Sonnet, Gemini Pro |
| `powerful` | Complex reasoning, architecture decisions | o3, Claude Opus, Gemini Ultra |

#### Provider Backends

8+ provider backends are supported:

| Provider | Config Key | Notes |
|----------|-----------|-------|
| OpenAI | `OPENAI_API_KEY` | Direct API |
| Anthropic | `ANTHROPIC_API_KEY` | Direct API |
| Google Gemini | `GEMINI_API_KEY` | Direct API |
| Azure OpenAI | `AZURE_OPENAI_API_KEY_0..n` | Supports `_0` through `_n` suffix for multiple deployments and failover |
| Azure AI Foundry | `AZURE_FOUNDRY_*` | Foundry model catalog |
| GitHub Models | `GITHUB_TOKEN` | Models API |
| Ollama | `OLLAMA_BASE_URL` | Local inference |
| Local ONNX | `LOCAL_MODEL_PATH` | Auto-detected from `~/.cache/aigallery` |

#### Circuit Breaker and Fallback

The smart router implements:

- **Circuit breaker:** Each provider backend tracks consecutive failure counts. Backends that exceed the threshold are marked unavailable for a configurable cool-down window.
- **Fallback chains:** Each tier has an ordered fallback chain. If the primary provider is unavailable or returns an error, the router automatically retries with the next provider in the chain.
- **Retry with backoff:** Individual LLM calls retry on transient errors (rate limits, timeouts) with exponential backoff before the circuit breaker engages.

---

### Tools Layer

**Source:** `agentic_v2/tools/builtin/`

#### Safety Model

The tools layer enforces a **DENY-by-default** safety policy. Every tool operation has an associated risk classification:

| Risk Level | Examples | Default Policy |
|------------|---------|----------------|
| Low | `file_read`, `web_search` | ALLOW |
| Medium | `file_write`, `http_request` | ALLOW with path/URL constraints |
| High | `shell`, `git`, `file_delete`, `code_exec` | DENY unless explicitly allowlisted |

Workflow YAML definitions must explicitly allowlist high-risk operations per step. An agent cannot perform a high-risk operation unless the step's `tools` block includes the relevant permission.

#### Built-in Tool Modules (11 total)

| Module | Description |
|--------|-------------|
| `file_read` | Read files from the filesystem; path containment enforced |
| `file_write` | Write files; path containment enforced; DENY by default for paths outside working dir |
| `file_delete` | Delete files; DENY by default |
| `shell` | Execute shell commands; DENY by default; allowlist per command |
| `web_search` | Web search via configured search API |
| `http_request` | Outbound HTTP; blocks private IP ranges; timeout enforced |
| `git` | Git operations (status, diff, log, commit); DENY for writes by default |
| `code_exec` | Execute code in sandbox; DENY by default |
| `rag_search` | Query the RAG index |
| `memory_read` | Read from the active memory store |
| `memory_write` | Write to the active memory store |

---

### RAG Pipeline

**Source:** `agentic_v2/rag/`

The RAG pipeline provides document ingestion, indexing, and retrieval for context augmentation. It is used directly by the `RAGMemoryStore` and the `SupportsRAGMixin`.

#### Pipeline Stages

```
Document Loading
      ↓
Recursive Chunking
      ↓
Content-Hash Deduplication
      ↓
Embedding (with hash-based cache)
      ↓
    ┌─────────────────────────────┐
    │  LanceDB Vector Index       │   ← cosine similarity
    │  BM25 Keyword Index         │   ← lexical matching
    └─────────────────────────────┘
      ↓
  Hybrid Retrieval (RRF fusion)
      ↓
  Token-Budget Assembly
      ↓
  OTEL Trace Spans
```

#### Stage Descriptions

| Stage | Detail |
|-------|--------|
| **Document Loading** | Supports plain text, Markdown, PDF (via `pdfplumber`), and HTML inputs |
| **Recursive Chunking** | Splits documents by semantic boundaries (headings, paragraphs, sentences) before falling back to token-count limits |
| **Content-Hash Deduplication** | Each chunk is hashed (SHA-256 of normalised content). Duplicate chunks are skipped during embedding, preventing redundant index entries |
| **Embedding** | Embedding vectors are computed lazily and cached by content hash, avoiding re-embedding unchanged content across ingestion runs |
| **LanceDB Vector Index** | Persistent on-disk vector store. Cosine similarity search returns top-K candidates |
| **BM25 Keyword Index** | In-memory BM25 index over chunk text. Captures exact-match and term-frequency signals not captured by dense vectors |
| **Hybrid Retrieval (RRF)** | Reciprocal Rank Fusion merges vector and keyword result lists. Balances semantic and lexical relevance |
| **Token-Budget Assembly** | Assembles the final context string by greedily appending the highest-ranked chunks until a configured token budget is reached |
| **OTEL Tracing** | Each pipeline stage emits OpenTelemetry spans, enabling distributed trace visualisation of retrieval quality |

---

### Core Protocols

**Source:** `agentic_v2/core/protocols.py`

All core abstractions are defined as Python `Protocol` classes decorated with `@runtime_checkable`. This enables `isinstance()` checks without requiring inheritance, keeping implementations loosely coupled.

| Protocol | Description |
|----------|-------------|
| `ExecutionEngine` | Interface for workflow execution engines; `execute(definition, inputs) -> WorkflowResult` |
| `AgentProtocol` | Interface for all agents; `run(task_input) -> TaskOutput` |
| `ToolProtocol` | Interface for tool modules; `invoke(operation, params) -> Any` |
| `MemoryStore` | Async key-value + search interface (see [Memory Abstractions](data-models-runtime.md#memory-abstractions)) |
| `SupportsStreaming` | Marks components that emit streaming events; `stream() -> AsyncIterator[AgentMessage]` |
| `SupportsCheckpointing` | Marks components that can save and restore state; `checkpoint() -> bytes`, `restore(data: bytes) -> None` |

All six protocols are `@runtime_checkable`.

---

## Async Architecture

The runtime is async-first. The following design decisions govern concurrency:

### Background Task Dispatch

`POST /api/run` dispatches execution via FastAPI `BackgroundTasks`. The HTTP response returns immediately (`202 Accepted`) with the `run_id`. Execution runs in the same event loop as the server but does not block the response thread.

### Event Publication via asyncio.Queue

Each active run owns an `asyncio.Queue[dict]`. The execution coroutine `put()`s event dictionaries into the queue as execution proceeds. The SSE stream handler and WebSocket handler both consume from this queue via `asyncio.Queue.get()`. This is a pure in-process pub/sub mechanism with no external broker dependency.

### SSE Streaming

The SSE endpoint uses an `async generator` that yields `text/event-stream` formatted strings from the run's event queue. FastAPI's streaming response support delivers these chunks via HTTP chunked transfer encoding.

### WebSocket with Replay Buffer

The WebSocket handler maintains a per-run circular buffer (`collections.deque(maxlen=500)`) of serialised event dictionaries. On new WebSocket connections, all buffered events are replayed in order before live events begin. This allows late-joining clients to recover full run history up to the buffer limit.

### Native DAG Concurrency

Within the native engine, steps with no unresolved dependencies are executed concurrently using `asyncio.gather`. This maximises throughput in workflows with parallel branches while respecting the dependency graph.

### No External Broker

There is no Redis, Kafka, or any external message broker. All event state is in-process. This simplifies deployment but means events are lost on server restart. Durable history is available via the persisted JSON run-log files.

---

## Security Architecture

Security controls are layered across three tiers:

### Tier 1: Transport and Authentication

- **HTTPS** is enforced by the deployment infrastructure (reverse proxy / load balancer). The application layer does not terminate TLS directly.
- **API key authentication** via `secrets.compare_digest()` prevents timing-based key enumeration.
- **CORS** is configurable via `AGENTIC_CORS_ORIGINS`. Defaults to permissive for local development; must be locked down for production.

### Tier 2: Input Sanitization Middleware

All inbound request bodies pass through a 5-detector pipeline before reaching route handlers:

| Detector | What It Catches |
|----------|----------------|
| Secret detector | API keys, tokens, private keys, connection strings |
| PII detector | Email addresses, phone numbers, national identifiers |
| Prompt injection detector | Instruction-override patterns (e.g., "ignore previous instructions") |
| Unicode anomaly detector | Zero-width characters, directional overrides, BOM markers |
| Classification engine | Assigns `CLEAN`, `REDACTED`, `BLOCKED`, or `REQUIRES_APPROVAL` |

Requests classified `BLOCKED` (e.g., containing private key material) are rejected with `400 Bad Request` before any business logic executes. Requests classified `REDACTED` proceed with sensitive values replaced by `[REDACTED]` markers.

### Tier 3: Runtime Safety Controls

| Control | Mechanism |
|---------|-----------|
| Path containment | File-access tools validate that resolved paths remain within the configured working directory before any I/O |
| Private IP blocking | Outbound HTTP tool requests check destination against RFC 1918 ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16) and loopback (127.0.0.0/8) and block matches |
| Tool safety defaults | All 11 built-in tool modules default to DENY for high-risk operations; per-step YAML allowlisting required |
| Secret provider abstraction | The `SecretProvider` abstraction centralises secret access; secrets are never passed directly in model configs or log output |

---

## Configuration System

**Source:** `agentic_v2/core/context.py`, environment variables

### Environment Variables

Approximately 25 environment variables govern runtime behaviour. Key variables:

| Variable | Description |
|----------|-------------|
| `AGENTIC_API_KEY` | Server API key; unset enables open mode |
| `AGENTIC_FILE_BASE_DIR` | Base directory for file tool path containment; path-traversal safety anchor |
| `AGENTIC_CORS_ORIGINS` | Comma-separated list of allowed CORS origins |
| `AGENTIC_DEFAULT_ADAPTER` | Default execution engine (`native` or `langchain`) |
| `AGENTIC_LOG_LEVEL` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic Claude API key |
| `GEMINI_API_KEY` | Google Gemini API key |
| `AZURE_OPENAI_API_KEY_0..n` | Azure OpenAI keys (supports `_0` through `_n` suffix) |
| `AZURE_OPENAI_ENDPOINT_0..n` | Azure OpenAI endpoints (matching `_0` through `_n` index) |
| `GITHUB_TOKEN` | GitHub Models API token |
| `OLLAMA_BASE_URL` | Ollama local inference base URL |
| `LOCAL_MODEL_PATH` | Local ONNX model path; auto-detected from `~/.cache/aigallery` when unset |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OpenTelemetry collector endpoint |

See `.env.example` for the full variable list with documentation.

### YAML-Based Configuration

Model routing, agent parameters, and workflow definitions are configured in YAML:

| Config Type | Location | Description |
|------------|----------|-------------|
| Workflow definitions | `workflows/definitions/*.yaml` | 6 built-in workflow definitions |
| Agent configs | Runtime-loaded | Agent names, tiers, tool allowlists |
| Model tier config | `models/tiers.yaml` | Provider priority order per tier |

### SecretProvider Abstraction

A `SecretProvider` class centralises access to secrets at runtime, preventing direct `os.environ` access scattered through the codebase. It supports:

- Environment variable backend (default)
- File-based backend (for mounted secrets in containerised environments)
- Custom backend (implement the protocol)

---

## CLI

**Source:** `agentic_v2/cli/`

The CLI is implemented with **Typer** and provides 7 top-level commands:

| Command | Description |
|---------|-------------|
| `agentic run <workflow> --input <file.json>` | Execute a workflow with inputs from a JSON file |
| `agentic compare <workflow> --input <file>` | Run the same workflow on both engines and compare outputs |
| `agentic list workflows\|agents\|tools` | List available workflows, agents, or tools |
| `agentic validate <workflow>` | Validate a workflow YAML without executing it |
| `agentic serve` | Start the FastAPI development server |
| `agentic version` | Print version information |
| `agentic rag ingest --source <path>` | Ingest documents into the RAG index |
| `agentic rag search <query>` | Run a search query against the RAG index |

The `compare` command is useful for verifying that the native and LangGraph engines produce equivalent outputs for a given workflow, which is important when migrating workflows between engines.

---

## Source Map

| Path | Contents |
|------|---------|
| `agentic_v2/server/` | FastAPI app factory, route modules, auth, execution coordinator, WebSocket handler, SSE streaming, server-layer models |
| `agentic_v2/contracts/` | Pydantic contracts: messages, schemas, sanitization, verification (additive-only policy) |
| `agentic_v2/core/` | Protocols, memory implementations, context, errors, secret provider |
| `agentic_v2/engine/` | Native DAG executor (Kahn's algorithm), step scheduler, result collector |
| `agentic_v2/langchain/` | LangGraph execution engine, state graph builder, LangChain tool wrappers |
| `agentic_v2/adapters/` | AdapterRegistry singleton, ExecutionEngine adapter base class |
| `agentic_v2/models/` | SmartRouter, provider backends, tier config, circuit breaker, LiteLLM integration |
| `agentic_v2/agents/` | BaseAgent, CoderAgent, ReviewerAgent, OrchestratorAgent, ArchitectAgent, capability mixins, implementations/ |
| `agentic_v2/tools/builtin/` | 11 built-in tool modules: file_read, file_write, file_delete, shell, web_search, http_request, git, code_exec, rag_search, memory_read, memory_write |
| `agentic_v2/rag/` | Document loader, chunker, embedder, LanceDB vector store, BM25 index, hybrid retriever, RRF fusion, token-budget assembler, OTEL spans |
| `agentic_v2/prompts/` | 7 agent persona Markdown files |
| `agentic_v2/workflows/definitions/` | 6 YAML workflow definitions |
| `agentic_v2/integrations/` | OpenTelemetry integration, tracer provider setup, span helpers |
| `agentic_v2/middleware/` | Sanitization detector implementations (secret, PII, prompt injection, Unicode, classifier) |
| `agentic_v2/cli/` | Typer CLI entry points |
| `tests/` | 100+ test files; pytest-asyncio auto mode; markers: integration, slow, security |
| `ui/` | React 19 frontend; @xyflow/react DAG canvas; TanStack Query; Tailwind CSS; Vitest |

---

## Key Design Decisions

### Execution Engine (post-ADR-013)

The system runs behind a shared `ExecutionEngine` protocol. The **native** engine has no optional dependencies and is the **strategic default** under [ADR-013](adr/ADR-013-foundation-native-dag.md). The **LangGraph** engine remains opt-in for backward compatibility during the deprecation window and is the current CLI default purely to avoid breaking existing scripts; it emits a `DeprecationWarning` on import and is targeted for removal in v2.0 (2026-Q3). The `agentic compare` command lets teams migrate workflows incrementally and verify equivalence between engines before cutting over.

### Additive-Only Contracts

All Pydantic models in `contracts/` follow an additive-only policy. Fields are never removed or renamed in ways that break existing serialised data (JSON run logs) or running clients. New fields are added as `Optional` with defaults. This policy protects filesystem-persisted run logs from becoming unreadable after upgrades.

### DENY-by-Default Tool Safety

High-risk tool operations are denied unless explicitly enabled per workflow step. This prevents accidental privilege escalation when new tools are added and ensures that security review of a workflow can be done by reading the YAML allowlist rather than auditing all agent code.

### No External Message Broker

The event streaming system uses in-process `asyncio.Queue` with a 500-event circular buffer. This eliminates infrastructure dependencies (Redis, RabbitMQ) for the core streaming path, simplifying deployment and reducing operational surface. The trade-off is that events are not durable across server restarts; this is acceptable because all run results are persisted to JSON log files.

### Filesystem Persistence

There is no database or ORM. All run results are serialised as JSON files. This keeps the deployment footprint minimal (no database server required) and makes run logs directly inspectable with standard tools. The trade-off is that querying run history at scale requires reading multiple files; the `GET /api/runs` endpoint applies in-memory filtering.

### Protocol-Driven Architecture

All major system interfaces are defined as `@runtime_checkable` Protocol classes. This decouples implementations from the interface definitions, enabling testing with pure mock implementations and preventing tight coupling between layers. It also allows third-party adapters, tools, and memory stores to be registered without modifying core code.

---

## Architectural Critique & Known Gaps

Merged from the 2026-03-03 architecture review. Captures weaknesses and recommendations that complement the strengths above.

### Protocol Type-Safety Weaknesses

- `ExecutionEngine.execute()` uses `Any` for `workflow`, `ctx`, and return type — loses compile-time type safety and pushes validation to runtime.
- `AgentProtocol.run()` uses `Any` for both input and output. `BaseAgent` is generic over `TInput`/`TOutput`, but the protocol itself does not enforce it.
- No protocol exists for `WorkflowLoader` or config validation — these remain concrete classes.

### Adapter Gaps

- **Context bridging missing.** `LangChainEngine` accepts `ctx: Any` but does not forward the `ExecutionContext` to the underlying `WorkflowRunner`. Shared state (variables, services, step tracking) from the native context system is not available in LangGraph executions. `ctx` is currently reserved for "future use."
- **Instance caching.** `AdapterRegistry` caches adapter instances. Configuration changes after first access require a registry reset — production-safe but forces `object.__new__()` workarounds in tests.

### Workflow DSL Limits

- `deep_research.yaml` is 619 lines with four near-identical rounds. YAML anchors help, but the round-based structure does not support dynamic round counts; adding more rounds requires duplication.
- `server/routes/workflows.py` is ~1,200 lines — the largest single file. Evaluation, dataset, and run-history concerns should be extracted as verticals grow.

### Code-Quality Configuration Drift

- `agentic-workflows-v2/pyproject.toml` now carries an explicit `[tool.ruff.lint]` rule set for E, F, W, I, N, UP, S, B, A, C4, SIM, TCH, and RUF. Some ignores remain as a documented Sprint C ratchet, but the public configuration now matches the repo standard instead of relying on private assistant config.

### Production Readiness Gaps

- All vector store / memory implementations are in-memory. Production needs a persistent `VectorStoreProtocol` implementation (LanceDB optional dep exists but no adapter).
- No cross-package integration tests exercising `tools/` → `agentic-workflows-v2` → `agentic-v2-eval` end-to-end.
- No adapter/tool plugin discovery — registration is import-time only (no `entry_points` or directory scan).
- RAG prompt-injection hardening (system-prompt-level delimiter framing for retrieved documents) is noted as architectural gap.

### Prioritized Recommendations

| # | Recommendation | Impact | Effort | Priority |
|---|---|:---:|:---:|:---:|
| 1 | Tighten protocol signatures — replace `Any` in `ExecutionEngine.execute()` / `AgentProtocol.run()` with bounded TypeVars or Union types | 4 | M | High |
| 2 | Bridge `ExecutionContext` into `LangChainEngine` so both engines share state during adapter-routed execution | 4 | M | High |
| 3 | Add cross-package integration tests covering the LLM client → engine → eval scoring path | 4 | M | High |
| 4 | Add RAG prompt-injection hardening (delimiter framing in system prompts for retrieved docs) | 4 | M | High |
| 5 | Add persistent `VectorStoreProtocol` adapter (LanceDB) to bridge dev and production | 4 | M | Medium |
| 6 | Extract `deep_research` round template into a loader-level loop construct — ~619 lines → ~200 | 3 | M | Medium |
| 7 | Split `server/routes/workflows.py` into evaluation, dataset, and run-history route modules | 3 | S | Medium |
| 8 | Add a standalone `quickstart.py` / CLI command running a simple workflow end-to-end | 3 | S | Medium |
| 9 | Document "How to implement ExecutionEngine / VectorStoreProtocol" with test templates | 3 | S | Medium |
| 10 | Add adapter/tool plugin discovery via `entry_points` or directory scan | 3 | M | Low |
