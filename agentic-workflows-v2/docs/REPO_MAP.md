# Repository Map

This is a practical map of the repository for maintainers and contributors.

## Top-Level

| Path | Notes |
| --- | --- |
| `agentic_v2/` | Core Python package |
| `ui/` | Frontend application |
| `backend/` | Minimal backend prototype scaffold |
| `docs/` | Documentation hub |
| `tests/` | Backend tests |
| `examples/` | Standalone examples |
| `scripts/` | Utility and automation scripts |
| `fixtures/` | Fixture artifacts for docs and tests |


## `agentic_v2/` Package

| Module area | Purpose |
| --- | --- |
| `agents/` | Agent classes, orchestration roles, implementations |
| `cli/` | `agentic` command-line interface |
| `config/` | Default model/agent/eval config |
| `contracts/` | Typed schemas and message contracts |
| `engine/` | DAG and step execution runtime |
| `evaluation/` | Normalization and scoring helpers |
| `integrations/` | External integration adapters (LangChain, tracing) |
| `langchain/` | LangChain/LangGraph workflow integration |
| `models/` | Model routing and backend adapters |
| `prompts/` | Role prompts used by higher-tier agents |
| `server/` | FastAPI app, routes, and streaming adapters |
| `tools/` | Tool registry + built-in tools |
| `workflows/` | YAML loader/runner and workflow definitions |

## Coverage Notes

This map is intentionally high-level. For file-level legacy/active status, use `reports/ACTIVE_VS_LEGACY_TOOLING_MAP.md`.
