# UI Component Inventory: React Dashboard

This document catalogs all 17 components in the React dashboard, organized by category. Each entry includes the source file path, props, and behavioral notes relevant to consumers and maintainers.

---

## Layout Components

### Sidebar

**File:** `src/components/layout/Sidebar.tsx`

Static left navigation panel. Renders `NavLink` elements from `react-router-dom` for all top-level application routes. The active route is highlighted using React Router's `isActive` callback to apply distinct styling to the currently matched link.

**Navigation Links:**

| Label | Target Route |
|---|---|
| Dashboard | `/` |
| Workflows | `/workflows` |
| Datasets | `/datasets` |
| Evaluations | `/evaluations` |
| Live | `/live` |

The component accepts no props. It has no local state and does not consume any query hooks.

---

## Common / Shared Components

### StatusBadge

**File:** `src/components/common/StatusBadge.tsx`

Renders a color-coded pill badge for a workflow or step execution status. Applies the appropriate Tailwind accent color class and a matching `lucide-react` icon for each status variant. The `running` status includes `animate-spin` on its icon.

| Prop | Type | Description |
|---|---|---|
| `status` | `StepStatus \| string` | The execution status to display |
| `size` | `'sm' \| 'md'` | Controls text and padding scale (optional, defaults to `'md'`) |

**Status-to-style mapping:**

| Status | Color | Icon |
|---|---|---|
| `pending` | amber | Clock |
| `running` | blue | Loader (animate-spin) |
| `completed` | green | CheckCircle |
| `failed` | red | XCircle |
| `skipped` | gray | MinusCircle |

Used in 6 or more locations across run lists, step panels, and the DAG node renderer.

---

### JsonViewer

**File:** `src/components/common/JsonViewer.tsx`

Renders an arbitrary JSON value as a collapsible, recursive tree. String values longer than 200 characters are truncated with a show-more affordance. Objects and arrays can be expanded or collapsed by clicking their key labels.

| Prop | Type | Description |
|---|---|---|
| `data` | `unknown` | The value to render (any JSON-serializable type) |
| `defaultExpanded` | `boolean` | Whether all nodes start expanded (optional) |
| `maxDepth` | `number` | Maximum depth before subtrees are collapsed by default (optional) |

Used in step I/O panels within `RunDetailPage` and `LiveStepDetails`.

---

### DurationDisplay

**File:** `src/components/common/DurationDisplay.tsx`

Formats a raw millisecond duration into a human-readable string. Handles null and undefined inputs gracefully by rendering nothing.

| Prop | Type | Description |
|---|---|---|
| `ms` | `number \| null \| undefined` | Duration in milliseconds |
| `className` | `string` | Optional additional Tailwind classes |

**Formatting rules:**

| Input range | Output format | Example |
|---|---|---|
| < 1 000 ms | `Xms` | `450ms` |
| < 60 000 ms | `X.Xs` | `4.2s` |
| >= 60 000 ms | `Xm Xs` | `1m 23s` |

Coverage is approximately 100% in the test suite.

---

## DAG Visualization Components

### WorkflowDAG

**File:** `src/components/dag/WorkflowDAG.tsx`

The primary DAG canvas component. Wraps `ReactFlowProvider` from `@xyflow/react` and renders the workflow as a directed graph. Used in both static preview mode (`WorkflowDetailPage`) and live animated mode (`LivePage`).

| Prop | Type | Description |
|---|---|---|
| `dagNodes` | `DAGNode[]` | Workflow step nodes from the DAG definition |
| `dagEdges` | `DAGEdge[]` | Directed edges between nodes |
| `stepStates` | `Map<string, StepState>` | Live per-step state (optional; omit for static preview) |
| `edgeCounts` | `Record<string, number>` | Message counts per edge for display (optional) |
| `kickbackEdges` | `string[]` | Edge IDs to render with kickback (violet) styling |
| `onNodeClick` | `(nodeId: string) => void` | Callback when a node is clicked (optional) |
| `className` | `string` | Optional additional CSS classes |

**Auto-pan behavior:** During live execution, the viewport automatically pans to center the node that has just transitioned to `running`. Auto-pan pauses when the user generates more than 2 interaction events within a 2-second window, and resumes after 5 seconds of inactivity.

**Edge coloring:**

| Edge state | Color |
|---|---|
| Pending | Gray |
| Active | Blue (animated dash) |
| Done | Green |
| Failed | Red |
| Kickback | Violet |

Renders `MiniMap`, `Controls`, and `Background` panels from `@xyflow/react`.

---

### StepNode

**File:** `src/components/dag/StepNode.tsx`

Custom node renderer registered with `@xyflow/react`. Displays a single workflow step within the DAG canvas.

**Displayed elements:**

- Step name and agent name
- Status icon (sourced from `StatusBadge` logic)
- Live `StepTimer` that updates every 250 ms while the step is in `running` state
- Accumulated token count badge (sourced from `token_usage` events)
- Model name and tier badge

Receives its data via the `data` prop as `StepNodeData`, which is injected by `WorkflowDAG` when building the React Flow node array.

---

### dagLayout

**File:** `src/components/dag/dagLayout.ts`

A pure utility function that converts a raw DAG response into positioned React Flow nodes and edges. Contains no React or side effects.

**Signature:** `dagLayout(dag: DAGResponse): { nodes: Node[], edges: Edge[] }`

**Layout constants:**

| Constant | Value | Purpose |
|---|---|---|
| `NODE_WIDTH` | 240 px | Fixed node width |
| `NODE_HEIGHT` | 120 px | Fixed node height |
| `H_GAP` | 60 px | Horizontal gap between nodes in the same level |
| `V_GAP` | 80 px | Vertical gap between topological levels |

**Algorithm:** Kahn's topological sort (BFS). Nodes are grouped into levels based on their maximum predecessor depth. Within each level, nodes are centered horizontally. The function does not detect cycles; a cyclic graph will produce incorrect layout output.

Coverage is 100% in the test suite.

---

## Run Components

### RunList

**File:** `src/components/runs/RunList.tsx`

Renders a scrollable list of run summary rows. Supports local (client-side) status filtering without a server round-trip. Displays skeleton pulse placeholders while data is loading.

| Prop | Type | Description |
|---|---|---|
| `runs` | `RunSummary[]` | Array of run summary records to display |
| `isLoading` | `boolean` | When true, renders skeleton rows instead of data |

The status filter is a local `useState` with options: `all`, `success`, `failed`. Filtering does not affect the TanStack Query cache.

---

### RunDetailSteps

**File:** `src/components/runs/RunDetail.tsx`

Renders an expandable step panel list for a completed run. Each panel can be individually expanded to reveal the step's input and output via `JsonViewer`.

| Prop | Type | Description |
|---|---|---|
| `steps` | `StepResult[]` | Array of completed step records |
| `selectedStep` | `string \| null` | ID of the currently selected/expanded step |
| `onSelectStep` | `(id: string \| null) => void` | Callback to change the selected step |

---

### RunSummaryCards

**File:** `src/components/runs/RunSummaryCards.tsx`

Displays aggregate run metrics as a row of stat cards. Renders skeleton placeholders when loading.

| Prop | Type | Description |
|---|---|---|
| `summary` | `RunsSummary` | Aggregate statistics object |
| `isLoading` | `boolean` | When true, renders skeleton cards |

Metrics shown: total runs, pass rate, average duration (via `DurationDisplay`), last run timestamp.

---

### RunConfigForm

**File:** `src/components/runs/RunConfigForm.tsx`

The most complex component in the codebase at approximately 681 lines. Renders the workflow run configuration form used on `WorkflowDetailPage`. On submission it POSTs a `WorkflowRunRequest` and navigates to `/live/:runId`.

| Prop | Type | Description |
|---|---|---|
| `inputs` | `WorkflowInputSchema` | JSON Schema-style definition of the workflow's expected inputs |
| `workflowName` | `string` | Name of the workflow being configured |
| `onChange` | `(values: RunConfigValues) => void` | Callback invoked on any field change |

**Embedded sub-components** (defined in the same file, not exported):

| Sub-component | Purpose |
|---|---|
| `CompactInputField` | Renders a single schema-driven input field (text, number, boolean, select) |
| `SampleSelector` | Multi-select grid for choosing evaluation dataset samples |
| `TechStackField` | Specialized field for selecting execution technology stack options |

---

## Live Execution Components

### LiveStepDetails

**File:** `src/components/live/LiveStepDetails.tsx`

Renders the step sidebar panel on `LivePage`. Displays a list of steps in execution order; selecting a step expands its input and output via `JsonViewer`.

| Prop | Type | Description |
|---|---|---|
| `stepStates` | `Map<string, StepState>` | Live step state map from `useWorkflowStream` |
| `stepOrder` | `string[]` | Ordered array of step IDs defining display order |
| `selectedStep` | `string \| null` | Currently selected step ID |
| `onSelectStep` | `(id: string \| null) => void` | Callback to change selection |

---

### NodeConfigOverlay

**File:** `src/components/live/NodeConfigOverlay.tsx`

A light-themed slide-in panel that allows runtime configuration overrides for a specific workflow step during an active execution. Uses `useNodeConfigUpdate` to send changes over the secondary WebSocket connection.

| Prop | Type | Description |
|---|---|---|
| `runId` | `string` | Active run identifier |
| `nodeId` | `string` | Step node to configure |
| `onClose` | `() => void` | Callback to close the panel |

**Configurable fields:** model selection, system prompt, temperature, max_tokens, top_p, tool_names.

**NOTE:** This component and the `useNodeConfigUpdate` hook are fully implemented but are not wired to any page in the current codebase. The component is dead code as of this writing.

---

### StepLogPanel

**File:** `src/components/live/StepLogPanel.tsx`

Collapsible timestamped event log panel displayed on `LivePage`. Renders all `ExecutionEvent` entries in chronological order with per-event-type color coding. Automatically filters out noise events: `keepalive` and `connection_established` are excluded from display.

| Prop | Type | Description |
|---|---|---|
| `events` | `ExecutionEvent[]` | Append-only event array from `useWorkflowStream` |

---

### TokenCounter

**File:** `src/components/live/TokenCounter.tsx`

Aggregates token consumption across all `token_usage` events in the active execution and displays the total token count alongside the number of distinct models that contributed usage.

| Prop | Type | Description |
|---|---|---|
| `events` | `ExecutionEvent[]` | Event array from `useWorkflowStream` |

---

## Pages

Eight page components map 1:1 to application routes. None use `React.lazy`. None have authentication guards.

| Component | File | Route | Description |
|---|---|---|---|
| `DashboardPage` | `src/pages/DashboardPage.tsx` | `/` | Aggregate stats cards, workflow grid, recent run summaries |
| `WorkflowsPage` | `src/pages/WorkflowsPage.tsx` | `/workflows` | Searchable, filterable list of all registered workflows |
| `WorkflowDetailPage` | `src/pages/WorkflowDetailPage.tsx` | `/workflows/:name` | Static DAG preview, run config form, execution history sidebar |
| `WorkflowEditorPage` | `src/pages/WorkflowEditorPage.tsx` | `/workflows/:name/edit` | Split-pane YAML editor with live DAG preview; only rendered when `VITE_AGENTIC_ENABLE_WORKFLOW_BUILDER` is set |
| `DatasetsPage` | `src/pages/DatasetsPage.tsx` | `/datasets` | Repository datasets, local datasets, and evaluation datasets |
| `EvaluationsPage` | `src/pages/EvaluationsPage.tsx` | `/evaluations` | Evaluation run list with rubric scores and pass/fail indicators |
| `RunDetailPage` | `src/pages/RunDetailPage.tsx` | `/runs/:filename` | Post-run static DAG with per-step I/O accordion panels |
| `LivePage` | `src/pages/LivePage.tsx` | `/live/:runId` | Real-time execution: auto-panning DAG canvas, step sidebar, event log |
