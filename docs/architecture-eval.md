# Architecture: agentic-v2-eval

## Executive Summary

`agentic-v2-eval` (v0.3.0) is a rubric-driven evaluation framework for agentic workflows. It provides LLM-as-judge scoring, structural pattern evaluation (ReAct, CoVe, Reflexion, RAG), output quality metrics, batch and streaming runners with configurable concurrency, and multiple report formats (JSON, Markdown, HTML). All evaluator dependencies are injected through structural protocols, enabling deterministic unit testing without live API calls.

The package is a workspace dependency of the broader monorepo. `agentic-systems-lab-tools` supplies the `LLMClient` and is lazy-loaded at call time so that import overhead is not paid unless evaluation actually runs. Install via `pip install -e ".[dev]"` from the `agentic-v2-eval/` directory.

---

## Technology Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| Language | Python | 3.11+ |
| Build backend | hatchling | `pyproject.toml` as single config source |
| Rubric parsing | PyYAML | YAML rubric files loaded at call time |
| LLM access | agentic-systems-lab-tools (workspace dep) | Lazy-loaded via `adapters/` bridge |
| Test runner | pytest + pytest-asyncio | asyncio mode: auto |
| Coverage | pytest-cov | 80% threshold enforced in CI |
| Static analysis | mypy | `--strict` mode |
| Linting | ruff | Rules: E, F, W, I, N, UP, S, B, A, C4, SIM, TCH, RUF |

---

## Architecture Pattern

### Plugin Registry + Protocol-Based Dependency Injection

Evaluators are registered in a central `EvaluatorRegistry` keyed by string name. Callers request an evaluator by name; the registry resolves and returns the concrete instance. New evaluator types can be added without touching any runner or reporter code.

All evaluators depend on `LLMClientProtocol`, a structural protocol defined in `interfaces.py`. The concrete `LLMClient` from `agentic-systems-lab-tools` satisfies this protocol at runtime. Tests inject a mock that also satisfies the protocol, ensuring no real API calls are made in the test suite.

Rubrics are loaded from YAML files at call time, not at import time. This keeps evaluator classes free of file-system state and makes rubric substitution trivial at the CLI level.

---

## Package Structure

```
src/agentic_v2_eval/
├── evaluators/
│   ├── base.py          # Abstract Evaluator base class
│   ├── llm.py           # LLMEvaluator — choice-anchored LLM judge
│   ├── pattern.py       # PatternEvaluator — agentic pattern conformance
│   ├── quality.py       # QualityEvaluator — output quality dimensions
│   └── standard.py      # StandardEvaluator — prompt quality grading
├── metrics/
│   ├── accuracy.py      # accuracy, precision, recall, F1, confusion matrix
│   ├── performance.py   # execution_time, memory_usage, throughput, latency_percentiles
│   └── quality.py       # code_quality (AST), lint_score, complexity_score
├── reporters/
│   ├── json.py          # JsonReporter
│   ├── markdown.py      # MarkdownReporter
│   └── html.py          # HtmlReporter (self-contained, embedded CSS)
├── runners/
│   ├── batch.py         # BatchRunner — sync, sequential, generic T/R
│   └── streaming.py     # StreamingRunner + AsyncStreamingRunner
├── rubrics/             # 8 YAML rubric definition files
│   ├── default.yaml
│   ├── agent.yaml
│   ├── code.yaml
│   ├── coding_standards.yaml
│   ├── pattern.yaml
│   ├── quality.yaml
│   ├── prompt_standard.yaml
│   └── prompt_pattern.yaml
├── sandbox/
│   ├── base.py          # BaseSandbox abstract class
│   └── local.py         # LocalSubprocessSandbox with safe_mode
├── adapters/
│   └── llm_client.py    # Bridge to agentic-systems-lab-tools LLMClient (lazy-loaded)
├── interfaces.py        # LLMClientProtocol, Evaluator protocols
├── scorer.py            # YAML-rubric weighted scoring engine
├── datasets.py          # Lazy bridge to tools.agents.benchmarks
└── __main__.py          # CLI entry point: evaluate, report
```

---

## Evaluator System

The `EvaluatorRegistry` holds four built-in evaluator types. Each is registered by a string key and resolved by name at runtime.

### LLMEvaluator

**Strategy:** Choice-anchored LLM-as-judge on a 5-point discrete scale.

- **Scale values:** 0, 0.25, 0.5, 0.75, 1.0
- **Default judge model:** `gh:gpt-4o`
- **Score extraction:** The judge prompt instructs the model to end its response with a bare numeric score on a new line. The evaluator reads the **last line** of the response and matches it against the five allowed values. Any deviation raises a parse error — there is no silent fallback to zero.
- **Use case:** General-purpose rubric-driven scoring where human-proxy judgment is needed.

### PatternEvaluator

**Strategy:** Structural conformance scoring for agentic prompt patterns.

- **Supported patterns:** ReAct, CoVe (Chain-of-Verification), Reflexion, RAG
- **Score structure:** `PatternScore` dataclass with 17 fields covering 7 universal dimensions and up to 3 pattern-specific dimensions per pattern type.
- **Variance reduction:** The evaluator runs the same prompt 20 times and reports the **median** score across runs to smooth stochastic LLM output.
- **Hard gates:** Four pre-conditions must all be met before the weighted score is computed. Failing any gate produces an immediate overall failure regardless of weighted score.

| Gate | Minimum | Meaning |
|------|---------|---------|
| POI (Pattern Observability Index) | 4 | Pattern structure must be detectable in the output |
| PC (Pattern Completeness) | 4 | All required pattern steps must be present |
| CA (Criterion Adherence) | 4 | The LLM followed the criterion instructions |
| PR (Pattern Ratio) | 0.75 | At least 75% of pattern-specific dimensions must pass |

- **Use case:** Verifying that agentic outputs adhere to a defined reasoning pattern.

### QualityEvaluator

**Strategy:** Five independent LLM judge calls, one per quality dimension.

| Dimension | Description |
|-----------|-------------|
| Coherence | Logical consistency and flow across the output |
| Fluency | Grammatical correctness and natural language quality |
| Relevance | On-topic alignment with the input prompt |
| Groundedness | Claims supported by provided context or evidence |
| Similarity | Semantic overlap with a reference output (if provided) |

- Each dimension is scored by a separate LLM call using the rubric definitions in `quality.yaml`.
- **Use case:** Output quality assessment independent of task correctness.

### StandardEvaluator

**Strategy:** Five prompt-quality dimensions scored 0–10, with letter grade and pass/fail determination.

| Dimension | Scale |
|-----------|-------|
| Clarity | 0–10 |
| Effectiveness | 0–10 |
| Structure | 0–10 |
| Specificity | 0–10 |
| Completeness | 0–10 |

- **Overall score:** Unweighted mean of the five dimension scores.
- **Grade mapping:** A (≥ 9.0), B (≥ 8.0), C (≥ 7.0), D (≥ 6.0), F (< 6.0)
- **Pass threshold:** overall_score ≥ 7.0
- **Use case:** Prompt engineering quality review and grading of prompt templates.

---

## Rubric System

All eight rubric files reside in `src/agentic_v2_eval/rubrics/`. Each criterion specifies a `weight` and optional `description`. The sum of weights within each rubric equals 1.0.

| Rubric File | Criteria | Purpose | Pass Threshold |
|-------------|----------|---------|----------------|
| `default.yaml` | 3 | General (Accuracy 0.5, Completeness 0.3, Efficiency 0.2) | — |
| `agent.yaml` | 6 | Scoring agent workflow outputs | 0.70 |
| `code.yaml` | 5 | Scoring code generation quality | 0.75 |
| `pattern.yaml` | 6 | Agentic pattern adherence with hard gates | 0.75 |
| `coding_standards.yaml` | 8 | Python/ML coding standards conformance | 0.70 |
| `quality.yaml` | 5 | LLM judge dimension definitions for QualityEvaluator | — |
| `prompt_standard.yaml` | 5 | Judge prompt definitions for StandardEvaluator | — |
| `prompt_pattern.yaml` | 4 | Judge prompts for ReAct/CoVe/Reflexion/RAG patterns | — |

### Hard Gates (pattern.yaml)

Hard gates are evaluated as binary pre-conditions before weighted scoring begins. If any gate fails the overall result is marked failed regardless of the weighted score.

| Gate | Minimum Value | Meaning |
|------|--------------|---------|
| POI | 4 | Pattern structure is observable in the output |
| PC | 4 | All required pattern steps are present |
| CA | 4 | The output adhered to criterion instructions |
| PR | 0.75 | ≥ 75% of pattern-specific dimensions passed |

---

## Scoring Engine (scorer.py)

The `Scorer` class loads a YAML rubric and computes both raw and weighted scores.

```python
@dataclass
class Criterion:
    name: str
    weight: float
    description: str
    min_score: float = 0.0
    max_score: float = 1.0

@dataclass
class ScoringResult:
    criteria_scores: dict[str, float]
    total_score: float         # unweighted mean
    weighted_score: float      # sum(score * weight) — range [0, 1]
    passed: bool               # weighted_score >= rubric pass_threshold
```

Rubric files are loaded at call time, not at module import, keeping the scorer stateless. Multiple rubrics can be applied to the same result set in a single run by passing different `--rubric` arguments.

---

## Runners

All runners are generic over `T` (input type) and `R` (result type).

| Runner | Mode | Concurrency | Result Order | Use Case |
|--------|------|-------------|--------------|----------|
| `BatchRunner[T, R]` | Synchronous | Sequential | Submission order | CI pipelines; finite input list, all results needed before reporting |
| `StreamingRunner[T, R]` | Synchronous iterator | Sequential | Submission order | Terminal progress display; no async overhead required |
| `AsyncStreamingRunner[T, R]` | Asynchronous | `asyncio.Semaphore(max_concurrency=5)` | Completion order (`FIRST_COMPLETED`) | I/O-bound scoring; up to 5 concurrent LLM evaluations in flight |

**BatchRunner** exposes a `continue_on_error: bool` flag. When `True`, per-item errors are recorded in the result without halting the batch.

**AsyncStreamingRunner** uses `FIRST_COMPLETED` wait strategy so results are yielded as each evaluation finishes rather than in the order they were submitted.

---

## Reporters

All three reporters share a `calculate_summary()` utility function and accept configurable options at construction time.

| Reporter | Output Format | Notes |
|----------|--------------|-------|
| `JsonReporter` | `.json` | Structured output suitable for downstream automation |
| `MarkdownReporter` | `.md` | Human-readable tables suitable for PR comments or GitHub Wiki |
| `HtmlReporter` | `.html` | Self-contained file with embedded CSS; no external assets required |

Both class-based (`reporter.generate(results)`) and functional (`generate_json_report(results)`) interfaces are available for all three formats.

---

## Metrics

### accuracy.py

- `accuracy(y_true, y_pred)` — standard classification accuracy
- `precision_recall_f1(y_true, y_pred)` — macro-averaged precision, recall, F1
- `confusion_matrix(y_true, y_pred)` — raw confusion matrix as nested list

### performance.py

- `execution_time(fn)` — decorator that records wall-clock elapsed time
- `memory_usage(fn)` — decorator using `tracemalloc` to measure peak memory
- `throughput(count, elapsed_s)` — items per second
- `benchmark(fn, n_runs)` — aggregate min/mean/max over n_runs
- `latency_percentiles(samples, percentiles)` — P50/P95/P99 from a list of latency samples

### quality.py (metrics)

- `code_quality(source)` — AST-based static analysis returning a normalized score
- `lint_score(source)` — invokes ruff programmatically and returns a pass-rate score
- `complexity_score(source)` — cyclomatic complexity via AST visitor

---

## Sandbox

`LocalSubprocessSandbox` executes evaluated code in an isolated subprocess.

| Property | Value |
|----------|-------|
| Default timeout | 30 seconds |
| Safe mode | Enabled by default |
| Blocked commands (safe_mode) | 24 commands including `rm`, `wget`, `curl`, `nc`, `kill`, `chmod`, `chown`, `dd`, `mkfs`, and additional destructive/network commands |
| Path escape prevention | Absolute paths outside the sandbox root are rejected before execution |

The sandbox provides subprocess-level guardrails only. It does not offer container-level isolation. For higher assurance, wrap the evaluator in a container image.

---

## Adapters

`adapters/llm_client.py` provides a lazy-loading bridge to `agentic-systems-lab-tools`. The import of `LLMClient` from `tools.llm.llm_client` is deferred until the first evaluation call. This means the `agentic-v2-eval` package can be imported without `agentic-systems-lab-tools` installed, enabling lighter-weight test environments that mock `LLMClientProtocol` directly.

---

## CLI Reference

The CLI is the `__main__.py` entry point, registered as the `agentic-v2-eval` console script.

```bash
# Score a results file against a rubric
agentic-v2-eval evaluate results.json [--rubric rubric.yaml] [--output scored.json]

# Generate a formatted report from scored results
agentic-v2-eval report results.json --format {json,markdown,html} --output out_file
```

### evaluate arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `results.json` | Yes | — | JSON file containing LLM outputs to evaluate |
| `--rubric` | No | `default.yaml` | Path to a YAML rubric file |
| `--output` | No | `scored.json` | Output path for scored results |

### report arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `results.json` | Yes | — | Scored results file (output of `evaluate`) |
| `--format` | Yes | — | One of `json`, `markdown`, `html` |
| `--output` | Yes | — | Output file path |

---

## Public API

The package exports 16 symbols from its top-level `__init__.py`.

| Symbol | Type | Description |
|--------|------|-------------|
| `COHERENCE` | Constant | Quality dimension identifier for Coherence |
| `FLUENCY` | Constant | Quality dimension identifier for Fluency |
| `GROUNDEDNESS` | Constant | Quality dimension identifier for Groundedness |
| `RELEVANCE` | Constant | Quality dimension identifier for Relevance |
| `SIMILARITY` | Constant | Quality dimension identifier for Similarity |
| `Evaluator` | Protocol | Base structural protocol for all evaluators |
| `EvaluatorRegistry` | Class | Plugin registry mapping names to evaluator instances |
| `LLMClientProtocol` | Protocol | Structural protocol satisfied by `LLMClient` and test mocks |
| `LLMEvaluatorDefinition` | Dataclass | Configuration for an `LLMEvaluator` instance |
| `PatternEvaluator` | Class | Evaluator for agentic pattern conformance |
| `PatternScore` | Dataclass | 17-field score result for pattern evaluation |
| `QualityEvaluator` | Class | Evaluator for five output quality dimensions |
| `Scorer` | Class | YAML-rubric weighted scoring engine |
| `ScoringResult` | Dataclass | Result of a `Scorer.score()` call |
| `StandardEvaluator` | Class | Evaluator for prompt engineering quality |
| `StandardScore` | Dataclass | Scored result from `StandardEvaluator` |

---

## Testing

| Property | Value |
|----------|-------|
| Test files | 11 |
| Approximate test count | ~215 |
| asyncio mode | auto (pytest-asyncio) |
| Coverage gate | 80% (enforced in CI) |
| Live API calls | None — all tests mock `LLMClientProtocol` |
| Test markers | `integration` (skipped in fast mode), `slow` |

```bash
cd agentic-v2-eval
pip install -e ".[dev]"
python -m pytest tests/ -v
python -m pytest tests/ --cov=agentic_v2_eval --cov-report=term-missing
```

Static analysis:

```bash
mypy --strict src/agentic_v2_eval/
ruff check src/agentic_v2_eval/
```

All function signatures and class attributes must carry type annotations. `mypy --strict` enforces this in CI and blocks merge on violations.
