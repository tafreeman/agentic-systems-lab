# Project Overview — `tafreeman/agentic-systems-lab`

---

## Project Identity

| Field | Value |
|---|---|
| Repository | `tafreeman/agentic-systems-lab` |
| Primary branch | `main` |
| Python version | 3.11+ |
| Node version | 20+ |
| Build system | hatchling (all Python packages), Vite 6 (frontend) |
| Workspace manager | uv (workspace with three Python members) |
| License | See `LICENSE` in repository root |

---

## Executive Summary

The `agentic-systems-lab` monorepo is a multi-agent AI workflow platform built for enterprise-grade use in production-grade environments. At its core, the system provides a runtime engine for defining, executing, and observing multi-step AI workflows in which each step is handled by a specialized agent (Coder, Reviewer, Architect, Orchestrator, and others). Workflows are described as directed acyclic graphs in YAML and can be executed through either a native Python DAG executor or a LangGraph-backed engine, depending on the deployment requirements. The server exposes a FastAPI backend with real-time WebSocket streaming so that a React dashboard can display live execution progress, step outputs, and run history.

The monorepo serves a deliberate dual purpose: it is both a working production platform and an reference implementation for onboarding software engineers at engineering teams. Every architectural decision — dual execution engines, protocol-based abstractions, layered sanitization, rubric-driven evaluation — is documented and designed to demonstrate enterprise practices. The evaluation framework (`agentic-v2-eval`) and shared tools library (`agentic-systems-lab-tools`) are independently installable packages, enabling teams to adopt the LLM client, benchmarking utilities, or evaluation pipeline independently of the full runtime.

Security and observability are first-class concerns throughout. A sanitization middleware pipeline protects all inbound prompt content from secret leakage, PII exposure, and prompt injection. An optional OpenTelemetry integration instruments the full execution pipeline — from HTTP request through agent steps, LLM calls, and RAG retrieval — for distributed tracing. CI enforces 80% test coverage on the runtime, 80% on the eval package, and 70% on shared tools, with bandit and pip-audit running in every pull request.

---

## Tech Stack

| Package | Key Technologies |
|---|---|
| **Runtime** (`agentic-workflows-v2/`) | Python 3.11+, FastAPI, uvicorn, Pydantic v2, LangGraph (optional), hatchling, OpenTelemetry, PyYAML |
| **UI** (`agentic-workflows-v2/ui/`) | React 19, TypeScript, Vite 6, TanStack Query, @xyflow/react 12, Tailwind CSS, Vitest |
| **Eval** (`agentic-v2-eval/`) | Python 3.11+, Pydantic v2, PyYAML, hatchling, pytest-asyncio |
| **Tools** (`tools/` / `agentic-systems-lab-tools`) | Python 3.11+, aiohttp, openai SDK, anthropic SDK, numpy, hatchling |

### Cross-Cutting Concerns

| Concern | Technology |
|---|---|
| Dependency management | uv workspace + lockfile |
| Linting and formatting | ruff, black, isort |
| Type checking | mypy --strict |
| Secret scanning | detect-secrets (pre-commit) |
| Security scanning | bandit (SAST), pip-audit (dependency CVEs) |
| Distributed tracing | OpenTelemetry SDK + OTLP exporter |
| Documentation | Sphinx + MyST (optional CI build) |
| Containerization | Docker (backend + frontend separate images) |
| CI/CD | GitHub Actions (11 workflow files) |

---

## Architecture Overview

The monorepo is organized as a **uv workspace** with four packages occupying distinct architectural layers:

```
┌─────────────────────────────────────────────────────────┐
│                    React 19 Dashboard                    │
│         (agentic-workflows-v2/ui/)                       │
│    REST /api/*  |  WebSocket /ws/execution/{run_id}     │
└─────────────────────────┬───────────────────────────────┘
                          │ HTTP + WebSocket
┌─────────────────────────▼───────────────────────────────┐
│              FastAPI Runtime Server                      │
│         (agentic-workflows-v2/)                          │
│                                                          │
│  ┌────────────────┐   ┌─────────────────────────────┐   │
│  │ Native DAG     │   │ LangGraph Engine             │   │
│  │ Executor       │   │ (optional extra)             │   │
│  │ (engine/)      │   │ (langchain/)                 │   │
│  └────────────────┘   └─────────────────────────────┘   │
│                                                          │
│  RAG Pipeline │ Middleware (sanitize) │ Models (routing) │
└──────────────────────────┬──────────────────────────────┘
                           │ imports
┌──────────────────────────▼──────────────────────────────┐
│              Shared Tools (agentic-systems-lab-tools)                │
│         (tools/)                                         │
│   LLMClient (10 providers) │ Benchmarks │ Cache │ Errors │
└──────────────────────────┬──────────────────────────────┘
                           │ lazy imports
┌──────────────────────────▼──────────────────────────────┐
│              Evaluation Framework                        │
│         (agentic-v2-eval/)                               │
│   Rubrics │ Evaluators │ Runners │ Reporters │ Metrics  │
└─────────────────────────────────────────────────────────┘
```

### Architectural Characteristics

**Dual execution engine.** Every workflow YAML definition can execute through either the native DAG engine (`engine/`) or the LangGraph engine (`langchain/`). The `agentic compare` CLI command runs both engines on the same input and diffs their outputs. The `AdapterRegistry` in `adapters/registry.py` maps names (`"native"`, `"langchain"`) to `ExecutionEngine` protocol implementations.

**Protocol-based abstraction.** `core/protocols.py` defines all inter-component contracts as `@runtime_checkable` protocols. Concrete implementations are registered at startup, not hard-coded. This makes the system testable with minimal mocking and allows new engine backends or agent types to be added without modifying the core.

**Layered LLM routing.** `ModelRouter` maps tiers (1/2/3) to model names from `config/defaults/models.yaml`. `SmartRouter` adds circuit breakers, per-provider bulkhead concurrency limits, latency-weighted selection, and tier-fallback degradation. Both are backed by the shared `tools.llm.LLMClient`.

**Additive-only contracts.** Pydantic v2 models in `contracts/` follow a strict additive-only policy: existing fields are never removed or renamed. This ensures backward compatibility for any consumer of saved run outputs or API responses.

---

## Repository Structure Diagram

```
prompts/
├── agentic-workflows-v2/   Runtime + UI
│   ├── agentic_v2/         Python source
│   ├── tests/              full test suite
│   └── ui/                 React 19 dashboard
├── agentic-v2-eval/        Standalone evaluation framework
│   └── src/agentic_v2_eval/
├── tools/                  Shared utilities (agentic-systems-lab-tools)
│   ├── llm/                Multi-provider LLM client
│   ├── agents/benchmarks/  8 benchmark definitions
│   └── core/               Shared errors, cache, config
├── docs/                   Generated project documentation

├── .github/workflows/      11 CI/CD workflow files
├── otel/                   OpenTelemetry collector config
├── tests/e2e/              Cross-package smoke tests
└── pyproject.toml          uv workspace root + agentic-systems-lab-tools
```

---

## Links to Related Documentation

| Document | Description |
|---|---|
| [Project Overview](project-overview.md) | Purpose, tech stack summary, architecture type, links to all docs |
| [Integration Architecture](integration-architecture.md) | Cross-package communication contracts, REST API endpoints, WebSocket protocol, data flow |
| [Development Guide](development-guide.md) | Local development setup, dev servers, testing, linting, CLI usage, common issues |
| [Deployment Guide](deployment-guide.md) | CI/CD pipeline, environment variable reference, Docker, production configuration |

### Additional Documentation in `docs/`

- `ARCHITECTURE.md` — Detailed system architecture decisions
- `CODING_STANDARDS.md` — Code style standards and enforcement
- `GLOSSARY.md` — Term definitions for the domain
- `ONBOARDING.md` — New contributor onboarding guide
- `WORKFLOW_AUTHORING.md` — Guide to writing YAML workflow definitions
- `docs/adr/` — Architecture Decision Records
