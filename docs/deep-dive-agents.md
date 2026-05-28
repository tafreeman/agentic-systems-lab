# Deep-Dive: Agents (`agentic-workflows-v2/agentic_v2/agents/`)

**Generated:** 2026-04-17
**Files analyzed:** 15
**Total LOC:** 4,337
**Target type:** folder
**Scan mode:** exhaustive

---

## Overview

The `agents/` package defines the agent abstraction layer for the `agentic-workflows-v2` runtime. It provides `BaseAgent` (a typed lifecycle-driven protocol), concrete specialized agents (Coder, Reviewer, Architect, TestAgent, Orchestrator), supporting utilities (conversation memory, capability matching, robust JSON extraction), and pluggable backend implementations (Anthropic Messages API, `claude-agent-sdk`).

**Responsibilities:**
- Typed agent lifecycle (`base.py`)
- Conversation memory with auto-summarization (`memory.py`)
- Capability-based agent-to-task matching (`capabilities.py`)
- Robust structured-output parsing (`json_extraction.py`)
- Concrete specialists (Coder, Reviewer, Architect, TestAgent)
- Meta-agent for task decomposition and delegation (`orchestrator.py`)
- Config loading (`config.py`)
- Backend implementations (`implementations/`)

---

## Agent Taxonomy

```
BaseAgent[TInput, TOutput]               (abstract, generic protocol)
  ├─ CoderAgent         (capabilities: CodeGeneration, SelfReflection)
  ├─ ReviewerAgent      (capabilities: CodeReview)
  ├─ ArchitectAgent     (capabilities: SystemsDesign)
  ├─ TestAgent          (capabilities: TestGeneration)
  └─ OrchestratorAgent  (capabilities: TaskDecomposition, AgentMatching)

implementations/ (backend adapters, not BaseAgent subclasses)
  ├─ ClaudeAgent         → Anthropic Messages API (tool_use)
  ├─ ClaudeSDKAgent      → claude-agent-sdk (standalone, no BaseAgent)
  └─ agent_loader        → factory + registry from YAML persona files
```

**Design principle:** Composition over inheritance. Capabilities are declared via mixin-like `CapabilitySet` objects rather than deep hierarchies.

---

## Agent Lifecycle

State machine (enforced by convention in `base.py`):

```
CREATED → INITIALIZING → READY → RUNNING → COMPLETED
                                        ↘ FAILED
                                        ↘ CANCELLED
```

**Per-invocation flow:**
1. **Construct** — agent instantiated with config, capabilities, LLM client, tool registry.
2. **Initialize** — load persona prompt (`prompts/*.md`), bind tools filtered by model tier.
3. **Prepare context** — merge system prompt + conversation memory + task input; apply token budget.
4. **LLM call** — via `models.SmartModelRouter` → backend (Anthropic, OpenAI, etc.).
5. **Tool invocation loop** — if LLM emits tool_use, dispatch via `ToolRegistry`, append results, recall LLM.
6. **Parse output** — `json_extraction` for structured responses; Pydantic validation against contract.
7. **Memory update** — append user/assistant turn; auto-summarize if window exceeded.
8. **Emit events** — lifecycle events for observability.

---

## Module Inventory

### `__init__.py` — 121 LOC
- **Purpose:** Package exports and agent factory registration. Re-exports public API and registers agent classes with the implementations loader.
- **Exports:** `BaseAgent`, `CoderAgent`, `ReviewerAgent`, `ArchitectAgent`, `TestAgent`, `OrchestratorAgent`, `ConversationMemory`, `CapabilitySet`.
- **Implementation detail:** Late-binding factory registration avoids circular imports with `OrchestratorAgent`.

### `base.py` — 541 LOC
- **Purpose:** Abstract `BaseAgent[TInput, TOutput]` generic with lifecycle state machine, event emission, tool binding, and default invocation loop.
- **Key exports:**
  - `BaseAgent[TInput, TOutput]` — abstract class with `async run(input) -> TOutput`, `async _invoke_llm()`, `_bind_tools()`, `_emit_event()`.
  - `AgentState` enum (CREATED, INITIALIZING, READY, RUNNING, COMPLETED, FAILED, CANCELLED).
  - `AgentEvent` dataclass.
- **Imports:** `typing.Generic`, `..contracts`, `..models.SmartModelRouter`, `..tools.ToolRegistry`.
- **Risks:** State transitions not type-enforced — relies on convention + tests.
- **Suggested tests:** illegal transitions raise; event ordering; generic type erasure.

### `capabilities.py` — 383 LOC
- **Purpose:** Capability declaration + scoring for agent-to-task matching. Enables runtime selection of the best-fit agent for a subtask.
- **Key exports:** `Capability` enum (CodeGeneration, CodeReview, SystemsDesign, TestGeneration, TaskDecomposition, AgentMatching, SelfReflection, ...), `CapabilitySet`, `score_match(task_needs, agent_caps) -> float`.
- **Implementation:** Weighted overlap + proficiency clamp to [0.0, 1.0]; division-by-zero avoided with `max(0.01, ...)`.
- **Suggested tests:** scoring monotonicity, empty sets, ties.

### `coder.py` — 367 LOC
- **Purpose:** Concrete Coder agent specialized for code generation with optional self-reflection pass.
- **Key exports:** `CoderAgent(BaseAgent[CodeTaskInput, CodeTaskOutput])`, `CODER_SYSTEM_PROMPT`.
- **Capabilities:** CodeGeneration, SelfReflection.
- **Implementation:** Two-pass mode — initial generation → critique → revision. Controlled by `config.self_reflect`.

### `reviewer.py` — 370 LOC
- **Purpose:** Code-review agent producing structured findings (severity, file, line, category, recommendation).
- **Key exports:** `ReviewerAgent(BaseAgent[ReviewInput, ReviewOutput])`.
- **Implementation:** Uses `json_extraction` to parse findings list; supports per-category gating.

### `architect.py` — 361 LOC
- **Purpose:** Architecture-design agent producing component diagrams, data flow, and decision rationale.
- **Key exports:** `ArchitectAgent(BaseAgent[DesignInput, DesignOutput])`.

### `test_agent.py` — 544 LOC
- **Purpose:** Test-generation agent producing pytest/Jest test scaffolds with fixtures.
- **Key exports:** `TestAgent(BaseAgent[TestInput, TestOutput])`.

### `orchestrator.py` — 541 LOC
- **Purpose:** Meta-agent that decomposes a high-level task into subtasks, scores candidate agents via `capabilities.score_match`, dispatches, and aggregates results. Supports fallback chains and DAG execution.
- **Key exports:** `OrchestratorAgent(BaseAgent[OrchestratorInput, OrchestratorOutput])`, `decompose_task()`, `select_agent()`.
- **Imports:** `..engine.dag`, capabilities, all concrete agents (via factory registry).
- **Risks:** Silent fallback chain — logs warnings but returns best-effort output if all agents fail.
- **Suggested tests:** all-agents-fail scenario surfaces error; DAG cycle detection; capability tie-breaking.

### `memory.py` — 266 LOC
- **Purpose:** `ConversationMemory` with sliding-window summarization. Keeps up to 50 messages and ~8000 tokens; auto-summarizes older turns when window exceeded. First system message always preserved.
- **Key exports:** `ConversationMemory`, `Message`, `summarize_window()`.
- **Implementation:** 4-char-per-token heuristic; summarization delegates to LLM client if configured, else naive concat.
- **Suggested tests:** window overflow triggers summarize; system message never evicted; token-count accuracy.

### `config.py` — 139 LOC
- **Purpose:** Agent configuration loader from YAML persona files (`prompts/*.md`) + runtime overrides.
- **Key exports:** `AgentConfig`, `load_agent_config(name)`, `AgentProfile`.

### `json_extraction.py` — 155 LOC
- **Purpose:** Robust JSON extraction from LLM freeform responses. Three strategies in order: fenced ` ```json `, fenced ` ``` ` (any), balanced-brace scan (handles strings with escapes).
- **Key exports:** `extract_json(text) -> dict | list | None`, `ExtractionStrategy`.
- **Implementation:** Balanced-brace scan tracks string state (`"`, `\"`) to avoid false matches.
- **Strengths:** Avoids greedy regex pitfalls; handles nested objects and embedded strings.
- **Suggested tests:** malformed responses, nested braces in strings, truncated JSON, multiple JSON blocks.

### `implementations/__init__.py` — 36 LOC
- **Purpose:** Exposes backend implementations and the agent loader.
- **Exports:** `ClaudeAgent`, `ClaudeSDKAgent`, `load_agent(name)`.

### `implementations/agent_loader.py` — 130 LOC
- **Purpose:** Factory registry for agent classes. Maps agent name → factory function. Populated by `agents/__init__.py` during import.
- **Key exports:** `register_agent(name, factory)`, `load_agent(name, config) -> BaseAgent`, `AGENT_REGISTRY`.

### `implementations/claude_agent.py` — 228 LOC
- **Purpose:** Backend adapter using Anthropic Messages API directly. Handles tool_use, streaming, and content-block parsing.
- **Key exports:** `ClaudeAgent` (inherits `BaseAgent`), `invoke_claude()`.
- **Imports:** `anthropic` SDK.

### `implementations/claude_sdk_agent.py` — 155 LOC
- **Purpose:** Backend using `claude-agent-sdk` package. Standalone — does not inherit `BaseAgent` (uses SDK's own lifecycle).
- **Key exports:** `ClaudeSDKAgent`, `run_claude_sdk()`.
- **Gotcha:** Not part of `BaseAgent` taxonomy — callers must branch on agent type.

---

## Dependency Graph (within `agents/`)

```
base.py
  ↑
  ├─ coder.py         → json_extraction.py, memory.py, capabilities.py
  ├─ reviewer.py      → json_extraction.py, memory.py, capabilities.py
  ├─ architect.py     → json_extraction.py, memory.py, capabilities.py
  ├─ test_agent.py    → json_extraction.py, memory.py, capabilities.py
  └─ orchestrator.py  → capabilities.py, (factory registry from __init__)

implementations/
  ├─ agent_loader.py  (registry populated by __init__.py)
  ├─ claude_agent.py  → base.py
  └─ claude_sdk_agent.py  (standalone)
```

No circular imports — `OrchestratorAgent` uses late-binding factory lookup to avoid importing concrete agents at module load.

---

## Capabilities & Config

- **`capabilities.py`**: declarative enum of skills an agent provides; `CapabilitySet` composes them. `score_match(task_needs, agent_caps)` returns weighted float for runtime routing.
- **`config.py`**: loads YAML persona (system prompt, expertise, boundaries, output format) and merges with runtime overrides (temperature, model tier, tool allowlist).

**Flow:**
1. Workflow YAML step declares required capabilities + agent name.
2. `agent_loader.load_agent(name, config)` constructs agent with `AgentConfig`.
3. `OrchestratorAgent` uses `capabilities.score_match` when subtasks need dynamic agent selection.

---

## Memory Integration

`memory.ConversationMemory` is self-contained and does NOT use `core.memory.MemoryStoreProtocol` — that protocol is for cross-run persistence (e.g., RAG-backed long-term memory). `ConversationMemory` is per-invocation context window management only.

For long-term memory, agents delegate to `core.memory.RAGMemoryStore` via `rag/` — retrieved chunks are injected into the prompt by the agent's `_prepare_context()`.

---

## JSON Extraction

Three strategies, applied in order until one succeeds:

1. **Fenced `json`** — ` ```json\n{...}\n``` `
2. **Fenced any** — ` ```\n{...}\n``` `
3. **Balanced-brace scan** — walks text tracking `{` / `}` depth; respects string literals and escape sequences.

**Why not regex:** greedy regex on nested braces fails silently; the balanced-brace scanner is correct by construction.

**Edge cases handled:** embedded `"}"`, escaped quotes `\"`, newlines inside strings, multiple JSON blocks (returns first valid).

---

## Integration Points

- **`..contracts`**: `TaskInput`/`TaskOutput` Pydantic models per agent.
- **`..models`**: `ModelTier`, `SmartModelRouter`, `get_client()` for LLM dispatch.
- **`..tools`**: `BaseTool`, `ToolRegistry` for function-calling.
- **`..engine`**: `DAG`, `StepDefinition` (orchestrator only).
- **`..prompts/*.md`**: persona definitions loaded by `config.py`.
- **`..rag`**: optional long-term memory via `RAGMemoryStore`.
- **External**: `anthropic` SDK, `claude-agent-sdk`.

**Used by:**
- `server/execution.py` (workflow runner invokes agents).
- `server/routes/agents.py` (enumeration via `load_agent_config`).
- `langchain/` adapter (wraps agents as LangGraph nodes).
- `engine/` native executor (invokes agents as DAG step handlers).
- Tests: `tests/test_agents/*.py`.

---

## Risks & Gotchas

1. **JSON extraction ambiguity** — if LLM emits multiple JSON blocks, only first is returned.
2. **Memory summarization loss** — 4-char/token heuristic is approximate; real token count may differ ±15%.
3. **Capability scoring** — no type-level enforcement that `Capability` enums align across declarations.
4. **Tool tier binding** — requires consistent `ModelTier` numbering in `..models`; drift breaks filtering silently.
5. **Orchestrator silent fallback** — logs warnings per failure but may return partial output; callers must check `OrchestratorOutput.status`.
6. **Mock backend fallback** — when `llm_client.backend is None`, agents return mock responses (dev mode). Must not leak to prod.
7. **State machine by convention** — illegal transitions not raised at type level; only caught by tests.
8. **Circular deps** — `OrchestratorAgent` uses late-binding factory registry; direct imports would break.
9. **`ClaudeSDKAgent` outside taxonomy** — does not inherit `BaseAgent`; callers need type narrowing.
10. **Agent config merging** — YAML + runtime overrides; unclear precedence in edge cases (nested dicts).

---

## Verification Steps

Before shipping agent changes:

1. `pip install -e ".[dev,claude]"` from `agentic-workflows-v2/`.
2. `python -m pytest tests/test_agents -v` — full agent suite green.
3. `python -m pytest tests/test_agents/test_json_extraction.py` — structured-output robustness.
4. `python -m pytest tests/test_agents/test_memory.py` — window overflow + summarization.
5. `agentic list agents` — all agents discoverable.
6. Run a minimal workflow using each concrete agent via `POST /api/run`.
7. `pre-commit run --all-files` — mypy strict passes with generics.

---

## Suggested Tests

- **BaseAgent**: state-machine legal/illegal transitions; event ordering; generic type preservation.
- **ConversationMemory**: window overflow triggers summarize; system message eviction prevention; token-count accuracy vs actual tokenizer.
- **CapabilitySet**: scoring monotonicity, empty intersections, ties, proficiency clamps.
- **JSON extraction**: malformed LLM responses (truncated, multiple blocks, nested braces in strings, escape sequences).
- **OrchestratorAgent**: all-agents-fail raises rather than silently returning; DAG cycle detection; capability tie-breaking.
- **ClaudeAgent**: tool_use round-trip; streaming content blocks; rate-limit retry.
- **ClaudeSDKAgent**: session lifecycle; standalone invocation path.
- **agent_loader**: unknown agent raises; registry population after late-binding.
- **Config**: YAML parse errors; override precedence; missing persona file.
- **Mock backend**: dev-mode path produces deterministic output; never fires in production config.

---

## Related Code & Reuse Opportunities

- **`json_extraction.py`** could be extracted as a standalone library — it's generally useful and better than greedy regex approaches.
- **`ConversationMemory`** could generalize to non-agent contexts (e.g., chat UI) — move to `core/memory.py`.
- **`CapabilitySet.score_match`** is a public-utility-caliber function; could be exposed for external orchestrators.
- **Agent event system** parallels `server/websocket.py` hub — consider unifying into `core/events.py`.
- **System prompts** currently in `prompts/*.md`; consider externalizing into versioned YAML for experimentation.
- **Backend adapters** (`ClaudeAgent`, `ClaudeSDKAgent`) could use the existing `AdapterRegistry` pattern from `adapters/` for symmetry.
- **Mock backend** pattern should be promoted to a shared `tools.llm.mock_client` for cross-package reuse.
