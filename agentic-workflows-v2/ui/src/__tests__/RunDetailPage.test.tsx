import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RunDetailPage from "../pages/RunDetailPage";

const mockUseRunDetail = vi.fn();
const mockUseWorkflowDAG = vi.fn();

vi.mock("../hooks/useRuns", () => ({
  useRunDetail: (...args: unknown[]) => mockUseRunDetail(...args),
}));

vi.mock("../hooks/useWorkflows", () => ({
  useWorkflowDAG: (...args: unknown[]) => mockUseWorkflowDAG(...args),
}));

vi.mock("../components/dag/WorkflowDAG", () => ({
  default: () => <div>Workflow DAG</div>,
}));

vi.mock("../components/runs/RunDetail", () => ({
  default: ({ steps }: { steps: Array<unknown> }) => <div>Run Detail Steps {steps.length}</div>,
}));

describe("RunDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders loading and not-found states", () => {
    mockUseRunDetail.mockReturnValue({ data: undefined, isLoading: true });
    mockUseWorkflowDAG.mockReturnValue({ data: undefined });

    const { rerender } = render(
      <MemoryRouter initialEntries={["/runs/run.json"]}>
        <Routes>
          <Route path="/runs/:filename" element={<RunDetailPage />} />
        </Routes>
      </MemoryRouter>
    );

    // Component renders "$ loading run…" (unicode ellipsis)
    expect(screen.getByText("$ loading run…")).toBeInTheDocument();

    mockUseRunDetail.mockReturnValue({ data: null, isLoading: false });
    rerender(
      <MemoryRouter initialEntries={["/runs/run.json"]}>
        <Routes>
          <Route path="/runs/:filename" element={<RunDetailPage />} />
        </Routes>
      </MemoryRouter>
    );

    // Component renders "$ run not found"
    expect(screen.getByText("$ run not found")).toBeInTheDocument();
  });

  it("renders the run summary, DAG, and evaluation summary", () => {
    mockUseRunDetail.mockReturnValue({
      data: {
        run_id: "run-123",
        workflow_name: "review_flow",
        status: "success",
        success_rate: 1,
        total_duration_ms: 5300,
        step_count: 2,
        failed_step_count: 0,
        start_time: "2026-04-11T12:00:00Z",
        end_time: "2026-04-11T12:00:05Z",
        steps: [
          {
            step_name: "ingest",
            status: "success",
            duration_ms: 1500,
            model_used: "gpt-4o-mini",
            tokens_used: 120,
            tier: "fast",
            input: {},
            output: {},
            error: null,
            metadata: null,
          },
        ],
        extra: {
          evaluation: {
            enabled: true,
            rubric: "default",
            criteria: [],
            overall_score: 92,
            weighted_score: 92,
            grade: "A",
            passed: true,
            pass_threshold: 80,
            generated_at: "2026-04-11T12:00:05Z",
          },
        },
      },
      isLoading: false,
    });
    mockUseWorkflowDAG.mockReturnValue({
      data: {
        name: "review_flow",
        description: "",
        nodes: [{ id: "ingest", agent: null, description: "", depends_on: [], tier: null }],
        edges: [],
      },
    });

    render(
      <MemoryRouter initialEntries={["/runs/run.json"]}>
        <Routes>
          <Route path="/runs/:filename" element={<RunDetailPage />} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText("review_flow")).toBeInTheDocument();
    expect(screen.getByText("run-123")).toBeInTheDocument();
    expect(screen.getByText("Workflow DAG")).toBeInTheDocument();
    expect(screen.getByText("Run Detail Steps 1")).toBeInTheDocument();
    // Component renders: grade <span>A</span> — so "grade" and "A" are separate nodes
    expect(screen.getByText(/grade/i)).toBeInTheDocument();
    expect(screen.getByText("A")).toBeInTheDocument();
    // Evaluation pill renders "passed" (lowercase)
    expect(screen.getByText("passed")).toBeInTheDocument();
  });
});
