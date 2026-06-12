# Contributing to `tafreeman/agentic-systems-lab`

> **Audience:** Anyone landing their first PR on this monorepo.
> **Outcome:** After reading this, you can clone, change code, pass local gates, and open a merge-ready PR.
> **Last verified:** 2026-06-11

If you just want to run the platform, start at [`docs/ONBOARDING.md`](docs/ONBOARDING.md) — it takes ~5 minutes to a first workflow run. This file is for contributors who intend to land code.

---

## 1. What lives in this repo

| Path | What it is | Build backend | Notes |
|------|-----------|---------------|-------|
| `agentic-workflows-v2/` | Runtime (CLI, DAG executor, LangGraph adapter, FastAPI server, WebSocket streaming) | hatchling | Python 3.11+ |
| `agentic-workflows-v2/ui/` | React 19 dashboard (Vite 6, Tailwind, @xyflow/react) | Vite | Node 20+ |
| `agentic-v2-eval/` | Rubric-based evaluation framework | hatchling | Python 3.11+ |
| `tools/` | Shared LLM client, benchmarks, caching utilities (package name: `agentic-systems-lab-tools`) | setuptools | Python 3.10+ |

Each Python package installs independently. There are **zero cross-package imports** — `tools` is the only optional shared surface, imported with `from tools.llm import LLMClient`.

Package-specific contribution notes live at [`agentic-workflows-v2/CONTRIBUTING.md`](agentic-workflows-v2/CONTRIBUTING.md). This root document covers monorepo-wide policy.

---

## 2. Local setup

```bash
git clone https://github.com/tafreeman/agentic-systems-lab.git
cd agentic-systems-lab
just setup          # installs root helpers + all three Python packages + UI deps
```

`just setup` wraps the individual `pip install -e` and `npm install` steps so every contributor ends up with the same environment. If `just` is not on your PATH, install it (`winget install casey.just` on Windows, `brew install just` on macOS) or run the equivalent commands manually — see `justfile` for the exact wrapping.

If you prefer a containerized workspace, open the repo in the provided devcontainer (`.devcontainer/`) — it installs everything at build time.

### Provider credentials

At least one LLM provider must be configured before any non-deterministic workflow will run:

```bash
cp .env.example .env
# edit .env and set ONE of:
#   GITHUB_TOKEN=ghp_…        (free tier, used by CI)
#   GEMINI_API_KEY=…          (free tier)
#   OPENAI_API_KEY=…          (paid)
#   ANTHROPIC_API_KEY=…       (paid)
```

The smart router will use whichever providers are configured. CI uses `GITHUB_TOKEN` with GitHub Models — see [`docs/adr/ADR-016-github-token-as-default-e2e-llm.md`](docs/adr/ADR-016-github-token-as-default-e2e-llm.md) for the trade-off that drove that choice.

---

## 3. Development workflow

1. Create a branch from `main`. Branch naming: `feature/…`, `fix/…`, `chore/…`, `docs/…`.
2. Make the smallest coherent change. Prefer one concern per PR.
3. Write tests first (TDD). New backend code targets 80% coverage on changed lines; the UI package enforces a 60% floor in `ui/vitest.config.ts`.
4. Update the docs in the same PR if the change touches user-facing behavior, configuration, or a new pattern. See the [documentation mapping](#7-documentation) below.
5. Run local gates before pushing (next section).
6. Push with `-u` on first push and open a PR against `main`.

Do not push directly to `main`. All changes land via PR.

---

## 4. Required local gates

These must all pass before a PR will merge. Run them from the repo root:

```bash
just test                     # runs the full backend + eval + UI test suite
just docs                     # verifies documentation (links, code fences, etc.)
pre-commit run --all-files    # black, isort, ruff, docformatter, mypy, pydocstyle, detect-secrets
```

### Per-package test entrypoints

If you only touched one package, you can narrow the run:

| Package | Command |
|---------|---------|
| Runtime | `cd agentic-workflows-v2 && python -m pytest tests/ -q` |
| Runtime + coverage | `cd agentic-workflows-v2 && python -m pytest tests/ -q --cov=agentic_v2 --cov-report=term-missing` |
| Eval | `cd agentic-v2-eval && python -m pytest tests/ -q` |
| UI unit | `cd agentic-workflows-v2/ui && npm test` |
| UI coverage | `cd agentic-workflows-v2/ui && npm run test:coverage` |
| UI build check | `cd agentic-workflows-v2/ui && npm run build` |

### CI gates you must not break

| Gate | What it enforces | Source |
|------|------------------|--------|
| Ruff lint | `E,F,W,I,N,UP,S,B,A,C4,SIM,TCH,RUF` — no warnings in changed files | `.github/workflows/ci.yml` |
| Mypy | `mypy --strict` on `agentic-workflows-v2/agentic_v2/`. `agentic-v2-eval` runs with 35 known findings (Sprint B) — see [`KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md). Note: mypy config is relaxed while type debt is being paid down (see `pyproject.toml` `[tool.mypy]`). | `ci.yml`, `eval-package-ci.yml` |
| Coverage floor | 80% on `agentic-workflows-v2/`, 60% on `ui/` | `ci.yml` |
| Schema drift | Snapshot test on `contracts/` Pydantic models — any wire-format change must be explicitly accepted by regenerating the snapshot | `scripts/generate_schemas.py`, see [ADR-014](docs/adr/ADR-014-pydantic-wire-format.md) |
| Playwright streaming (5×) | End-to-end streaming flow runs 5× per PR. One failure blocks merge | `ci.yml` |
| Nightly reliability (50×) | Rolling flake-rate gate over 50 runs. Failure blocks a release cut, not a PR | `nightly.yml` |
| Time-to-first-span p95 | SLO gate on trace latency — see [ADR-015](docs/adr/ADR-015-slo-in-git-rolling-window.md) for the git-as-time-series pattern | `nightly.yml` |
| pip-audit | No High/Critical advisories | `dependency-review.yml` |
| detect-secrets | Baseline-driven — see `.secrets.baseline` | pre-commit |

Full CI job catalogue: [`.github/workflows/`](.github/workflows/).

> **mypy enforcement scope:** The badge says "type checked: mypy" but enforcement is not yet strict — `disallow_untyped_defs = false` and several modules (tools/builtin, integrations/mcp, integrations/tracing, langchain.*) carry `ignore_errors = true` overrides while pre-existing type debt is being paid down. The ratchet plan is captured in `agentic-workflows-v2/pyproject.toml` under `[tool.mypy]` TODO comments; each Sprint C task removes one override block as that module's types are cleaned up.

---

## 5. Commit format

Conventional commits. Enforced by review, not by hook.

```
<type>(<scope>): <subject>

<optional body>
```

| Type | Use for |
|------|--------|
| `feat` | New user-facing behavior |
| `fix` | Bug fix |
| `refactor` | No behavior change |
| `test` | Tests only |
| `docs` | Documentation only |
| `chore` | Tooling, CI, dependency bumps |
| `perf` | Performance improvement with benchmark evidence |
| `ci` | CI pipeline changes |
| `style` | Formatting only (rare — pre-commit handles this) |
| `wip` | Reserved for draft commits on feature branches — **squash before merge** |

Scopes match the package or subsystem: `contracts`, `ui`, `server`, `engine`, `eval`, `rag`, `ci`, `slo`, `mcp/results`, etc. Read the last 40 commits on `main` (`git log --oneline -40`) to calibrate tone — terse, specific, present tense.

Attribution (`Co-Authored-By`) is intentionally disabled for this repo. Do not re-enable it.

---

## 6. When to write an ADR

Open an Architecture Decision Record under [`docs/adr/`](docs/adr/) when you:

- Introduce a new wire-format contract (request/response schema, event shape, persistence format).
- Add, replace, or deprecate an execution engine, provider adapter, or storage backend.
- Change a security boundary (tool allowlist, secret source, auth model).
- Pick a pattern that future contributors might reasonably challenge (a new rolling-window design, a retry strategy, an SLO methodology).

Use the existing ADR numbering scheme. Next free number is **017** as of 2026-04-22. Skip to the next free integer if you land in a race. ADRs 004-006 are deliberately unused and **should not be reclaimed** — the numbering gap is documented in [`docs/adr/ADR-INDEX.md`](docs/adr/ADR-INDEX.md).

An ADR is **not** required for:

- Bug fixes, refactors, or test additions.
- UI polish that doesn't change contracts.
- New workflows, personas, or tools that use existing patterns.
- Pre-commit or lint rule tweaks.

If in doubt, propose the ADR as a stub in the PR and let the reviewer decide.

---

## 7. Documentation

Docs live close to what they describe. The mapping for changes:

| Change | Update |
|--------|--------|
| New or modified workflow | [`docs/WORKFLOW_AUTHORING.md`](docs/WORKFLOW_AUTHORING.md) |
| New environment variable | Root [`README.md`](README.md), [`.env.example`](.env.example), [`docs/ONBOARDING.md`](docs/ONBOARDING.md) |
| New REST or WebSocket endpoint | [`docs/api-contracts-runtime.md`](docs/api-contracts-runtime.md) |
| New architecture pattern | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (umbrella) + relevant `docs/architecture-*.md` |
| New bootstrap / devcontainer behavior | Root `README.md`, `docs/ONBOARDING.md`, this file |
| User-visible change (per release) | `CHANGELOG.md` under `## [Unreleased]` |
| Breaking or migration-worthy change | [`docs/MIGRATIONS.md`](docs/MIGRATIONS.md) |
| Known limitation or temporary defect | [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md) |
| Proposed epic or major initiative | [`docs/ROADMAP.md`](docs/ROADMAP.md) |

Docs must be runnable or falsifiable. Command blocks must actually work. Diagrams use Mermaid. Every top-level doc carries a "last verified" date — update it when the doc is touched.

---

## 8. Runtime artifact hygiene

Several directories and files produced at runtime are **never** committed. They are excluded by root `.gitignore` rules. Do not stage or force-add them.

| Artifact family | Gitignore pattern | Why it must stay out |
|---|---|---|
| `runs/` — workflow-run JSON logs | `/runs/` (line ~359) | Contains LLM inputs/outputs and may hold PII or sensitive prompts |
| `agentic-workflows-v2/runs/` — same, under the sub-package | `runs/` in `agentic-workflows-v2/.gitignore` | Same as above |
| `.agentic_memory.json` | `.agentic_memory.json` (root `.gitignore`) | Agent-session state; may contain workspace-local secrets or paths |
| `tools/llm/windows_ai_bridge/bin/` and `obj/` | `[Bb]in/` / `[Oo]bj/` (lines ~37-38) | .NET build output; binary artifacts should never enter the tree |

### Verification commands

```bash
# Confirm no run logs are tracked
git ls-files runs/ agentic-workflows-v2/runs/

# Confirm all three families are ignored
git check-ignore -v runs/ .agentic_memory.json \
  agentic-workflows-v2/runs/ agentic-workflows-v2/.agentic_memory.json \
  tools/llm/windows_ai_bridge/bin tools/llm/windows_ai_bridge/obj
```

Both commands should produce no output / only gitignore-rule lines respectively. If a pattern is missing for a new artifact family, add it to the appropriate `.gitignore` **in the same PR** as the feature that produces the artifact.

### PR checklist addition

Add this item to your PR description when you add a feature that writes files at runtime:

```markdown
- [ ] New runtime output paths are covered by .gitignore (verified with `git check-ignore -v`)
```

---

## 9. Security

- Never commit secrets, API keys, or production tokens. `.env` is gitignored; `.env.example` is the only committed template.
- Resolve runtime secrets through `agentic_v2.models.secrets.get_secret()` / `get_first_secret()` — not `os.environ` directly.
- Follow the disclosure process in [`SECURITY.md`](agentic-workflows-v2/SECURITY.md) for any vulnerability report.
- AI-generated code is untrusted input — run full lint + type check + tests before accepting.

---

## 10. AI-assisted development

This is a research lab, and parts of it were built with AI-assisted tooling (LLM coding assistants) under human review. We disclose this openly rather than hide it.

- **Human ownership.** Every change — AI-assisted or hand-written — is owned by the contributor who opens the PR. You are accountable for what you submit: you must understand it, be able to explain it, and stand behind its correctness and licensing.
- **AI output is untrusted input.** Consistent with §9, treat anything an assistant generates as a draft to be verified, not trusted code. It passes the same gates as everything else — lint, types, tests, coverage, and review (CONTRIBUTING §4) — before it lands.
- **No lowered bar.** AI assistance is not a justification for skipping tests, ADRs, or docs. The review standard is identical regardless of how the code was produced.
- **Disclosure.** If a change is substantially AI-generated, a one-line note in the PR description is welcome (not required) so reviewers can calibrate scrutiny.

---

## 11. Need help

- Open a discussion or issue on the repository.
- Read [`docs/GLOSSARY.md`](docs/GLOSSARY.md) for domain terms.
- Support channels and response expectations: [`SUPPORT.md`](SUPPORT.md).
- For architecture questions, start at [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and the ADRs.

---

## 12. PR checklist

Copy into your PR description:

```markdown
- [ ] Branch from main; name follows `feature|fix|chore|docs/…`
- [ ] Tests added or updated; coverage holds on changed lines
- [ ] `just test && just docs && pre-commit run --all-files` green locally
- [ ] CHANGELOG.md [Unreleased] updated for user-visible changes
- [ ] ADR added (or confirmed not required — see CONTRIBUTING §6)
- [ ] Docs updated per CONTRIBUTING §7 table
- [ ] No secrets, no `.env` committed
- [ ] New runtime output paths (if any) added to .gitignore — see CONTRIBUTING §8
- [ ] Commit message follows conventional format
```
