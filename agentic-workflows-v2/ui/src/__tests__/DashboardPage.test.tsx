import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DashboardPage from "../pages/DashboardPage";

const mockUseRunsSummary = vi.fn();
const mockUseRuns = vi.fn();
const mockUseWorkflows = vi.fn();

vi.mock("../hooks/useRuns", () => ({
  useRunsSummary: () => mockUseRunsSummary(),
  useRuns: () => mockUseRuns(),
}));

vi.mock("../hooks/useWorkflows", () => ({
  useWorkflows: () => mockUseWorkflows(),
}));

vi.mock("../hooks/useHotkeys", () => ({
  useHotkeys: () => {},
}));

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders available workflows and recent runs", () => {
    mockUseRunsSummary.mockReturnValue({
      data: { total_runs: 2, success: 2, failed: 0 },
      isLoading: false,
    });
    mockUseRuns.mockReturnValue({
      data: [
        {
          filename: "run1.json",
          run_id: "run-001",
          workflow_name: "triage",
          status: "success",
          start_time: null,
          step_count: 1,
          failed_step_count: 0,
          total_duration_ms: 1000,
          evaluation_score: null,
        },
        {
          filename: "run2.json",
          run_id: "run-002",
          workflow_name: "review",
          status: "success",
          start_time: null,
          step_count: 1,
          failed_step_count: 0,
          total_duration_ms: 2000,
          evaluation_score: null,
        },
      ],
      isLoading: false,
    });
    mockUseWorkflows.mockReturnValue({ data: ["triage", "review"] });

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    );

    // Workflow quick links render in the workflows section
    expect(screen.getByRole("link", { name: /triage/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /review/i })).toBeInTheDocument();
    // Dashboard heading
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
  });

  it("renders the empty state when there are no runs", () => {
    mockUseRunsSummary.mockReturnValue({
      data: { total_runs: 0, success: 0, failed: 0 },
      isLoading: false,
    });
    mockUseRuns.mockReturnValue({ data: [], isLoading: false });
    mockUseWorkflows.mockReturnValue({ data: ["triage"] });

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    );

    // Empty state text from the component
    expect(
      screen.getByText(/no runs yet · select a workflow to start/i)
    ).toBeInTheDocument();
  });
});
