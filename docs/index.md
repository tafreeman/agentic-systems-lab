# Project Documentation Index

> **Generated:** 2026-04-16 | **Last Updated:** 2026-04-22 | **Scan Mode:** initial_scan (exhaustive) | **Workflow Version:** 1.2.0 | **Deep-Dives:** 3

---

## Project Overview

- **Repository:** tafreeman/agentic-systems-lab
- **Type:** Monorepo (uv workspace) with 4 parts
- **Primary Language:** Python 3.11+ / TypeScript 5.7
- **Architecture:** Dual execution engine (native DAG + LangGraph), protocol-based, FastAPI + React 19

### Quick Reference by Part

#### Runtime — `agentic-workflows-v2/` (backend)

- **Tech Stack:** Python 3.11, FastAPI, Pydantic v2, Typer CLI, httpx/aiohttp
- **Engines:** Native DAG (Kahn's algorithm) + LangGraph state machines
- **Providers:** 8+ LLM providers (OpenAI, Anthropic, Gemini, Azure, GitHub Models, Ollama, local ONNX, Windows AI)
- **Root:** `agentic-workflows-v2/`

#### UI — `agentic-workflows-v2/ui/` (web)

- **Tech Stack:** React 19, Vite 6, TypeScript 5.7, TanStack Query 5, @xyflow/react 12, Tailwind CSS 3.4
- **Root:** `agentic-workflows-v2/ui/`

#### Eval — `agentic-v2-eval/` (library)

- **Tech Stack:** Python 3.11, PyYAML, 8 rubrics, 4 evaluator types, batch/streaming runners
- **Root:** `agentic-v2-eval/`

#### Tools — `tools/` (library, package: agentic-systems-lab-tools)

- **Tech Stack:** Python 3.11, OpenAI/Anthropic SDKs, Pydantic, NumPy, aiohttp
- **Role:** Shared LLM client (10 providers), benchmarks, caching, error taxonomy
- **Root:** `tools/` (workspace root)

---

## Generated Documentation

### Project-Wide

- [Architecture (Umbrella)](./ARCHITECTURE.md) — System map linking all per-package deep dives + the five load-bearing mechanisms
- [Roadmap](./ROADMAP.md) — Shipped epics, Epic 4 tombstone, Sprint B, proposed Epic 7+
- [Known Limitations](./KNOWN_LIMITATIONS.md) — Honest accounting of items shipped with caveats
- [Migrations](./MIGRATIONS.md) — Breaking changes since v0.3.0 (starts with `presentation/` extraction)
- [Onboarding Guide](./ONBOARDING.md) — Canonical 5-minute to 1-hour first-run path
- [Contribution Policy](../CONTRIBUTING.md) — Monorepo-wide contribution guide (at repo root)
- [Project Overview](./project-overview.md) — Purpose, tech stack summary, architecture type, links to all docs
- [Integration Architecture](./integration-architecture.md) — How the 4 parts communicate (REST, WebSocket, SSE, imports)
- [Development Guide](./development-guide.md) — Prerequisites, installation, dev servers, testing, CLI, common issues
- [Deployment Guide](./deployment-guide.md) — CI/CD pipeline, security scanning, environment variables, production checklist

### Runtime (Backend)

- [Architecture — Runtime](./architecture-runtime.md) — Dual-engine architecture, server layers, agents, models, RAG, security
- [API Contracts — Runtime](./api-contracts-runtime.md) — 16 REST endpoints + WebSocket + SSE, auth model, request/response schemas
- [Data Models — Runtime](./data-models-runtime.md) — 38+ Pydantic v2 models across server, contracts, core (messages, schemas, sanitization, verification, memory, errors)

### UI (Frontend)

- [Architecture — UI](./architecture-ui.md) — React 19 SPA, TanStack Query, routing, design system, WebSocket streaming
- [Component Inventory — UI](./component-inventory-ui.md) — 17 components across 6 categories (layout, common, DAG, runs, live, pages)

### Evaluation Framework

- [Architecture — Eval](./architecture-eval.md) — Rubric-driven evaluation, 4 evaluator types, scoring engine, runners, reporters, sandbox

### Shared Tools

- [Architecture — Tools](./architecture-tools.md) — Multi-provider LLM client, response caching, model probing, benchmarks, error taxonomy

---

## Deep-Dive Documentation

Exhaustive full-file analysis of specific areas:

- [Server Deep-Dive](./deep-dive-server.md) — Comprehensive analysis of `agentic-workflows-v2/agentic_v2/server/` (23 files, 6,589 LOC) — Generated 2026-04-17
- [Agents Deep-Dive](./deep-dive-agents.md) — Comprehensive analysis of `agentic-workflows-v2/agentic_v2/agents/` (15 files, 4,337 LOC) — Generated 2026-04-17
- [agentic-v2-eval Deep-Dive](./deep-dive-agentic-v2-eval.md) — Comprehensive analysis of the evaluation framework (`agentic-v2-eval/`, 60 files incl. tests + rubrics) — Generated 2026-04-18

---

## Existing Documentation

### Architecture Decision Records

- [ADR Index](./adr/ADR-INDEX.md) — Master index of all ADRs (start here)
- [ADR-001/002/003 — Architecture Decisions](./adr/ADR-001-002-003-architecture-decisions.md)
- [ADR-007 — Classification Matrix Stop Policy](./adr/ADR-007-classification-matrix-stop-policy.md)
- [ADR-008 — Testing Approach Overhaul](./adr/ADR-008-testing-approach-overhaul.md)
- [ADR-009 — Scoring Enhancements](./adr/ADR-009-scoring-enhancements.md)
- [ADR-010 — Eval Harness Methodology](./adr/ADR-010-eval-harness-methodology.md)
- [ADR-011 — Eval Harness API Interface](./adr/ADR-011-eval-harness-api-interface.md)
- [ADR-012 — UI Evaluation Hub](./adr/ADR-012-ui-evaluation-hub.md)
- [RAG Pipeline Blueprint](./adr/RAG-pipeline-blueprint.md)

### Reference Documents

- [Coding Standards](./CODING_STANDARDS.md) — Detailed coding standards reference
- [Workflow Authoring](./WORKFLOW_AUTHORING.md) — YAML workflow definition guide
- [Pattern Catalog](./PATTERN_CATALOG.md) — Agentic pattern reference
- [Glossary](./GLOSSARY.md) — Term definitions
- [Onboarding](./ONBOARDING.md) — Team onboarding guide

---

## Getting Started

### For New Developers

1. Read the [Project Overview](./project-overview.md) to understand the system
2. Follow the [Development Guide](./development-guide.md) to set up your environment
3. Review the root [`CONTRIBUTING.md`](../CONTRIBUTING.md) for code standards and workflow
4. Explore the [Project Overview](./project-overview.md) to understand the codebase layout

### For Feature Work

- **Backend features:** Start with [Architecture — Runtime](./architecture-runtime.md) + [API Contracts](./api-contracts-runtime.md)
- **UI features:** Start with [Architecture — UI](./architecture-ui.md) + [Component Inventory](./component-inventory-ui.md)
- **Full-stack features:** Add [Integration Architecture](./integration-architecture.md)
- **Evaluation work:** Start with [Architecture — Eval](./architecture-eval.md)
- **Shared utilities:** Start with [Architecture — Tools](./architecture-tools.md)

### For Brownfield PRD

When ready to plan new features, run the BMad PRD workflow (`bmad-create-prd`) and provide this index as input context.
