import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import RunConfigForm from "../components/runs/RunConfigForm";
import type { WorkflowInputSchema } from "../api/types";

/** Helper to build a minimal input schema. */
function makeInput(
  overrides: Partial<WorkflowInputSchema> & { name: string }
): WorkflowInputSchema {
  return {
    type: "string",
    description: "",
    default: null,
    required: true,
    enum: null,
    ...overrides,
  };
}

describe("RunConfigForm", () => {
  it("renders the correct number of input fields from schema", () => {
    const inputs: WorkflowInputSchema[] = [
      makeInput({ name: "repo_url", description: "GitHub repository URL" }),
      makeInput({ name: "issue_text", description: "Issue description" }),
    ];
    const onChange = vi.fn();

    render(<RunConfigForm inputs={inputs} workflowName="test" onChange={onChange} />);

    // Both fields should be rendered
    expect(screen.getByTestId("input-repo_url")).toBeInTheDocument();
    expect(screen.getByTestId("input-issue_text")).toBeInTheDocument();

    // Verify the containing grid exists
    expect(screen.getByTestId("workflow-inputs")).toBeInTheDocument();
  });

  it("renders a select dropdown for enum inputs", () => {
    const inputs: WorkflowInputSchema[] = [
      makeInput({
        name: "language",
        enum: ["python", "typescript", "go"],
        description: "Programming language",
      }),
    ];
    const onChange = vi.fn();

    render(<RunConfigForm inputs={inputs} workflowName="test" onChange={onChange} />);

    const select = screen.getByTestId("input-language") as HTMLSelectElement;
    expect(select.tagName).toBe("SELECT");

    // Enum options should be present
    const options = select.querySelectorAll("option");
    const optionValues = Array.from(options).map((o) => o.value);
    expect(optionValues).toContain("python");
    expect(optionValues).toContain("typescript");
    expect(optionValues).toContain("go");
  });

  it("does not mark optional fields as required", () => {
    const inputs: WorkflowInputSchema[] = [
      makeInput({ name: "optional_field", required: false }),
      makeInput({ name: "required_field", required: true }),
    ];
    const onChange = vi.fn();

    render(<RunConfigForm inputs={inputs} workflowName="test" onChange={onChange} />);

    const optionalInput = screen.getByTestId(
      "input-optional_field"
    ) as HTMLInputElement;
    const requiredInput = screen.getByTestId(
      "input-required_field"
    ) as HTMLInputElement;

    expect(optionalInput.required).toBe(false);
    expect(requiredInput.required).toBe(true);
  });

  it("populates default values from schema", () => {
    const inputs: WorkflowInputSchema[] = [
      makeInput({ name: "model", default: "gpt-4o" }),
    ];
    const onChange = vi.fn();

    render(<RunConfigForm inputs={inputs} workflowName="test" onChange={onChange} />);

    const input = screen.getByTestId("input-model") as HTMLInputElement;
    expect(input.value).toBe("gpt-4o");
  });

  it("shows advanced config panel with rubric and runtime options when toggled", () => {
    const inputs: WorkflowInputSchema[] = [
      makeInput({ name: "task" }),
    ];
    const onChange = vi.fn();

    render(<RunConfigForm inputs={inputs} workflowName="test" onChange={onChange} />);

    // Advanced panel should not be visible initially
    expect(screen.queryByTestId("rubric-config")).not.toBeInTheDocument();
    expect(screen.queryByTestId("runtime-config")).not.toBeInTheDocument();

    // Click toggle
    fireEvent.click(screen.getByTestId("advanced-toggle"));

    // Now both config sections should be visible
    expect(screen.getByTestId("rubric-config")).toBeInTheDocument();
    expect(screen.getByTestId("runtime-config")).toBeInTheDocument();
  });

  it("calls onChange with execution profile and rubric values", async () => {
    const inputs: WorkflowInputSchema[] = [
      makeInput({ name: "prompt", default: "hello" }),
    ];
    const onChange = vi.fn();

    render(<RunConfigForm inputs={inputs} workflowName="test" onChange={onChange} />);

    // The form should emit onChange on initial render with defaults
    expect(onChange).toHaveBeenCalled();

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1]?.[0];
    expect(lastCall).toBeDefined();
    expect(lastCall!.inputValues).toHaveProperty("prompt", "hello");
    expect(lastCall!.executionProfile).toHaveProperty("runtime", "subprocess");
    expect(lastCall!.rubricId).toBe("");
  });

  it("renders textarea for object-type inputs", () => {
    const inputs: WorkflowInputSchema[] = [
      makeInput({ name: "config", type: "object", description: "JSON config" }),
    ];
    const onChange = vi.fn();

    render(<RunConfigForm inputs={inputs} workflowName="test" onChange={onChange} />);

    const textarea = screen.getByTestId("input-config") as HTMLTextAreaElement;
    expect(textarea.tagName).toBe("TEXTAREA");
  });

  it("renders no input grid when inputs array is empty", () => {
    const onChange = vi.fn();

    render(<RunConfigForm inputs={[]} workflowName="test" onChange={onChange} />);

    expect(screen.queryByTestId("workflow-inputs")).not.toBeInTheDocument();
    // Form wrapper should still exist
    expect(screen.getByTestId("run-config-form")).toBeInTheDocument();
  });
});
