# Known Limitations

> **Audience:** Operators, auditors, and contributors reading failing CI or trying to understand why something "works but not quite."
> **Outcome:** After reading, you know what is intentionally unfinished in v0.3.0 and what Sprint B is expected to address.
> **Last verified:** 2026-04-22

This is an honest accounting. Every item here is real, reproducible, and has shipped into the current release. Nothing here is a guess. If you find a new limitation, add it — do not paper over it elsewhere.

Each item includes a **Status** (reflecting how we're treating it today) and an **Upstream fix** field pointing at the Sprint B ticket, workaround, or follow-up.

---

## 1. Typed gates that are not fully enforced

### 1.1 35 mypy findings in `agentic-v2-eval/`

The eval package runs `mypy` with carve-outs because 35 strict-mode findings accumulated during Epic 6 and were not cleared before the release cut. The backend runtime (`agentic-workflows-v2/agentic_v2/`) runs with `mypy --strict` fully enforced.

- **Surface:** CI job `eval-package-ci.yml` runs mypy with a mask.
- **Risk:** Type-level regressions in `agentic-v2-eval` will not fail CI.
- **Workaround:** Run `cd agentic-v2-eval && mypy --strict src/agentic_v2_eval/` locally before landing changes there.
- **Status:** Accepted debt for v0.3.0.
- **Upstream fix:** Sprint B — see [`ROADMAP.md`](ROADMAP.md) §2.

### 1.2 SLO p95 gate passes trivially on an empty window

The time-to-first-span p95 gate reads a rolling window of measurements stored in git (see [ADR-015](adr/ADR-015-slo-in-git-rolling-window.md)). If the window is empty — first run in a new branch, or after a window reset — the p95 computation returns a passing value by default instead of failing closed.

- **Surface:** `nightly.yml` + the SLO gate job.
- **Risk:** A branch can appear to "pass SLO" without actually having measured anything.
- **Workaround:** Check the SLO artifact directly — if it shows `samples: 0`, treat it as *not passing*.
- **Status:** Known; intentionally deferred so v0.3.0 can ship.
- **Upstream fix:** Sprint B — require ≥ N samples before the gate can declare pass.

### 1.3 Python ↔ TypeScript wire format is manually mirrored

`agentic_v2/contracts/events.py` defines the execution-event discriminated union in Python; `ui/src/api/types.ts` mirrors it by hand. Drift is caught by reviewer eyeball, not by automation.

- **Surface:** Any new event field requires an edit in both files.
- **Risk:** Silent shape mismatches between backend emit and frontend decode. Recent example avoided by review only.
- **Workaround:** When editing `contracts/events.py`, grep `ui/src/api/types.ts` for the event name and update in the same PR.
- **Status:** Ratified as manual in [ADR-014](adr/ADR-014-pydantic-wire-format.md); drift detection is documented-only.
- **Upstream fix:** Sprint B — add a generator or diff test.

---

## 2. API quirks

### 2.1 Dataset sample endpoints use query params for `dataset_id`

`GET /eval/datasets/sample-list?dataset_id=…&limit=…` and `GET /eval/datasets/sample-detail?dataset_id=…&sample_index=…` take the dataset ID as a query parameter rather than a path parameter. The reason: dataset IDs can contain slashes (e.g., `huggingface/swe-bench`), and path-based routing would require percent-encoding that breaks the generated OpenAPI schema on some clients.

- **Surface:** REST API — `agentic_v2/server/`.
- **Risk:** Inconsistent with the `GET /runs/{filename}/evaluation` endpoint, which does use a path param.
- **Workaround:** None needed — the endpoint works. Just surprising.
- **Status:** Intentional. See `KNOWN_ISSUES.md` (eval package) for the trade-off analysis.
- **Upstream fix:** Sprint B will revisit with usage data. May move to path-param-with-escaping.

### 2.2 LangChain adapter requires a separate extras install

Running `agentic run <workflow> --adapter langchain` requires that the package was installed with the `[langchain]` extras:

```bash
pip install -e ".[dev,server,langchain]"
```

A bare `pip install -e ".[dev,server]"` will succeed, but any `--adapter langchain` call fails at import time.

- **Surface:** `agentic_v2/langchain/` imports are guarded with `try/except ImportError`, but the adapter registration path surfaces the error late.
- **Risk:** Confusing first-run failure if a contributor installed minimal extras.
- **Workaround:** Install with `langchain` extras (included in `just setup`), or pass `--adapter native` explicitly.
- **Status:** Accepted — the optional extras design is correct for dependency weight. The adapter is **deprecated** per [ADR-013](adr/ADR-013-foundation-native-dag.md) and emits a `DeprecationWarning` on import; removal target is v2.0 (2026-Q3). The CLI's `--adapter langchain` default is transitional and exists only to avoid breaking existing scripts during the migration window.
- **Upstream fix:** Migrate workflows to `--adapter native`; the extras install and this limitation disappear at the v2.0 removal milestone.

---

## 3. CI and environment dependencies

### 3.1 Placeholder mode exists but CI still validates provider integration

The runtime supports `AGENTIC_NO_LLM=1` for deterministic placeholder execution across both native and LangChain engines (committed in `c2aff71`, documented in [`docs/NO_LLM_MODE.md`](NO_LLM_MODE.md)). However, some end-to-end CI gates intentionally exercise GitHub Models through `GITHUB_TOKEN` to validate provider integration itself. The trade-off is ratified in [ADR-016](adr/ADR-016-github-token-as-default-e2e-llm.md).

- **Surface:** `ci.yml`, `nightly.yml`, `performance-benchmark.yml` (which require live provider credentials).
- **Zero-config alternative:** Set `AGENTIC_NO_LLM=1` to run workflows without any LLM provider. See [`docs/NO_LLM_MODE.md`](NO_LLM_MODE.md) for scope and limitations.
- **Risk:** A GitHub Models outage or rate-limit event fails the provider-integration CI jobs, but `AGENTIC_NO_LLM=1` jobs remain unaffected.
- **Workaround:** `agentic run test_deterministic` or `AGENTIC_NO_LLM=1 agentic run <workflow>` runs entirely without LLM calls — use for shape and flow testing.
- **Status:** Accepted for v0.3.0. Free LLM access in CI vs. provider dependency trade-off is explicit in ADR-016.
- **Upstream fix:** None — placeholder mode is live. Future work: extend mode to evaluation/rubric scoring.

### 3.2 Windows is a first-class target but has specific gotchas

Epic 3 hardened the Windows bring-up story. Known residual friction:

- `npx` is unreliable on Windows PATH; always use `npm` for running scripts (see [`CLAUDE.md`](../CLAUDE.md)).
- `jq` is not available; JSON parsing in scripts uses `python -c` or `grep`.
- `pnpm` fails with EPERM on mounted / shared drives; fall back to `npm`.
- PowerShell run from Git Bash mangles `$_` and `$_.Property` — wrap with `powershell.exe -NoProfile -Command '…'` and single quotes.

- **Surface:** Developer workflow scripts.
- **Status:** Documented in `CLAUDE.md`. No single fix — all require awareness.

---

## 4. Operational gaps

### 4.1 Replay buffer is in-memory only

The WebSocket event replay buffer in `agentic_v2/server/websocket.py` is a 500-event in-memory ring. If the server restarts, the buffer is lost and reconnecting clients see a partial history.

- **Surface:** Live execution streaming.
- **Risk:** A server restart mid-run produces an inconsistent client view. The run itself continues; only the UI "missed" events.
- **Workaround:** Reload the run's final state from `GET /runs/{filename}` after a restart.
- **Status:** Accepted. A durable replay buffer is scope creep for v0.3.x.

### 4.2 Provider stats persist but are not synchronized across processes

`SmartModelRouter` stats survive a single process restart via atomic JSON serialization. Multi-process or multi-host deployments do not share this state.

- **Surface:** `agentic_v2/models/smart_router.py`.
- **Risk:** Circuit-breaker state does not propagate — each process rediscovers "this model is dead" independently.
- **Workaround:** Run a single server process, or accept the warm-up cost.
- **Status:** Accepted. Multi-host sharing is an Epic 8 candidate.

---

## 5. Documentation and process

### 5.1 Implementation plans for Epics 3, 5, and 6 are retrospective

Epics 1 and 2 have proper pre-implementation plan docs. Epics 3, 5, and 6 shipped without plan docs — the retrospective plans under [`implementation notes/retro-epic*`](implementation notes/) were written after the fact to preserve decision history. They are shorter and less exhaustive than the Epic 1/2 plans.

- **Risk:** Decision rationale may be under-documented compared to prospective plans.
- **Mitigation:** Three load-bearing decisions from Epic 6 are called out in `KNOWN_ISSUES.md` (eval package).
- **Status:** Accepted; new epics are expected to ship with prospective plans going forward.

### 5.2 `Generated:` and `Last Updated:` dates in docs may lag

Per-package deep-dive docs under `docs/architecture-*.md` carry generation dates that were set during an initial documentation pass (2026-04-16 to 2026-04-18). Subsequent epic work may have moved details under them without updating the dates.

- **Status:** Accepted. Trust the current code over the doc when the date is older than 2 weeks; file an issue.
- **Upstream fix:** Sprint B — audit and either refresh or re-date.

---

## 6. How this list is maintained

- Any limitation discovered in the wild should be added here with a Status and a workaround. Do not hide limitations in issue trackers.
- When a limitation is fixed, remove the entry and link the fix from `CHANGELOG.md` under the release it shipped in.
- The "Last verified" date at the top of this document is refreshed whenever an entry is added, resolved, or materially changed.
