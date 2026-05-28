# agentic-v2-eval — Deep Dive Documentation

**Generated:** 2026-04-18
**Scope:** `agentic-v2-eval/`
**Files Analyzed:** 60 (Python + YAML + TOML + Markdown, `.venv` / `__pycache__` / `dist` / `build` excluded)
**Workflow Mode:** Exhaustive Deep-Dive

---

## Overview

`agentic-v2-eval` is the evaluation framework for the `agentic-systems-lab` monorepo. Its job is to score LLM outputs (prose, prompts, code, agentic workflow runs) against weighted rubrics, using deterministic LLM-as-judge patterns plus static metrics. It is a separate `uv` workspace member that depends on `agentic-systems-lab-tools` (for the shared LLM client) but is decoupled from the `agentic-workflows-v2` runtime — the runtime imports only the `LLMClientProtocol` from here.

**Purpose:** Produce reproducible, rubric-weighted scores and human-readable reports (JSON / Markdown / HTML) from evaluation runs.

**Key responsibilities:**
- Rubric loading and validation (`rubrics/`)
- Evaluator strategies: LLM judge, pattern judge (ReAct / CoVe / Reflexion / RAG), standard prompt-quality judge, quality judge (coherence/fluency/relevance/groundedness/similarity)
- Batch and async-streaming test-case execution
- Weighted scoring via `Scorer` and rubric YAML
- Multi-format reporting
- Subprocess sandbox for executing evaluation-time code (`sandbox/local.py`)
- Dataset bridge to `tools.agents.benchmarks` (HumanEval, MBPP, etc.)

**Integration summary:**
- **Upstream:** `tools.llm.llm_client.LLMClient` (static) + `tools.agents.benchmarks.*` (lazy)
- **Downstream:** `agentic-workflows-v2/agentic_v2/models/llm.py` imports `LLMClientProtocol`
- **CLI:** `agentic-v2-eval evaluate <json> [--rubric NAME]` and `... report <json>`

---

## Complete File Inventory

### Top-level config

#### `agentic-v2-eval/pyproject.toml`
- **Purpose:** Hatchling build, entry points, dependencies, pytest/coverage/mypy tool config.
- **LOC:** 62
- **Key details:** `requires-python >=3.11`. Runtime deps minimal: `pyyaml>=6.0` + workspace-sibling `agentic-systems-lab-tools`. Dev extras: pytest, pytest-asyncio, mypy, ruff. `asyncio_mode = "auto"`. Coverage `fail_under = 80`, branch coverage on. mypy `disallow_untyped_defs`.
- **Contributor note:** `agentic-systems-lab-tools` is a uv workspace dep — always `uv sync` from repo root. Version bumps here must be mirrored in `__init__.py::__version__`.

#### `agentic-v2-eval/README.md`
- User-facing quick-start and module listing. The inner `src/agentic_v2_eval/README.md` is a shorter duplicate with a stale import path (`from src.agentic_v2_eval.scorer`). **Fix:** change to `from agentic_v2_eval.scorer`.

### Package top-level (`src/agentic_v2_eval/`)

#### `__init__.py` (52 LOC)
- **Purpose:** Public surface; re-exports `Scorer`, `ScoringResult`, `EvaluatorRegistry`, `PatternEvaluator`, `PatternScore`, `StandardEvaluator`, `StandardScore`, `QualityEvaluator`, `LLMEvaluatorDefinition`, the five quality constants (`COHERENCE`, `FLUENCY`, `GROUNDEDNESS`, `RELEVANCE`, `SIMILARITY`), `Evaluator`, `LLMClientProtocol`, `__version__ = "0.3.0"`.
- **Side effects on import:** parses `quality.yaml`, `prompt_standard.yaml`, `prompt_pattern.yaml`; populates `EvaluatorRegistry`.
- **Risk:** YAML load failures are caught with `print("Warning: ...")` and import still succeeds — evaluators silently degrade to 0.0 scores. Violates the repo's structured-logging rule.

#### `__main__.py` (208 LOC)
- **Exports:** `main(argv)`, `cmd_evaluate(args)`, `cmd_report(args)`.
- **CLI:** `evaluate` (scores a results JSON using a rubric), `report` (produces JSON/Markdown/HTML). Input normalizes bare dict, list-of-dicts, or `{"results": [...]}`.
- **Risk:** broad `except Exception as e` (~line 161) swallows unknown failures without traceback. Add traceback logging.

#### `interfaces.py` (66 LOC)
- **Exports:** `LLMClientProtocol` (`@runtime_checkable`), `Evaluator` (Protocol).
- **`LLMClientProtocol.generate_text` signature:** `(model_name: str, prompt: str, temperature: float = 0.1, max_tokens: int = 1000, **kwargs) -> str`.
- **Naming collision:** both `interfaces.py::Evaluator` (Protocol, `output: str`) and `evaluators/base.py::Evaluator` (ABC, `output: Any`) exist. Rename one to avoid confusion.

#### `scorer.py` (187 LOC)
- **Exports:** `Criterion` (dataclass), `ScoringResult`, `Scorer` (accepts `str | Path | dict` — path or in-memory rubric).
- **Normalization:** `(value - min) / (max - min)`; clamped. `weighted_score = sum(norm * weight)`; `total_score = raw_sum / len(self.criteria)` **including missing criteria**.
- **Risk:** `total_score` divisor includes missing criteria, making values non-comparable across runs with different result completeness. `weighted_score` is correct; `total_score` is not.

#### `datasets.py` (220 LOC)
- **Purpose:** Lazy bridge to `tools.agents.benchmarks`. Module-level `None` sentinels populated on first `_ensure_imports()` call. Lazy `__getattr__` exposes typing stubs.
- **Risk:** `language` / `difficulty` filters applied client-side **after** load — `limit=5` may return fewer than 5 tasks when filters are applied. Push filters into the loader for correctness.

### `adapters/`

#### `adapters/llm_client.py` (143 LOC)
- **Exports:** `LLMClientAdapter` (dataclass), `create_llm_client(model, temperature, max_tokens, system_instruction)`.
- **Pattern:** stores the `LLMClient` class (not instance) — `generate_text` is called as a static method.
- **Risk:** if `tools.llm.LLMClient` is ever refactored to require instantiation, this adapter breaks silently. Tests mock the class, masking this structural assumption.

### `evaluators/`

#### `evaluators/base.py` (86 LOC)
- **Exports:** `Evaluator` (ABC with abstract `evaluate(output, **kwargs) -> dict`), `EvaluatorRegistry` (class-variable singleton with `@register(name)` decorator).
- **Risk:** `EvaluatorRegistry._registry` is a `ClassVar[dict]` — state persists across test runs unless explicitly cleared. Tests registering custom evaluators must restore state.

#### `evaluators/llm.py` (149 LOC)
- **Exports:** `Choice` (dataclass), `STANDARD_CHOICES` (5-point 0.0–1.0 map), `LLMEvaluator` (registered as `"llm"`).
- **Template substitution** uses `{{var}}` via `str.replace`. **Score extraction** tries exact last-line match first, then substring search in last 3 lines. **Temperature fixed at 0.0.** Returns `{"score": 0.0, "passed": False, "error": ...}` on exception.

#### `evaluators/pattern.py` (326 LOC)
- **Exports:** `PatternScore`, `PatternEvaluator` (registered as `"pattern"`); module-level constants loaded at import from `prompt_pattern.yaml`.
- **Workflow:** multi-run LLM judge for ReAct / CoVe / Reflexion / RAG. Aggregates N runs via `statistics.median`. Hard gates: POI ≥ 4, PC ≥ 4, CA ≥ 4, PR ≥ 0.75. `overall_uni` sums `PIF + POI + PC + CA + SRC + IR` (PR excluded).
- **Risk:** `print()` used for run failures (~lines 211, 241) — replace with `logger`. Default `runs=1` but docstring says "usually 20".

#### `evaluators/quality.py` (164 LOC)
- **Exports:** `LLMEvaluatorDefinition`, `QualityEvaluator` (registered as `"quality"`), module-level `COHERENCE`, `FLUENCY`, `RELEVANCE`, `GROUNDEDNESS`, `SIMILARITY`.
- **Risk:** score-extraction logic duplicated verbatim with `llm.py`. Extract to a shared `_extract_choice_score(response, choices)` helper.

#### `evaluators/standard.py` (223 LOC)
- **Exports:** `StandardScore`, `StandardEvaluator` (registered as `"standard"`).
- **Details:** truncates prompts > 18k chars (head 16k + tail 1k + `[...TRUNCATED...]`). Hard-coded `max_tokens=900` for judge. Grade bands: A ≥ 90, B ≥ 80, C ≥ 70, D ≥ 60, else F.
- **Risk:** `max_tokens=900` not configurable — expose as parameter or move to YAML. "Uniform weights for now" note at line 156 is a documented deferred improvement.

### `metrics/`

#### `metrics/accuracy.py` (153 LOC)
- **Exports:** `calculate_accuracy`, `calculate_precision_recall`, `calculate_f1_score`, `calculate_confusion_matrix`.
- **Note:** `calculate_confusion_matrix` is not re-exported from `metrics/__init__.py` — callers must import directly.

#### `metrics/quality.py` (246 LOC)
- **Exports:** `code_quality_score`, `lint_score`, `complexity_score`.
- **Risk:** `lint_score` regex `r"[^\s]=|=[^\s=]"` is imprecise (flags `==`, misses `+=`/`-=`). Consider AST-based checks or subprocess linting.

#### `metrics/performance.py` (223 LOC)
- **Exports:** `PerformanceResult`, `execution_time_score`, `memory_usage_score`, `throughput_score`, `measure_time` (contextmanager), `benchmark` (harness with warmup), `latency_percentiles`.
- **Note:** percentile calculation uses floor index, not interpolation.

### `runners/`

#### `runners/batch.py` (140 LOC)
- **Exports:** `BatchResult[R]` (Generic with `success_rate`), `BatchRunner[T, R]`, `run_batch_evaluation(...)`.
- **Default:** `continue_on_error=True`; errors collected as `(index, exception)` tuples.

#### `runners/streaming.py` (267 LOC)
- **Exports:** `StreamingStats`, `StreamingRunner[T, R]`, `AsyncStreamingRunner[T, R]`, `run_streaming_evaluation(...)`.
- **Async pattern:** `iter_results` is an `async def` returning `AsyncIterator`. Bounded concurrency via semaphore-equivalent logic — drains one completed task when `pending >= max_concurrency`. Uses `inspect.isawaitable(value)` to handle sync or async evaluators transparently.
- **Risk:** nested async-generator pattern is non-obvious. Document or refactor.

### `reporters/`

#### `reporters/_summary.py` (39 LOC)
- Shared statistics helper. Iterates results, collects numeric fields per key, computes mean + optional min/max. Keys `{key}_mean`, `{key}_min`, `{key}_max`.

#### `reporters/json.py` (156 LOC)
- **Exports:** `JsonReportConfig`, `JsonReporter`, `generate_json_report`.
- Creates parent dirs; `default=str` serializer fallback.

#### `reporters/markdown.py` (224 LOC)
- **Exports:** `MarkdownReportConfig`, `MarkdownReporter`, `generate_markdown_report`.
- Pipe chars escaped; list/dict values truncated to 50 chars. Sorted columns.

#### `reporters/html.py` (340 LOC)
- **Exports:** `DEFAULT_STYLES`, `HtmlReportConfig` (with `score_thresholds: tuple[float, float]`, default `(0.5, 0.8)`), `HtmlReporter`, `generate_html_report`.
- Self-contained HTML (embedded CSS). Score cells classed `score-high / score-medium / score-low` via configured thresholds.

### `rubrics/`

#### `rubrics/__init__.py` (100 LOC)
- **Exports:** string constants `DEFAULT`, `AGENT`, `CODE`, `PATTERN`; `RUBRICS_DIR`; `load_rubric(name)`, `list_rubrics()`, `get_rubric_path(name)`.
- **No caching** — each call re-reads from disk. Consider `@lru_cache` for high-throughput use.

#### YAML rubric files
| File | Criteria | Weight sum | Notes |
|------|----------|------------|-------|
| `default.yaml` | 3 | 1.0 | Minimal: accuracy 0.5, completeness 0.3, efficiency 0.2 |
| `agent.yaml` | 6 | 1.0 | 0–5 level descriptors; pass=0.70, excellent=0.90 |
| `code.yaml` | 5 | 1.0 | Correctness/Completeness/Code Quality/Efficiency/Security; pass=0.75 |
| `pattern.yaml` | 6 | 1.0 | Phase Ordering/Completeness/Constraint Adherence are hard gates (min 4); pass=0.75 |
| `coding_standards.yaml` | 8 | — | References `docs/CODING_STANDARDS.md` (27 rules) |
| `quality.yaml` | 5 judges | — | Coherence/Fluency/Relevance/Groundedness/Similarity; `choices_type: standard_5_point` |
| `prompt_standard.yaml` | — | — | Single `judge_prompt` (5-dim 0–10 JSON judge) |
| `prompt_pattern.yaml` | — | — | `judge_prompt` + per-pattern definitions (react / cove / reflexion / rag) |

### `sandbox/`

#### `sandbox/base.py` (77 LOC)
- **Exports:** `ExecutionResult` (dataclass), `Sandbox` (ABC with `run_command`, `write_file`, `read_file`).

#### `sandbox/local.py` (297 LOC)
- **Exports:** `BLOCKED_COMMANDS` (18 dangerous names/patterns), `LocalSubprocessSandbox` (implements `Sandbox`, context manager).
- **Safety:** `tempfile.TemporaryDirectory` (cleaned up via `__exit__`/`__del__`). `_check_command_safety` checks lowercased executable name, then full command string for blocklist substrings. Path escape prevented by `work_dir.resolve().relative_to(self._root.resolve())`.
- **Risks:** `BLOCKED_COMMANDS` contains `":(){` (fork-bomb pattern) as a substring match — can false-positive on benign code. `curl`/`wget` blocked in safe mode, surprising for eval contexts needing HTTP — consider a separate network-block flag.

### `tests/`

| File | LOC | Scope |
|------|-----|-------|
| `conftest.py` | small | Inserts `src/` onto `sys.path` for editable-free runs |
| `test_eval.py` | ~454 | Integration across metrics, Scorer, all runners, reporters, CLI |
| `test_metrics.py` | ~247 | Accuracy + performance unit tests (class-based) |
| `test_adapters.py` | ~245 | `LLMClientAdapter` + `inspect.signature` protocol compliance |
| `test_benchmarks.py` | ~331 | `tools.agents.benchmarks.*` via `sys.path.insert` |
| `test_datasets_bridge.py` | ~196 | Lazy-load bridge; skips for network tests |
| `test_pattern_evaluator.py` | ~312 | PatternEvaluator with mock LLM; all 4 patterns |
| `test_quality_evaluator.py` | ~282 | QualityEvaluator + Choice template substitution |
| `test_reporters.py` | ~223 | All 3 reporters, HTML escaping, pipe escaping |
| `test_rubrics.py` | ~226 | Structural validation across all 4 rubrics (parametrized) |
| `test_sandbox.py` | ~163 | Sandbox with Windows/Linux branching, timeout, blocklist |
| `verify_p2.py` | ~96 | Standalone decoupling verification (no `tools` in pattern.py scope) |

---

## Contributor Checklist

**Risks & gotchas:**
1. Module-level YAML loading in all four evaluators — silent 0.0 degradation on missing/malformed rubric files.
2. `LLMClientAdapter` calls `LLMClient` as a **static class method** — a silent structural assumption not enforced by tests (they mock the class).
3. `EvaluatorRegistry._registry` is a shared `ClassVar`. Tests that register custom evaluators must tear down or they pollute subsequent tests.
4. `datasets.load_benchmark(..., limit=N, language=X)` applies the language filter client-side — result may have fewer than N tasks silently.
5. `Scorer.total_score` divides by `len(self.criteria)` including missing criteria — non-comparable across runs. Use `weighted_score` for cross-run comparisons.

**Pre-change verification steps:**
- `pytest agentic-v2-eval/tests/ -v --cov=agentic_v2_eval --cov-report=term-missing` (≥ 80% branch)
- `python agentic-v2-eval/tests/verify_p2.py` — decoupling sanity
- `pytest agentic-v2-eval/tests/test_rubrics.py` — rubric weight integrity
- `pytest agentic-v2-eval/tests/test_adapters.py::TestLLMClientProtocolCompliance` — protocol shape
- `pytest agentic-v2-eval/tests/test_eval.py::test_cli_evaluate_defaults_to_packaged_rubric` — CLI e2e

**Suggested tests before PR:**
```bash
cd agentic-v2-eval && pytest tests/ --cov=agentic_v2_eval --cov-report=term-missing
pytest agentic-v2-eval/tests/ -m "not integration and not slow"
ruff check agentic-v2-eval/src/
mypy agentic-v2-eval/src/agentic_v2_eval --strict
python agentic-v2-eval/tests/verify_p2.py
```

---

## Architecture & Design Patterns

### Code organization
Feature-oriented layout: `adapters/` (LLM bridge), `evaluators/` (scoring strategies), `metrics/` (static metrics), `runners/` (execution), `reporters/` (output), `rubrics/` (config + YAML), `sandbox/` (isolation). Top-level modules (`scorer.py`, `datasets.py`, `interfaces.py`, `__main__.py`) are glue/API layers.

### Design patterns
- **Decorator-based registry** (`EvaluatorRegistry.register("name")`) — class variable + lookup; pluggable without core edits.
- **Protocol-based dependency injection** (`LLMClientProtocol`, `Evaluator`) — enables clean mocking and multi-provider support.
- **Adapter pattern** (`LLMClientAdapter`) — wraps third-party `tools.llm.LLMClient` to satisfy protocol.
- **Strategy pattern** — four distinct evaluator strategies behind a uniform ABC.
- **Template Method / judge-pattern** — LLM judges parameterised by rubric YAML + prompt template.
- **Generic typed runners** (`BatchRunner[T, R]`, `StreamingRunner[T, R]`, `AsyncStreamingRunner[T, R]`).

### State management
- `Scorer` — instance-held rubric/criteria, immutable post-construction.
- `EvaluatorRegistry._registry` — `ClassVar[dict]` singleton, populated at import.
- `LLMClientAdapter._llm_client_class` — lazy class reference, singleton-like.
- `datasets.py` — module-level `None` sentinels populated on first use.
- Runners are stateless except for configuration.

### Error-handling philosophy
- Evaluators catch broad exceptions and return 0.0 + `"error"` payloads rather than raising — favours pipeline survival over fail-fast.
- `Scorer` raises `FileNotFoundError` / `ValueError` at construction; runtime scoring methods do not raise.
- Sandbox wraps all subprocess errors in `ExecutionResult(exit_code=-1, error=...)`.
- CLI `__main__` catches broad `Exception` and exits non-zero.

### Testing strategy
- Class-based unit tests for pure metrics (`test_metrics.py`).
- `MagicMock`-based LLM simulation for evaluator tests.
- `pytest.skip` for tests requiring network or local data.
- Parametrized rubric validation (weights, thresholds, structure).
- `verify_p2.py` as a runnable sanity script (dual-mode: pytest or `python`).
- `asyncio_mode = "auto"` — no explicit decorators.

---

## Data Flow

```
DATASET        → EVALUATOR         → SCORER        → REPORTER
load_benchmark   LLMClientAdapter    Scorer.score    Json/MD/HTML
(tools.*)        .generate_text      (rubric YAML)   (disk)
                 (N runs, median)
```

### Entry points
- `__main__.py` — CLI (`agentic-v2-eval evaluate|report`)
- `__init__.py` — public Python API
- `interfaces.py` — imported by `agentic-workflows-v2`

### Transformations
- **Dataset → task**: `BenchmarkTask` records loaded lazily from `tools.agents.benchmarks`.
- **Task → judge prompt**: template substitution with `{{var}}` in `LLMEvaluator`, or `str.format` with `{}` escaping in `PatternEvaluator` / `StandardEvaluator`.
- **Judge response → score**: last-line exact match → substring search → JSON parsing with markdown-fence stripping.
- **Multi-run aggregate**: `statistics.median` per criterion.
- **Raw scores → weighted**: `Scorer` normalizes and weights per rubric.
- **Scores → report**: `_summary.calculate_summary` + format-specific renderer.

### Exit points
- Disk: `*.json`, `*.md`, `*.html` report files (parent dirs auto-created).
- stdout/stderr: CLI output.
- Return values: `ScoringResult`, `PatternScore`, `StandardScore`, `ExecutionResult`.

---

## Integration Points

### APIs consumed
All LLM calls funnel through `LLMClientProtocol.generate_text` → `LLMClientAdapter` → `tools.llm.LLMClient` (static class method). Supported providers:
- `local:*` (ONNX), `windows-ai:*` (Phi Silica), `azure-foundry:*`, `gh:*` (GitHub Models), `gemini:*`, `claude:*`, `gpt*`.

### Filesystem writes
- `reporters/json.py`, `reporters/markdown.py`, `reporters/html.py` — output files
- `__main__.py cmd_evaluate` — optional scored JSON
- `sandbox/local.py` — temp dir scoped writes via `write_file`

### Subprocess
- `sandbox/local.py::LocalSubprocessSandbox.run_command` — `subprocess.run(..., capture_output=True, text=True, timeout=...)`

### Imports from sibling packages
| From | Target | Mode |
|------|--------|------|
| `adapters/llm_client.py` | `tools.llm.llm_client.LLMClient` | Lazy (first `generate_text`) |
| `datasets.py` | `tools.agents.benchmarks.*` | Lazy (first API call) |
| `tests/test_benchmarks.py` | `tools.agents.benchmarks.*` | Direct (`sys.path.insert`) |

### Downstream consumers
- `agentic-workflows-v2/agentic_v2/models/llm.py` — imports `LLMClientProtocol` from `agentic_v2_eval.interfaces`.

---

## Dependency Graph

```
__main__      → rubrics, scorer, reporters
__init__      → evaluators/{base,pattern,quality,standard}, interfaces, scorer
interfaces    → ∅ (leaf)
scorer        → ∅ (leaf, uses yaml)
datasets      → tools.agents.benchmarks (lazy, external)
adapters/llm_client → tools.llm (lazy, external)
evaluators/base     → ∅ (leaf)
evaluators/llm      → interfaces, evaluators/base
evaluators/pattern  → interfaces, rubrics, evaluators/base
evaluators/quality  → interfaces, rubrics, evaluators/base, evaluators/llm
evaluators/standard → interfaces, rubrics, evaluators/base
metrics/*     → ∅ (leaves)
runners/*     → ∅ (leaves)
reporters/*   → reporters/_summary
reporters/_summary → ∅ (leaf)
rubrics/__init__   → ∅ (leaf, uses yaml)
sandbox/local → sandbox/base
```

### Entry points (not imported by others in scope)
`__main__.py`, `__init__.py`, test files

### Leaf modules
`interfaces.py`, `scorer.py`, `datasets.py`, `adapters/llm_client.py`, `metrics/accuracy.py`, `metrics/quality.py`, `metrics/performance.py`, `runners/batch.py`, `runners/streaming.py`, `reporters/_summary.py`, `rubrics/__init__.py`, `sandbox/base.py`

### Circular dependencies
✓ None detected — the graph is a strict DAG.

---

## Testing Analysis

**Coverage gate:** `fail_under = 80` (branch coverage on). Actual per-module coverage requires running `pytest --cov=agentic_v2_eval --cov-report=term-missing` — not measured here.

**Test utilities:**
- `MagicMock` used extensively for LLM mocking.
- `inspect.signature` for protocol-shape compliance.
- `pytest.approx` for float comparison.
- `pytest.skip` for network-dependent tests.
- Parametrize decorator for rubric-sweep tests.

**Testing gaps:**
- `metrics/quality.py` has no dedicated test file (covered only superficially in `test_eval.py`).
- No contract test asserting `LLMClient` call-signature stability — the static-class-method assumption in `LLMClientAdapter` is masked by mock usage.
- No integration test spanning dataset → evaluator → scorer → reporter as a single run.
- Sandbox testing branches on `sys.platform` but does not exercise both in CI if CI is single-platform.

---

## Related Code & Reuse Opportunities

### Duplication with `agentic-workflows-v2`
- **LLM client wrapper:** `agentic-workflows-v2/agentic_v2/models/llm.py` defines its own `LLMClient` that wraps `tools.llm.LLMClient` and satisfies `LLMClientProtocol`. This duplicates `LLMClientAdapter` logic. **Recommendation:** consolidate on `agentic-v2-eval`'s `LLMClientAdapter` as canonical; have the runtime import it directly, eliminating maintenance split.

### Reusable patterns
- **`EvaluatorRegistry` decorator pattern** — candidate for the runtime's agent / tool registries.
- **`AsyncStreamingRunner` bounded concurrency** — tested pattern for parallel agent invocations in workflow steps.
- **`Scorer` rubric-weighted scoring** — generic enough for any cross-run comparison, not just eval.
- **`LocalSubprocessSandbox`** — no equivalent in the runtime. Useful for executing agent-generated code during workflow tasks.

---

## Implementation Notes

### Code quality observations
- Several `print()` calls on error paths where `logger` is required by repo standards: `__init__.py`, `evaluators/pattern.py` (lines ~211, ~241), `evaluators/quality.py` (`print(f"Evaluation failed: {e}")`), `evaluators/standard.py`.
- Score-extraction logic duplicated between `llm.py` and `quality.py` — extract shared helper.
- `lint_score` regex for `=` spacing is imprecise.
- Inner `src/agentic_v2_eval/README.md` has a stale import path.
- `# pragma: no cover` on an exercised branch in `runners/streaming.py` (~line 196) — remove to surface actual coverage.

### TODOs and future work
- `evaluators/standard.py:156` — "Uniform weights for now (or load from rubric in future)".
- Naming collision between `interfaces.Evaluator` and `evaluators/base.Evaluator`.

### Known issues
- `Scorer.total_score` misleading when criteria are missing — prefer `weighted_score` for cross-run comparison.
- `datasets.load_benchmark` filters applied client-side defeat `limit`.
- `LLMClientAdapter` assumes static-class-method `generate_text`.

### Optimization opportunities
- Add `@lru_cache` to `rubrics.load_rubric` for high-throughput reuse.
- Push `language`/`difficulty` filters into the dataset loader.
- Extract shared score-extraction helper to remove duplication.
- Make `max_tokens` configurable in `StandardEvaluator` (currently hard-coded 900).

### Technical debt
- `BLOCKED_COMMANDS` substring-match on fork-bomb pattern can false-positive.
- Network commands (`curl`, `wget`) blocked in safe mode without a flag to re-enable.
- Rubric YAML loaded at module import with silent fallback — violates fail-fast principle.

---

## Modification Guidance

### To add a new evaluator
1. Create `src/agentic_v2_eval/evaluators/<name>.py` with a class inheriting `Evaluator` (ABC from `evaluators/base.py`).
2. Decorate with `@EvaluatorRegistry.register("<name>")`.
3. If it needs an LLM, accept an `LLMClientProtocol` instance via constructor (DI, not import).
4. Add YAML rubric in `rubrics/` if score dimensions need configuration.
5. Re-export from `evaluators/__init__.py` and (optionally) top-level `__init__.py`.
6. Add tests in `tests/test_<name>_evaluator.py` using `MagicMock` for the LLM.

### To add a new rubric
1. Drop `<name>.yaml` in `src/agentic_v2_eval/rubrics/`. Ensure weights sum to 1.0.
2. Document criteria levels (0–5 or 0–10 per rubric convention).
3. Add to the parametrized sweep in `tests/test_rubrics.py`.
4. If the rubric is intended for CLI use, it becomes automatically available via `load_rubric("<name>")`.

### To add a new reporter
1. Create `src/agentic_v2_eval/reporters/<format>.py` with `<Format>ReportConfig` dataclass and `<Format>Reporter` class.
2. Use `_summary.calculate_summary` for aggregates.
3. Create parent dirs via `output_path.parent.mkdir(parents=True, exist_ok=True)`.
4. Re-export from `reporters/__init__.py`.
5. Add tests in `tests/test_reporters.py` (follow existing class structure).
6. Optionally wire into `__main__.cmd_report`.

### To modify `LLMClientAdapter` or the protocol
- Changes to `LLMClientProtocol.generate_text` signature require updates in both `adapters/llm_client.py` **and** `agentic-workflows-v2/agentic_v2/models/llm.py` (runtime's own wrapper).
- Run `pytest tests/test_adapters.py::TestLLMClientProtocolCompliance` to confirm `inspect.signature` match.

### To remove / deprecate
- Mark with a `# deprecated(YYYY-QN): <reason>` comment.
- Do not remove from `__init__.py` re-exports until all known consumers migrate.
- Add a `DeprecationWarning` in the symbol itself for runtime visibility.

### Testing checklist for changes
- [ ] All existing tests pass (`pytest tests/`).
- [ ] Coverage remains ≥ 80% (branch).
- [ ] `python tests/verify_p2.py` still decouples `tools` from pattern scope.
- [ ] `mypy --strict src/agentic_v2_eval` has no new errors.
- [ ] `ruff check src/` clean.
- [ ] If touching `interfaces.py` or adapters: protocol-compliance test green.
- [ ] If touching rubrics: weight-sum test green.
- [ ] If touching the LLM adapter: integration-tested against at least one real provider.

---

_Generated by `document-project` workflow (deep-dive mode)_
_Base Documentation: docs/index.md_
_Scan Date: 2026-04-18_
_Analysis Mode: Exhaustive_
