/** Mirrors server StepStatus enum. */
export type StepStatus =
  | "pending"
  | "running"
  | "success"
  | "failed"
  | "skipped"
  | "cancelled";

/** A node in the DAG visualization (from GET /api/workflows/{name}/dag). */
export interface DAGNode {
  id: string;
  agent: string | null;
  description: string;
  depends_on: string[];
  tier: string | null;
}

export interface DAGEdge {
  source: string;
  target: string;
}

/** Input parameter schema for a workflow. */
export interface WorkflowInputSchema {
  name: string;
  type: string;
  description: string;
  default: unknown;
  required: boolean;
  enum: string[] | null;
}

export interface DAGResponse {
  name: string;
  description: string;
  nodes: DAGNode[];
  edges: DAGEdge[];
  inputs?: WorkflowInputSchema[];
}

export interface WorkflowEditorStep {
  name: string;
  agent?: string | null;
  description?: string | null;
  tier?: string | null;
  depends_on?: string[];
  when?: string | null;
  loop_until?: string | null;
  loop_max?: number | null;
  tools?: string[];
  prompt_file?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface WorkflowEditorDocument extends DAGResponse {
  source: string;
  steps?: WorkflowEditorStep[];
  metadata?: Record<string, unknown> | null;
  read_only?: boolean;
  updated_at?: string | null;
}

export interface WorkflowEditorMutationRequest {
  source: string;
}

export interface WorkflowEditorValidationIssue {
  level: "error" | "warning";
  message: string;
  path?: string | null;
}

export interface WorkflowEditorValidateResponse {
  valid: boolean;
  issues: WorkflowEditorValidationIssue[];
  workflow?: WorkflowEditorDocument;
}

export interface WorkflowEditorSaveResponse {
  saved: boolean;
  workflow: WorkflowEditorDocument;
}

/** Summary of a single run (from GET /api/runs). */
export interface RunSummary {
  filename: string;
  run_id: string | null;
  workflow_name: string | null;
  status: string | null;
  success_rate: number | null;
  total_duration_ms: number | null;
  step_count: number | null;
  failed_step_count: number | null;
  start_time: string | null;
  end_time: string | null;
  evaluation_score?: number | null;
  evaluation_grade?: string | null;
}

/** Full run detail (from GET /api/runs/{filename}). */
export interface RunDetail {
  run_id: string;
  workflow_name: string;
  status: string;
  success_rate: number;
  total_duration_ms: number;
  step_count: number;
  failed_step_count: number;
  start_time: string;
  end_time: string;
  steps: StepResult[];
  dataset?: Record<string, unknown> | null;
  extra?: {
    evaluation_requested?: boolean;
    evaluation?: EvaluationResult | null;
    [key: string]: unknown;
  } | null;
}

export interface StepResult {
  step_name: string;
  status: StepStatus;
  duration_ms: number;
  model_used: string | null;
  tokens_used: number | null;
  tier: string | null;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  error: string | null;
  metadata?: Record<string, unknown> | null;
}

/** Aggregate stats (from GET /api/runs/summary). */
export interface RunsSummary {
  total_runs: number;
  success: number;
  failed: number;
  avg_duration_ms: number | null;
  workflows: string[];
  tokens_30d?: number | null;
}

/** Execution profile for runtime configuration. */
export interface ExecutionProfileRequest {
  runtime: "subprocess" | "docker";
  max_attempts?: number;
  max_duration_minutes?: number;
  container_image?: string;
}

/** POST /api/run request. */
export interface WorkflowRunRequest {
  workflow: string;
  input_data: Record<string, unknown>;
  run_id?: string;
  evaluation?: WorkflowEvaluationRequest;
  execution_profile?: ExecutionProfileRequest;
}

/** POST /api/run response. */
export interface WorkflowRunResponse {
  run_id: string;
  status: StepStatus;
}

export interface WorkflowEvaluationRequest {
  enabled: boolean;
  enforce_hard_gates?: boolean;
  dataset_source: "none" | "repository" | "local";
  dataset_id?: string;
  local_dataset_path?: string;
  sample_index?: number;
  rubric?: string;
  rubric_id?: string;
}

export interface EvaluationDatasetOption {
  id: string;
  name: string;
  source: "repository" | "local";
  description: string;
  sample_count: number | null;
}

export interface EvaluationSetOption {
  id: string;
  name: string;
  description: string;
  datasets: string[];
}

export interface EvaluationDatasetsResponse {
  repository: EvaluationDatasetOption[];
  local: EvaluationDatasetOption[];
  eval_sets: EvaluationSetOption[];
}

export interface EvaluationCriterionScore {
  criterion: string;
  score: number;
  weight: number;
  max_score: number;
}

export interface EvaluationResult {
  enabled: boolean;
  rubric: string;
  criteria: EvaluationCriterionScore[];
  overall_score: number;
  weighted_score: number;
  grade: string;
  passed: boolean;
  pass_threshold: number;
  generated_at: string;
  dataset?: Record<string, unknown> | null;
}

// ---------------------------------------------------------------------------
// WebSocket execution events
// ---------------------------------------------------------------------------
// The server-originating wire shapes below are AUTO-GENERATED from the
// Pydantic contract in `agentic_v2/contracts/events.py`. Regenerate with:
//
//     python scripts/generate_ts_types.py              # in agentic-workflows-v2/
//     npm run generate:types                           # in agentic-workflows-v2/ui/
//
// The `wire-format-drift` CI job fails any PR that changes the Python
// contract without regenerating the TypeScript mirror. See CONTRIBUTING.md.
export type {
  WorkflowStartEvent,
  StepStartEvent,
  StepEndEvent,
  StepCompleteEvent,
  StepErrorEvent,
  WorkflowEndEvent,
  EvaluationStartEvent,
  EvaluationCompleteEvent,
} from "./events.generated";

import type { ExecutionEvent as WireExecutionEvent } from "./events.generated";

/**
 * Client-only WebSocket event shapes emitted by the streaming channel
 * itself (connection lifecycle, transport-level errors, keepalive pings).
 *
 * These are NOT part of the Python `ExecutionEvent` contract — the server
 * never wraps them in a Pydantic model — so they stay hand-defined here.
 */
export type ChannelEvent =
  | { type: "error"; run_id: string; error: string }
  | { type: "keepalive" }
  | { type: "connection_established"; run_id: string; message: string };

/**
 * Union of every event type the UI handles on the execution WebSocket.
 *
 * Wire events come from `events.generated.ts` (Pydantic-derived).
 * Channel events are transport-level and defined above.
 */
export type ExecutionEvent = WireExecutionEvent | ChannelEvent;

/** Agent info (from GET /api/agents). */
export interface AgentInfo {
  name: string;
  description: string;
  tier: string;
}

// ---------------------------------------------------------------------------
// Epic 6 — Evaluation detail types
// ---------------------------------------------------------------------------

export interface EvaluationCriterionDetail {
  criterion: string;
  weight: number;
  raw_score: number;
  normalized_score: number;
  weighted_contribution: number;
  floor?: number | null;
  floor_violated: boolean;
}

export interface ScoreLayers {
  layer1_objective: number;
  layer2_judge?: number | null;
  layer3_similarity: number;
  layer3_efficiency: number;
  layer3_advisory: number;
}

export interface HardGates {
  required_outputs_present: boolean;
  overall_status_success: boolean;
  no_critical_step_failures: boolean;
  release_build_verified: boolean;
  schema_contract_valid: boolean;
  dataset_workflow_compatible: boolean;
}

export interface FloorViolation {
  criterion: string;
  floor: number;
  normalized_score: number;
}

export interface RunEvaluationDetail {
  enabled: boolean;
  rubric: string;
  rubric_id: string;
  rubric_version: string;
  criteria: EvaluationCriterionDetail[];
  overall_score: number;
  weighted_score: number;
  objective_weighted_score: number;
  grade: string;
  grade_capped: boolean;
  passed: boolean;
  pass_threshold: number;
  hard_gates?: HardGates | null;
  hard_gate_failures: string[];
  floor_violations: FloorViolation[];
  step_scores: Record<string, unknown>;
  score_layers?: ScoreLayers | null;
  hybrid_weights: Record<string, number>;
  judge?: Record<string, unknown> | null;
  generated_at: string;
  dataset?: Record<string, unknown> | null;
}

/** Response for GET /api/runs/{filename}/evaluation */
export interface RunEvaluationDetailResponse {
  filename: string;
  run_id: string | null;
  workflow_name: string | null;
  status: string | null;
  evaluation_requested: boolean;
  dataset?: Record<string, unknown> | null;
  evaluation?: RunEvaluationDetail | null;
}

// ---------------------------------------------------------------------------
// Epic 6 — Dataset sample browser types
// ---------------------------------------------------------------------------

export interface DatasetSampleSummary {
  sample_index: number;
  sample_id?: string | null;
  task_id?: string | null;
  title: string;
  summary: string;
  field_names: string[];
}

/** Response for GET /api/eval/datasets/sample-list */
export interface DatasetSampleListResponse {
  dataset_source: string;
  dataset_id: string;
  sample_count: number;
  offset: number;
  limit: number;
  samples: DatasetSampleSummary[];
}

/** Response for GET /api/eval/datasets/sample-detail */
export interface DatasetSampleDetailResponse {
  dataset_source: string;
  dataset_id: string;
  sample_index: number;
  sample_id?: string | null;
  task_id?: string | null;
  field_names: string[];
  summary: string;
  sample: Record<string, unknown>;
  dataset_meta: Record<string, unknown>;
  workflow_preview?: Record<string, unknown> | null;
}
