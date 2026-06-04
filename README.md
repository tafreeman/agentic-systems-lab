<div align="center">

# Agentic Systems Lab

**Development sandbox, runnable examples, and research companion to [agentic-runtime-platform](https://github.com/tafreeman/agentic-runtime-platform).**

[![CI](https://github.com/tafreeman/agentic-systems-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/tafreeman/agentic-systems-lab/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Linting: ruff](https://img.shields.io/badge/linting-ruff-261230.svg)](https://github.com/astral-sh/ruff)
[![Type checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue.svg)](http://mypy-lang.org/)

</div>

> **Note:** The production runtime lives at [tafreeman/agentic-runtime-platform](https://github.com/tafreeman/agentic-runtime-platform).
> This repo is where new features are prototyped, security sprints are run, and example code is maintained before promotion upstream.

---

## What this repo is for

Three things that don't belong in the main repo but need a home:

**1. Runnable examples** — Six self-contained scripts covering every major API surface: pipeline building, RAG, custom agents, model routing, evaluation, and adapter switching. Each runs without API keys in no-LLM mode and is commented for onboarding use.

**2. Security and tooling sprints** — Hardening work (tool safety, sanitization, sandbox escapes, subprocess env isolation) is prototyped and fully tested here before being upstreamed. Sprint 1 (S1-01 through S1-07) was completed in this repo.

**3. Research library** — Curated source registry, approved domains, and reference material used to gate evaluation outputs (`coverage_score >= 0.80`, `source_quality_score >= 0.80`).

---

## Quick start — examples

```bash
# Install the runtime in dev mode (from agentic-workflows-v2/)
pip install -e ".[dev,server]"

# Install the eval package (from agentic-v2-eval/)
pip install -e ".[dev]"

# Run any example — no API keys needed
python examples/01_hello_workflow.py
python examples/02_rag_pipeline.py
python examples/03_custom_agent.py
python examples/04_model_routing.py
python examples/05_evaluation.py
python examples/06_adapter_switching.py
```

| Example | What it covers |
|---------|---------------|
| `01_hello_workflow.py` | `StepDefinition`, `PipelineBuilder`, `PipelineExecutor`, `ExecutionContext` |
| `02_rag_pipeline.py` | Full RAG: chunk, embed, store, hybrid retrieve (dense + BM25 + RRF), assemble |
| `03_custom_agent.py` | Subclass `BaseAgent`, typed I/O, event handlers, agent lifecycle |
| `04_model_routing.py` | `ModelRouter`, `FallbackChain` DSL, `SmartModelRouter` with circuit breakers |
| `05_evaluation.py` | `Scorer`, built-in rubrics, multi-run comparison |
| `06_adapter_switching.py` | `AdapterRegistry`, DAG vs pipeline execution semantics |

---

## Relationship to agentic-runtime-platform

```
agentic-runtime-platform (production)     agentic-systems-lab (this repo)
--------------------------------  --------------------------------
Reviewed, tagged releases         Active sprint work
Clean docs/ARCHITECTURE.md        Planning artifacts, retros
No generated output               Research library, run outputs
Pinned deps, CI green             Experimental dependency bumps
```

Changes flow one direction: prototype here, upstream when stable.

---

## Architecture

```mermaid
graph TD
    A["📄 YAML Workflow DSL<br/><i>deep_research · code_review · tdd_codegen</i>"] --> B["🔍 Workflow Loader & Validator<br/><i>Expression resolution · Input typing</i>"]

    B --> C["⚡ DAG Executor<br/><i>Native Runtime</i>"]
    B --> D["🔗 LangGraph Compiler<br/><i>LangChain Engine</i>"]

    C --> E["🔀 Tiered Model Router"]
    D --> E

    E --> F["☁️ Provider Backends"]

    subgraph DAG ["DAG Executor"]
        C
        C1["Kahn's algorithm scheduling"]
        C2["asyncio.wait FIRST_COMPLETED"]
        C3["Cascade failure propagation"]
        C4["Max concurrency control"]
    end

    subgraph LG ["LangGraph Compiler"]
        D
        D1["StateGraph node generation"]
        D2["Conditional + loop edges"]
        D3["Checkpointing support"]
    end

    subgraph Router ["Model Router"]
        E
        E1["Tier 0 → Deterministic · no LLM"]
        E2["Tier 1 → Small · flash-lite, 4o-mini"]
        E3["Tier 2 → Medium · flash, haiku"]
        E4["Tier 3 → Large · 2.5-flash, gpt-4o"]
        E5["Tier 4 → Premium · 2.5-pro, claude-sonnet"]
        E6["Tier 5 → Frontier · claude-opus"]
        E7["Health-weighted selection · Adaptive cooldowns<br/>Circuit breakers · Cost-aware routing"]
    end

    subgraph Providers ["Providers"]
        F
        F1["OpenAI"]
        F2["Anthropic"]
        F3["Google Gemini"]
        F4["Ollama / LM Studio"]
        F5["Azure OpenAI"]
        F6["GitHub Models"]
    end

    style A fill:#4a90d9,stroke:#2c5f8a,color:#fff
    style B fill:#6c5ce7,stroke:#4834a8,color:#fff
    style E fill:#e17055,stroke:#b34530,color:#fff
    style F fill:#00b894,stroke:#008060,color:#fff
    style C fill:#fdcb6e,stroke:#c8a034,color:#333
    style D fill:#fdcb6e,stroke:#c8a034,color:#333
```

---

## Key Design Decisions

### Why DAG over Pipeline?

Multi-agent workflows rarely execute linearly. Consider a research-style workflow (patterned after the internal deep research graph): after an initial planning step, _two specialist analysts_ (AI-focused and SWE-focused) run in parallel over the same evidence bundle. Their outputs merge into a Chain-of-Verification (CoVe) step, which conditionally triggers another research round based on confidence scoring. A pipeline would serialize the analysts unnecessarily; a DAG with `asyncio.wait(FIRST_COMPLETED)` maximizes throughput.

### Why YAML Workflow Definitions?

Workflow structure should be auditable and version-controlled separately from execution logic. Each YAML file declares steps, their agent assignments, input/output mappings with expression syntax (`${steps.intake_scope.outputs.scoped_goal}`), conditional gates (`when:`), and loop termination conditions (`loop_until:`). The runtime compiles these into executable graphs — the YAML is the single source of truth for workflow topology.

### Why Tiered Model Routing?

Mapping workflow steps to models by name creates brittleness: model names change, endpoints go down, pricing shifts. Instead, each agent is assigned a _capability tier_ (e.g., `tier3_analyst`). The router resolves this to the best available model at runtime, with fallback chains like:

```
Tier 3: gemini-2.5-flash → gh:gpt-4o → openai:gpt-4o → anthropic:claude-sonnet
```

The `SmartModelRouter` extends this with health-weighted selection, adaptive cooldowns (exponential backoff on failures), and circuit breaker patterns — if a model fails repeatedly, it's temporarily excluded from selection.

### Why Rubric-Based Scoring?

LLM outputs resist binary pass/fail evaluation. The scoring system uses YAML-defined rubrics with weighted criteria, score normalization with clamping, and explicit handling of missing criteria. For complex evaluations, a multidimensional scoring engine classifies outputs across five orthogonal dimensions (coverage, source quality, agreement, verification, recency) into lettered tiers (S/A/B/C/D/F), with configurable pass/fail gates per dimension.

---

## Workflow Definitions

The engine ships with **6 production workflow definitions**, each solving a distinct orchestration pattern:

| Workflow | Pattern | Description |
|----------|---------|-------------|
| `code_review` | Fan-out / fan-in | Parse code → parallel architecture + quality reviews → synthesis |
| `bug_resolution` | Sequential with verification | Reproduce → root cause analysis → fix → test → verify |
| `fullstack_generation` | Sequential with parallel sub-steps | Requirements → API design → frontend + backend in parallel → integration |
| `iterative_review` | Multi-loop with bounded iteration | Review → feedback → revise → re-review until quality gates pass |
| `conditional_branching` | Conditional DAG | Steps execute or skip based on runtime condition evaluation |
| `test_deterministic` | Tier-0 only | Deterministic step for testing the engine without LLM calls |

### Example: Multi-Agent Workflow DSL

The following illustrates the full power of the workflow DSL — iterative research with bounded rounds, conditional execution, parallel specialist analysis, and confidence-gated termination:

```yaml
steps:
  - name: intake_scope
    agent: tier3_planner
    description: Clarify user objective, constraints, and success criteria
    tools: [context_store]
    inputs:
      topic: ${inputs.topic}
      goal: ${coalesce(inputs.goal, inputs.topic)}
    outputs:
      scoped_goal: scoped_goal

  - name: analyst_ai_round1         # ← Runs in parallel
    agent: tier3_analyst             #   with analyst_swe_round1
    depends_on: [retrieval_react_round1]
    ...

  - name: analyst_swe_round1        # ← Runs in parallel
    agent: tier3_analyst             #   with analyst_ai_round1
    depends_on: [retrieval_react_round1]
    ...

  - name: hypothesis_tree_tot_round2
    agent: tier3_reasoner
    depends_on: [coverage_confidence_audit_round1]
    when: ${inputs.max_rounds} >= 2 and not ${steps...gate_passed}
    # ↑ Conditional: only runs if confidence gate hasn't passed
```

#### Execution Flow (Single Research Round)

```mermaid
graph LR
    A["🎯 intake_scope<br/><i>tier3_planner</i>"] --> B["📋 source_policy<br/><i>tier2_researcher</i>"]
    B --> C["🌳 hypothesis_tree<br/><i>tier3_reasoner</i>"]
    C --> D["🔎 retrieval_react<br/><i>tier2_researcher</i>"]

    D --> E["🤖 analyst_ai<br/><i>tier3_analyst</i>"]
    D --> F["💻 analyst_swe<br/><i>tier3_analyst</i>"]

    E --> G["✅ cove_verify<br/><i>tier3_reviewer</i>"]
    F --> G

    G --> H{"📊 confidence<br/>gate passed?"}

    H -- "No" --> C2["🌳 next round<br/><i>refine hypotheses</i>"]
    H -- "Yes" --> I["📝 final_synthesis<br/><i>tier4_writer</i>"]
    I --> J["📦 rag_package<br/><i>tier2_assembler</i>"]

    style A fill:#4a90d9,stroke:#2c5f8a,color:#fff
    style E fill:#e17055,stroke:#b34530,color:#fff
    style F fill:#e17055,stroke:#b34530,color:#fff
    style G fill:#6c5ce7,stroke:#4834a8,color:#fff
    style H fill:#fdcb6e,stroke:#c8a034,color:#333
    style I fill:#00b894,stroke:#008060,color:#fff
    style C2 fill:#fd79a8,stroke:#c0392b,color:#fff
```

---

## Project Structure

```
agentic-workflows/
├── agentic-workflows-v2/          # Core runtime package
│   ├── agentic_v2/
│   │   ├── engine/                # DAG executor, step runner, expression engine
│   │   │   ├── dag_executor.py    # Kahn's algorithm with asyncio scheduling
│   │   │   ├── dag.py             # DAG data structure with cycle detection
│   │   │   ├── expressions.py     # ${...} expression resolver
│   │   │   ├── runtime.py         # Subprocess & Docker isolated execution
│   │   │   └── step.py            # Step execution with should_run() gates
│   │   ├── models/                # Model routing and provider abstraction
│   │   │   ├── router.py          # Tier-based routing with DSL chain builder
│   │   │   ├── smart_router.py    # Health-weighted selection, circuit breakers
│   │   │   ├── backends.py        # Provider adapters (OpenAI, Anthropic, Gemini, etc.)
│   │   │   └── model_stats.py     # Performance tracking and persistence
│   │   ├── agents/                # Agent implementations
│   │   │   ├── orchestrator.py    # Capability-based agent matching + DAG scheduling
│   │   │   ├── architect.py       # System design agent
│   │   │   ├── coder.py           # Code generation agent
│   │   │   └── reviewer.py        # Code review agent
│   │   ├── workflows/             # Workflow runtime
│   │   │   ├── definitions/       # 6 YAML workflow definitions
│   │   │   ├── loader.py          # YAML → WorkflowConfig parser
│   │   │   └── runner.py          # Workflow execution orchestrator
│   │   ├── langchain/             # LangGraph integration
│   │   │   └── graph.py           # YAML → LangGraph StateGraph compiler
│   │   ├── server/                # FastAPI backend
│   │   │   ├── app.py             # Application factory
│   │   │   ├── evaluation.py      # Evaluation endpoints
│   │   │   ├── judge.py           # LLM-as-judge integration
│   │   │   ├── websocket.py       # Live SSE/WebSocket streaming
│   │   │   └── scoring_profiles.py
│   │   ├── contracts/             # Typed data contracts (Pydantic + dataclasses)
│   │   ├── prompts/               # Agent system prompts (Markdown)
│   │   ├── tools/                 # Built-in agent tools
│   │   └── cli/                   # `agentic` CLI entry point
│   ├── ui/                        # React dashboard (Vite + TypeScript)
│   ├── tests/                     # 100+ test files
│   └── pyproject.toml             # hatchling build, optional dep groups
│
├── agentic-v2-eval/               # Evaluation framework package
│   ├── src/agentic_v2_eval/
│   │   ├── datasets/              # Dataset adapters (SWE-bench, etc.)
│   │   ├── evaluators/            # Rubric-based evaluators
│   │   ├── reporters/             # Result reporting
│   │   └── scoring/               # Scoring utilities
│   └── tests/
│
├── tools/                         # Shared utilities
│   ├── llm/                       # Provider adapters, probes, ranking
│   └── core/                      # Config, errors, caching, helpers
│
└── .github/                       # CI/CD and GitHub configuration
```

---

## Technical Highlights

### DAG Executor — Concurrent Scheduling Engine

The heart of the runtime is `dag_executor.py`, implementing Kahn's algorithm with `asyncio.wait(FIRST_COMPLETED)` for true parallel scheduling:

- **Dynamic scheduling**: Steps are dispatched as soon as all dependencies resolve — no artificial batching
- **Max concurrency control**: Configurable limit prevents resource exhaustion on large DAGs
- **Cascade failure propagation**: When a step fails, all transitively dependent steps are automatically skipped via BFS traversal
- **Deadlock detection**: Unreachable steps (unmet dependencies after all runnable steps complete) are detected and force-skipped
- **Observable execution**: Every step transition emits structured events via an `on_update` callback for SSE/WebSocket streaming to the React UI

### Smart Model Router — Resilient Model Selection

The `SmartModelRouter` goes beyond simple fallback chains:

- **Health-weighted selection**: Models with better track records are preferred, scored by `success_rate × (1 / avg_latency)`
- **Adaptive cooldowns**: Cooldown duration scales with consecutive failures via exponential backoff (`base × multiplier^failures`)
- **Circuit breaker pattern**: Models in `OPEN` state are excluded from selection until a configurable number of probe successes
- **Cost-aware routing**: Optional `max_cost` filter excludes models above a cost-per-token threshold
- **Stats persistence**: Performance data survives process restarts via atomic JSON serialization

### LangGraph Compiler — YAML to Executable Graph

`graph.py` compiles YAML workflow configs into LangGraph `StateGraph` objects:

- One node per step, with tier-appropriate agent construction
- Conditional edges from `when:` expressions (steps self-skip when conditions aren't met, preserving graph connectivity)
- Loop edges from `loop_until:` expressions with iteration counting and max bounds
- Multi-model failover: each LLM node tries candidates in order, catching retryable errors and advancing to the next model
- Full token tracking via provider-specific metadata extraction (OpenAI, Anthropic, Gemini)

### Evaluation Framework — Rubric-Based Scoring

The evaluation system supports multiple scoring profiles:

- **Weighted criteria scoring**: Each rubric criterion has a weight; final scores are normalized with clamping and missing-criteria awareness
- **Multidimensional scoring**: DORA-style classification across 5 dimensions with S/A/B/C/D/F tiers and configurable gate logic
- **LLM-as-judge**: Integrates an LLM evaluator for subjective quality assessment with structured rubric prompts
- **Scoring profiles**: Switchable configurations (Profile A–E) for different evaluation contexts

---

## Quick Start

> **Fast path:** clone → setup → [`docs/ONBOARDING.md`](docs/ONBOARDING.md) (full guide) → [`docs/DEMO.md`](docs/DEMO.md) (the three commands that prove the platform is alive, with expected outputs). The Installation block below is the equivalent manual path for contributors who want package-level control.

### Prerequisites

- Python 3.11+
- **Option 1:** At least one LLM provider configured (see `.env.example` for supported providers)
- **Option 2:** Or run with `AGENTIC_NO_LLM=1` (placeholder mode — no provider key needed) to explore the platform without setting up credentials. See [`docs/NO_LLM_MODE.md`](docs/NO_LLM_MODE.md) for details and scope limitations.

### Installation

```bash
# Clone the repository
git clone https://github.com/tafreeman/agentic-systems-lab.git
cd agentic-systems-lab

# One-command bootstrap (installs root helpers, all three Python packages, and UI deps)
just setup

# Or install the runtime package directly if you do not have `just` available:
cd agentic-workflows-v2
pip install -e ".[dev,server,langchain]"

# Configure your environment
cp ../.env.example ../.env
# Edit .env with your API keys
```

### Running a Workflow

```bash
# List available workflows
agentic list workflows

# Create a JSON input file for the workflow
printf '%s\n' '{"input_text": "agentic AI"}' > test-input.json

# Run a deterministic smoke test workflow
agentic run test_deterministic --input test-input.json

# Run with dry-run (validates DAG without executing)
agentic run code_review --dry-run
```

### Starting the Dashboard

```bash
# Start the FastAPI backend
cd agentic-workflows-v2
uvicorn agentic_v2.server.app:create_app --factory --reload --port 8010

# Start the React UI (in another terminal)
cd agentic-workflows-v2/ui
npm install && npm run dev
```

### Running Tests

```bash
# Runtime tests (100+ test files)
cd agentic-workflows-v2
pytest tests/ -v --cov=agentic_v2

# Evaluation framework tests
cd agentic-v2-eval
pytest tests/ -v
```

---

## Development

### Code Quality Toolchain

This project enforces code quality through pre-commit hooks:

| Tool | Purpose |
|------|---------|
| **black** | Code formatting (88 char line length) |
| **isort** | Import sorting (black-compatible profile) |
| **ruff** | Fast linting with auto-fix |
| **mypy** | Static type checking |
| **docformatter** | Docstring formatting |
| **pydocstyle** | Google-style docstring enforcement |

```bash
# Install pre-commit hooks
pre-commit install

# Run all hooks manually
pre-commit run --all-files
```

### Code Style

- **Type annotations throughout** — `dict[str, float]`, `Optional[str]`, `list[dict[str, Any]]` — consistent Python 3.11+ generics
- **Dataclasses** — frozen where appropriate, field factories, clean defaults
- **Custom exception hierarchy** — `MissingDependencyError`, `CycleDetectedError` with structured attributes
- **Google-style docstrings** — Args/Returns/Raises sections across all public APIs
- **Async-first** — `pytest-asyncio` for async test infrastructure

### Optional Dependency Groups

```toml
[project.optional-dependencies]
dev       = ["pytest", "pytest-asyncio", "pytest-cov", "black", "ruff"]
server    = ["fastapi", "uvicorn", "python-multipart"]
langchain = ["langchain", "langchain-openai", "langchain-anthropic", "langchain-google-genai"]
tracing   = ["opentelemetry-sdk", "opentelemetry-exporter-otlp-proto-grpc"]
claude    = ["anthropic", "claude-agent-sdk"]
```

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a user-facing history of features, improvements, and fixes.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for monorepo-wide contribution guidelines — local gates, commit format, when an ADR is required, and the PR checklist. Package-specific notes are at [`agentic-workflows-v2/CONTRIBUTING.md`](agentic-workflows-v2/CONTRIBUTING.md).

**Built with AI assistance.** Parts of this lab were developed with LLM coding assistants under human review; every change passes the same lint/type/test/coverage gates regardless of how it was produced. See [CONTRIBUTING.md §9](CONTRIBUTING.md#9-ai-assisted-development) for the full policy.

## Roadmap & Known Limitations

- [`docs/ROADMAP.md`](docs/ROADMAP.md) — epics shipped in April 2026, the Epic 4 numbering gap, and proposed next work.
- [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md) — honest accounting of currently-open issues (SLO empty-window, provider-key dependence, and remaining contract-drift work).
- [`docs/MIGRATIONS.md`](docs/MIGRATIONS.md) — breaking changes since the last coherent release, starting with the `presentation/` system extraction.

## Security

See [SECURITY.md](agentic-workflows-v2/SECURITY.md) for vulnerability reporting procedures.

## License

This project is licensed under the MIT License — see [LICENSE](agentic-workflows-v2/LICENSE) for details.
