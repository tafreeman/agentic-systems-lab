# Roadmap

> **Audience:** Contributors, reviewers, and stakeholders asking "what shipped, what's next, and why is Epic 4 missing?"
> **Outcome:** After reading, you can answer "is this in scope this quarter?" without asking a human.
> **Last verified:** 2026-04-22

This is the in-repo backlog. Day-to-day sprint tracking lives in issues; this file captures the load-bearing multi-week arcs. If you are about to propose a new initiative, add a stub under **Proposed** and open a PR for review — a roadmap entry without a PR is aspiration.

---

## 1. Shipped in April 2026 (v0.3.0)

v0.3.0 bundles five epics completed between 2026-04-01 and 2026-04-22. Full change lists are in [`CHANGELOG.md`](../CHANGELOG.md) under `[0.3.0]`.

| Epic | Theme | Headline |
|------|-------|----------|
| **1** | Platform Foundation | Typed protocols, consolidated settings, schema-drift CI gate, golden-output regression, OTEL parent-child trace assertion, CI ruff + 80% coverage enforcement. |
| **2** | Observable Execution | Typed event wire format, live DAG animation, StepNode B2 redesign, 5-field drill-down, Playwright streaming PR gate (5×), reconnect-replay test, time-to-first-span SLO + p95 gate, nightly 50× reliability. |
| **3** | DevEx / Windows | `scripts/setup-dev.ps1` one-command bootstrap, `port-guard`, `workspace-test-runner`, `workflow-linter`, Windows Unicode CLI fix. |
| **5** | Console UI Polish | ASCII StatusBadge, `useHotkeys`, dashboard filter, empty/error/404 states, skip-to-main link, focus ring audit, paper-theme contrast QA, `BDagMini` SVG thumbnail. |
| **6** | Evaluation & Data Depth | Additive Pydantic v2 evaluation contracts, `tokens_30d` live stat, `GET /runs/{filename}/evaluation`, dataset sample endpoints, Evaluations rubric accordion, Datasets 3-pane browser. |

Implementation history is summarized below without carrying internal planning artifacts. Epics 3, 5, and 6 did not have formal pre-implementation plans; retrospective notes are summarized in the epic entries.





### The Epic 4 question

**There is no Epic 4.** The epic numbering jumps from Epic 3 to Epic 5 intentionally — no story, plan, commit, branch, or changelog entry uses the label "Epic 4" in this repository. The number was allocated during planning but never authored.

This is a **tombstone**, not a gap: do not retroactively renumber 5/6 down to 4/5, and do not reclaim "Epic 4" for a future initiative. Future epics continue from Epic 7.

*Verification:* `git log --all --grep="epic.4" -i` returns zero matches as of 2026-04-22. A repo-wide grep of source + docs returns the same.

---

## 2. In flight (Sprint B — targeted 2026-04-29 → 2026-05-10)

Sprint B is stabilization, not new capability. These items unblock a clean v0.3.1 point release.

| Item | Owner | Target |
|------|-------|--------|
| **Unmask 35 mypy findings in `agentic-v2-eval/`** — the eval package currently runs mypy with exemptions; cut that list to zero. | unassigned | Sprint B |
| **Fix SLO p95 empty-window trivial-pass** — time-to-first-span gate should require ≥ N samples before it declares "pass". See [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md). | unassigned | Sprint B |
| **Automate Python ↔ TypeScript wire-format drift detection** — today the `contracts/events.py` union and `ui/src/api/types.ts` are mirrored by hand. Add a generator or diff test. | unassigned | Sprint B |
| **Dataset sample endpoint API polish** — revisit query-param-for-slash-handling after we see real usage; possibly move to path-param with escaping. | unassigned | Sprint B |
| **Placeholder / no-LLM CI mode** — currently CI depends on `GITHUB_TOKEN` + GitHub Models; a no-network mode would allow contributions from contributors without a token. | unassigned | Sprint B or later |

None of these block v0.3.0 release; all are honest accounting of debt taken on to ship.

---

## 3. Proposed (Epic 7+)

### Epic 7 — First-Run Experience

**Problem statement:** A contributor landing on this repo cannot reliably go from `git clone` to "I understand this and ran a workflow" in under 30 minutes without reading source code. The documentation work bundled in this docs sprint closes a significant portion of that gap, but does not ship the polish:

- Self-contained no-LLM demo path (`test_deterministic` exists but is not surfaced as the recommended first step).
- Dashboard "Hello World" tile on first run — show the user *something* without requiring them to craft a JSON input file.
- Better error messages when no provider key is set (current behavior: cryptic router failure deep in a call stack).
- Devcontainer validation in CI (exists but not yet a PR gate).

**Definition of done:**

- A contributor with no prior context completes `docs/ONBOARDING.md` Quick Start in < 10 minutes on a fresh Windows or Ubuntu clone.
- `agentic run test_deterministic` succeeds with no environment variables set, producing clear output explaining the zero-LLM path.
- The dashboard ships with a default guide panel that walks through the first run in < 3 clicks.
- Devcontainer builds on every PR touching `.devcontainer/`.

**Target:** Not yet scheduled. Sprint B first.

### Epic 8 — Production Readiness Pack (candidate)

**Problem statement:** This platform claims enterprise-grade practices for production-grade environments. Remaining gaps before that claim holds end-to-end: authentication on the API server, tenant isolation, an audit log that is *actually* immutable (current logs are structured but file-based), and a supply-chain story for model weights.

**Status:** Candidate only. Needs scoping before it becomes an epic.

### Epic 9 — Multi-Run Comparison (candidate)

**Problem statement:** Today the UI shows one run at a time. A frequent workflow during evaluation is comparing two or three runs side by side — same workflow, different prompts or adapters — to spot regressions. Some primitives exist (`agentic compare`, ADR-012 UI Evaluation Hub proposed), but the full comparison UX has not been built.

**Status:** Partially proposed in [ADR-012](adr/ADR-012-ui-evaluation-hub.md). Consolidate into an epic if prioritized.

---

## 4. Out of scope for v0.3.x

Flagged here so nobody quietly adds them to a sprint:

- **Presentation / deck system** - extracted to a separate repository on 2026-04-22. See [`MIGRATIONS.md`](MIGRATIONS.md). Not returning to this repo.
- **Cross-language agent workers** — this runtime is Python. Polyglot agents are intentionally deferred.
- **Multi-tenant billing / quotas** — scope for Epic 8 candidate only if it is promoted.

---

## 5. How to propose new work

1. Open a PR that adds a subsection under §3 (Proposed). Include: problem statement, definition of done, rough sizing (story-weeks), open questions.
2. If the work crosses an architectural boundary — new engine, new contract, new security surface — write an ADR under [`adr/`](adr/) at the same time (see [`../CONTRIBUTING.md`](../CONTRIBUTING.md#6-when-to-write-an-adr)).
3. Once an epic is accepted for sprint, move its entry to §2 (In flight) and add a concise implementation note to the epic entry.
4. When the epic ships, move its entry to §1 with the release it landed in.

An accepted roadmap entry is a promise to a reviewer, not to a user — shipping dates slip, scope narrows. Update the entry when reality changes.
