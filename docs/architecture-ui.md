# UI Architecture: React Dashboard

## Executive Summary

The React dashboard is a single-page application that provides a management interface for the multi-agent workflow runtime. It delivers real-time DAG visualization of workflow execution, live step-by-step streaming via WebSocket, and evaluation result management. The frontend communicates exclusively with the FastAPI backend at `localhost:8010` through a Vite dev proxy, and ships as a static build artifact consumed by the server in production.

---

## Technology Stack

| Dependency | Version | Role |
|---|---|---|
| React | 19 | UI framework |
| TypeScript | 5.7 (strict) | Type safety |
| Vite | 6 | Build toolchain, dev proxy |
| TanStack Query | 5 | Server state management |
| @xyflow/react | 12 | DAG graph visualization |
| react-router-dom | 7 | Client-side routing |
| Tailwind CSS | 3.4 | Utility-first styling |
| lucide-react | latest | Icon library |
| Vitest + RTL | 2.1 | Unit and component testing |

TypeScript is configured with `strict: true` and `noUncheckedIndexedAccess: true`. The path alias `@` maps to `src/`.

---

## Architecture Pattern

The application follows a **component-based SPA** architecture with the following structural principles:

- **Server state** is managed exclusively by TanStack Query. There is no Redux store, no React Context for global state, and no client-side state management library.
- **Real-time execution state** is owned by the `useWorkflowStream` hook, which wraps a WebSocket connection and exposes derived state to the `LivePage`.
- **Feature flags** are resolved at compile time via Vite defines, not at runtime via API or localStorage.
- **Routing** is flat BrowserRouter with no lazy loading and no authentication guards.

```
src/
├── api/            # fetch client, WebSocket client
├── components/
│   ├── common/     # StatusBadge, JsonViewer, DurationDisplay
│   ├── dag/        # WorkflowDAG, StepNode, dagLayout
│   ├── layout/     # Sidebar
│   ├── live/       # LiveStepDetails, NodeConfigOverlay, StepLogPanel, TokenCounter
│   └── runs/       # RunList, RunDetail, RunSummaryCards, RunConfigForm
├── hooks/          # useWorkflows.ts, useRuns.ts, useWorkflowStream.ts
├── pages/          # 8 page components
├── types/          # Shared TypeScript interfaces
└── utils/          # featureFlags.ts, formatting helpers
```

---

## API Client Layer

**File:** `src/api/client.ts`

All HTTP communication uses the native `fetch` API. There are no third-party HTTP clients, no interceptors, and no authentication headers.

- **Base URL:** `/api` — resolved relative to the page origin and proxied by Vite to `localhost:8010` during development.
- **Generic wrapper:** `fetchJSON<T>(path, options?)` — performs a `fetch`, checks `response.ok`, parses JSON, and returns `T`. Throws on non-2xx responses.
- No retry logic on the HTTP client itself. Retry is delegated to TanStack Query configuration.

**File:** `src/api/websocket.ts`

The WebSocket client manages a single connection per `LivePage` mount.

- **Reconnect strategy:** Exponential backoff, maximum 5 retries. After 5 failures the connection is marked permanently closed and the UI shows an error state.
- **Message handling:** Raw JSON messages are parsed and dispatched to the `useWorkflowStream` hook callback.
- **Teardown:** The client exposes a `close()` method; the hook calls it in the `useEffect` cleanup to prevent stale connections on unmount.

Note: `listAgents()` and `healthCheck()` are defined in the API client but are not called anywhere in the current codebase.

---

## State Management

### TanStack Query Configuration

Global defaults set in `App.tsx` via `QueryClient`:

| Option | Value |
|---|---|
| `staleTime` | 10 000 ms |
| `retry` | 1 |
| `refetchOnWindowFocus` | `false` |

### Query Hooks

**`src/hooks/useWorkflows.ts`** — 4 hooks:
- `useWorkflows()` — fetches workflow list
- `useWorkflow(name)` — fetches single workflow definition
- `useWorkflowRuns(name)` — fetches run history for a workflow
- `useWorkflowValidation(name)` — triggers validation on demand

**`src/hooks/useRuns.ts`** — 3 hooks:
- `useRuns()` — fetches all run files
- `useRunDetail(filename)` — fetches parsed run JSON
- `useDatasets()` — fetches available dataset names

### Mutations

Three mutations are defined inline within their respective page components rather than extracted to shared hooks:

- `runWorkflow` — `POST /api/workflows/:name/run` — triggered from `WorkflowDetailPage`
- `saveWorkflowEditor` — `PUT /api/workflows/:name` — triggered from `WorkflowEditorPage`
- `validateWorkflowEditor` — `POST /api/workflows/:name/validate` — triggered from `WorkflowEditorPage`

### WebSocket State: useWorkflowStream

**File:** `src/hooks/useWorkflowStream.ts`

Manages all live execution state. Returned state shape:

| Field | Type | Description |
|---|---|---|
| `stepStates` | `Map<string, StepState>` | Per-step accumulated state keyed by step name |
| `events` | `StreamEvent[]` | Raw event log for `StepLogPanel` |
| `workflowStatus` | `string` | Top-level run status |
| `evaluationResult` | `EvaluationResult \| null` | Final evaluation payload if present |

State updates are immutable: each incoming WebSocket message produces a new `Map` reference via spread/copy rather than in-place mutation. React Context is not used anywhere in the codebase.

---

## Routing

**Router:** `react-router-dom` v7 `BrowserRouter`, defined in `App.tsx`.

| Path | Component | Notes |
|---|---|---|
| `/` | `DashboardPage` | |
| `/workflows` | `WorkflowsPage` | |
| `/workflows/:name/edit` | `WorkflowEditorPage` | Rendered only when feature flag is enabled |
| `/workflows/:name` | `WorkflowDetailPage` | |
| `/datasets` | `DatasetsPage` | |
| `/evaluations` | `EvaluationsPage` | |
| `/runs/:filename` | `RunDetailPage` | |
| `/live/:runId` | `LivePage` | WebSocket-driven |
| `*` | Redirect to `/` | Catch-all |

There are no route guards, no authentication checks, and no `React.lazy` / Suspense-based code splitting. All page components are statically imported.

---

## Feature Flag

**File:** `src/utils/featureFlags.ts`

```ts
export function isWorkflowBuilderEnabled(): boolean {
  return __AGENTIC_ENABLE_WORKFLOW_BUILDER__ === true;
}
```

The constant `__AGENTIC_ENABLE_WORKFLOW_BUILDER__` is injected at build time by Vite's `define` config. It is not readable from `window` or `localStorage` at runtime. Dead-code elimination removes the `WorkflowEditorPage` import when the flag is `false`.

Set via environment variable: `VITE_AGENTIC_ENABLE_WORKFLOW_BUILDER=true`.

---

## Design System

The application uses a **dark theme** throughout. There is no light/dark toggle.

### Surface Scale

| Token | Hex | Usage |
|---|---|---|
| `surface-0` | `#0a0a0f` | Page background |
| `surface-1` | `#13131a` | Card background |
| `surface-2` | `#1a1a24` | Input / nested surface |
| `surface-3` | `#222230` | Hover / border |

### Accent Colors

`blue` (primary actions), `green` (success/running), `red` (error/failed), `amber` (warning/pending), `purple` (kickback edges in DAG).

### Custom Tailwind Classes

Defined in `src/index.css` using `@layer components`:

| Class | Description |
|---|---|
| `.card` | Dark surface card with border and rounded corners |
| `.card-hover` | `.card` plus hover border lift transition |
| `.btn-primary` | Blue filled button |
| `.btn-ghost` | Transparent button with hover fill |

### Icons

All icons are sourced from `lucide-react`. There are no custom SVGs or icon fonts.

---

## Build and Dev Configuration

### Build Command

```bash
tsc -b && vite build
```

TypeScript is checked first; Vite handles compilation and bundling. Output goes to `dist/`.

### Dev Server

```bash
npm run dev   # port 5173
```

### Vite Proxy

| Prefix | Target | Protocol |
|---|---|---|
| `/api/*` | `localhost:8010` | HTTP |
| `/ws/*` | `localhost:8010` | WebSocket |

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VITE_API_PROXY_TARGET` | `localhost:8010` | Backend proxy target |
| `VITE_AGENTIC_ENABLE_WORKFLOW_BUILDER` | `false` | Enables workflow editor page |

### TypeScript Configuration

- `strict: true`
- `noUncheckedIndexedAccess: true`
- `paths: { "@/*": ["src/*"] }`
- Separate `tsconfig.app.json` and `tsconfig.node.json`

---

## Testing

**Framework:** Vitest 2.1 with jsdom environment and React Testing Library.

| Metric | Value |
|---|---|
| Test files | 23 |
| Coverage | 23.2% |
| Configured threshold | 60% (not enforced in CI) |

### Well-Covered Modules

| Module | Coverage |
|---|---|
| `DurationDisplay` | ~100% |
| `StatusBadge` | ~100% |
| `dagLayout` | 100% |
| `useWorkflowStream` | 91% |

### Known Coverage Gaps

Page components, `RunConfigForm`, and `WorkflowDAG` have minimal or no test coverage. The 60% threshold in `vitest.config.ts` is configured but not enforced in CI, so the build does not fail on low coverage.

---

## Known Issues and Technical Debt

| Issue | Location | Impact |
|---|---|---|
| `useNodeConfigUpdate` hook and `NodeConfigOverlay` component are implemented but never wired to any page | `src/components/live/NodeConfigOverlay.tsx` | Dead code, no user-facing impact |
| `listAgents()` and `healthCheck()` are defined in the API client but never called | `src/api/client.ts` | Dead code |
| Test coverage at 23.2% against a 60% target | `vitest.config.ts` | Threshold not enforced; regression risk |
| Inline mutations in page components are not reusable | `WorkflowDetailPage`, `WorkflowEditorPage` | Low — pages are not deeply nested |
