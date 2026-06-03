# Development History

> This is a retrospective record of what was built in the agentic-systems-lab repository — inferred from architectural decision records, the roadmap, and the git log. Because the history was squashed at the time of public release, commit-level granularity before the initial public release commit (`111a692`) is not recoverable from this repository. Phase dates and sequencing are derived from ADR timestamps and the v0.3.0 roadmap entry.

---

## Phase 0: Foundation

The project began as a sandbox and research companion to a separate production repository (`agentic-runtime-platform`). The founding premise was that new features, security sprints, and example code should have a home where they could be prototyped fully before any upstream promotion. Early work established the monorepo structure: a core runtime package (`agentic-workflows-v2`), a standalone evaluation framework (`agentic-v2-eval`), and shared tools under `tools/`. The YAML workflow DSL was defined early and became the single source of truth for workflow topology — a deliberate choice to keep workflow structure auditable and separate from execution logic.

### Key decisions established here

- **ADR-001** ratified a dual execution engine strategy: a native DAG executor (Kahn's topological-sort algorithm with `asyncio` wavefront parallelism) and a LangGraph adapter, held behind a common `ExecutionEngine` protocol. The intent was to converge toward a single engine over time.
- **ADR-002** described the SmartModelRouter circuit-breaker design: tier-based routing across five or more LLM providers, health-weighted selection, adaptive cooldowns, and per-provider circuit breakers.
- **ADR-003** (later superseded) specified an early composite Confidence Index gate for the deep research supervisor state machine.

Six production workflow definitions shipped as part of the foundation: `code_review`, `bug_resolution`, `fullstack_generation`, `iterative_review`, `conditional_branching`, and `test_deterministic`. Six self-contained example scripts were added alongside them, each runnable without API keys using a no-LLM placeholder mode.

---

## Phase 1: Testing Overhaul

Once the runtime was functional, an audit of the test suite revealed two simultaneous problems: approximately 95 low-value or broken tests inflating the count while providing no defect detection, and roughly 14,100 lines of critical production code with zero test coverage. **ADR-008** (dated 2026-03-02) codified the response: a four-tier Test Value Taxonomy and seven enforceable rules to prevent future degradation. The remediation was structured in phases — first removing duplicates and broken tests (the "Phase 0 cleanup" described in ADR-008), then investing in the riskiest uncovered modules. An 80% coverage gate was introduced into CI with per-package floors differentiated by blast radius. The evaluation framework (`agentic-v2-eval`) emerged from this work as a cleanly tested package with strong rubric-based scoring, multidimensional classification, and an LLM-as-judge integration.

---

## Phase 2: Observable Execution (Epic 2)

With a stable runtime and a healthier test foundation, the next arc focused on making execution visible. Before this work, the event stream between the server and the React dashboard was loosely structured Python dicts; consumers inferred field shapes by reading source. **ADR-014** (2026-04-21) replaced this with a Pydantic v2 discriminated union in `contracts/events.py`, eliminating silent field drift and inconsistent event type strings. The React UI gained a live DAG animation, a five-field step drill-down panel, and a StepNode redesign. On the observability side, **ADR-015** (2026-04-22) solved how to enforce distributional SLO signals in CI — time-to-first-span p95 and nightly streaming flake rate — by storing a rolling window directly in git rather than standing up dedicated infrastructure. A Playwright-based streaming PR gate (five executions per PR) and a 50-run nightly reliability harness were added as enforcement points.

---

## Phase 3: Engine Consolidation

The dual-engine architecture from ADR-001 carried a maintenance cost that became untenable as the platform matured: eight-plus optional packages, a dual-engine test matrix, and onboarding friction. **ADR-013** (2026-04-20) ratified what had already become true in practice — the native DAG executor satisfied all production requirements without LangGraph's Pregel layer. The LangGraph adapter was deprecated with a `DeprecationWarning` on import, and the removal milestone was set for v2.0. This consolidation eliminated behavioral divergence risk and reduced CI complexity to a single engine contract suite.

**ADR-016** (also accepted by late April 2026) addressed the related CI dependency problem: end-to-end tests had previously required a real LLM provider key. GitHub Models accessed via `GITHUB_TOKEN` was adopted as the default E2E provider, with fork-skip guards so that external contributors without a token are not blocked.

---

## Phase 4: UI Polish, Evaluation Depth, and DevEx (Epics 3, 5, 6)

The final arc of work before the v0.3.0 release bundled three epics that improved the surface people actually touch. DevEx work (Epic 3) produced a one-command Windows bootstrap script (`scripts/setup-dev.ps1`), a port guard utility, a workspace test runner, and a workflow linter. Console UI polish (Epic 5) added an ASCII StatusBadge, keyboard shortcuts via `useHotkeys`, dashboard filtering, and a full accessibility audit (skip-to-main link, focus rings, `aria-hidden` on decorative glyphs). Evaluation depth (Epic 6) introduced additive Pydantic v2 evaluation contracts, a live `tokens_30d` statistic, new dataset sample endpoints, a rubric accordion in the Evaluations view, and a three-pane Datasets browser. **ADR-017** ratified the API shape for dataset identifiers as query parameters rather than path segments.

The v0.3.0 release shipped on 2026-04-22. Epic 4 was deliberately never authored; the numbering gap is a tombstone, not an oversight.

---

## Post-Release: CI Hardening and Docs

After the release, a stabilization sprint addressed the gap between what shipped and what was honest to claim. The CI toolchain was migrated to Node 24, coverage tooling was fixed so the 80% gate actually fails at 79.93% (a precision bug had let borderline results pass), the GitHub Pages site was restyled to the ember/console design system, and documentation was refreshed to remove phantom commit references and surface the AI-assistance disclosure. Known limitations — the SLO empty-window trivial-pass, the hand-mirrored Python/TypeScript wire format, and remaining contract-drift work — were documented honestly in `docs/KNOWN_LIMITATIONS.md` rather than quietly deferred.
