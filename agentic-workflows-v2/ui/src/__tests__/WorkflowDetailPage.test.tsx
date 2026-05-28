import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import WorkflowDetailPage from "../pages/WorkflowDetailPage";

const mockUseWorkflowDAG = vi.fn();
const mockUseRuns = vi.fn();
const mockRunWorkflow = vi.fn();
const mockFlag = vi.fn();

vi.mock("../hooks/useWorkflows", () => ({
  useWorkflowDAG: (...args: unknown[]) => mockUseWorkflowDAG(...args),
}));

vi.mock("../hooks/useRuns", () => ({
  useRuns: (...args: unknown[]) => mockUseRuns(...args),
}));

vi.mock("../config/featureFlags", () => ({
  isWorkflowBuilderEnabled: () => mockFlag(),
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual("../api/client");
  return {
    ...actual,
    runWorkflow: (...args: unknown[]) => mockRunWorkflow(...args),
  };
});

vi.mock("../components/dag/WorkflowDAG", () => ({
  default: () => <div>Workflow DAG</div>,
}));

vi.mock("../components/runs/RunList", () => ({
  default: ({ runs }: { runs?: Array<unknown> }) => <div>History {runs?.length ?? 0}</div>,
}));

vi.mock("../components/runs/RunConfigForm", () => ({
  default: ({ onChange }: { onChange: (values: unknown) => void }) => {
    onChange({
      inputValues: { prompt: "hello" },
      executionProfile: { runtime: "subprocess" },
      rubricId: "",
      evaluation: {
        enabled: false,
        datasetSource: "none",
        datasetId: "",
        evalSetId: "",
        selectedSamples: [0],
        runsPerRecord: 1,
      },
    });
    return <div>Run Config Form</div>;
  },
}));

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/workflows/review_flow"]}>
        <Routes>
          <Route path="/workflows/:name" element={<WorkflowDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("WorkflowDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFlag.mockReturnValue(true);
    mockUseWorkflowDAG.mockReturnValue({
      data: {
        name: "review_flow",
        description: "Review workflow",
        nodes: [{ id: "ingest", agent: "collector", description: "", depends_on: [], tier: null }],
        edges: [],
        inputs: [
          { name: "prompt", type: "string", description: "", default: "", required: true, enum: null },
        ],
      },
      isLoading: false,
    });
    mockUseRuns.mockReturnValue({
      data: [{ filename: "run.json" }],
      isLoading: false,
    });
    mockRunWorkflow.mockResolvedValue({ run_id: "run-123", status: "pending" });
  });

  it("renders the detail page with the edit entrypoint", () => {
    renderPage();

    expect(screen.getByText("Review workflow")).toBeInTheDocument();
    expect(screen.getByText("Workflow DAG")).toBeInTheDocument();
    expect(screen.getByText("Run Config Form")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /edit/i })).toHaveAttribute(
      "href",
      "/workflows/review_flow/edit"
    );
  });

  it("starts a run from the page", async () => {
    renderPage();

    fireEvent.click(screen.getByTestId("run-button"));

    await waitFor(() => {
      expect(mockRunWorkflow).toHaveBeenCalledWith({
        workflow: "review_flow",
        input_data: { prompt: "hello" },
        evaluation: undefined,
        execution_profile: { runtime: "subprocess" },
      });
    });
  });
});
