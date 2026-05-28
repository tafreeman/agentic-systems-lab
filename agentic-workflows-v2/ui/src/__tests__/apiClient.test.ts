import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getWorkflowEditor,
  getWorkflowDAG,
  listEvaluationDatasets,
  listRuns,
  listWorkflows,
  saveWorkflowEditor,
  validateWorkflowEditor,
} from "../api/client";

describe("API client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("listWorkflows fetches /api/workflows", async () => {
    const mockResponse = { workflows: ["code_review", "fullstack_generation"] };
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    } as Response);

    const result = await listWorkflows();
    expect(result.workflows).toEqual(["code_review", "fullstack_generation"]);
    expect(fetch).toHaveBeenCalledWith("http://localhost:3000/api/workflows", undefined);
  });

  it("getWorkflowDAG fetches /api/workflows/{name}/dag", async () => {
    const mockDAG = { name: "test", description: "", nodes: [], edges: [] };
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockDAG),
    } as Response);

    const result = await getWorkflowDAG("test");
    expect(result.name).toBe("test");
    expect(fetch).toHaveBeenCalledWith("http://localhost:3000/api/workflows/test/dag", undefined);
  });

  it("getWorkflowEditor fetches /api/workflows/{name}/editor", async () => {
    const mockEditor = {
      name: "test",
      path: "workflows/test.yaml",
      yaml_text: "name: test\nsteps:\n  - name: draft\n    agent: writer\n",
      document: {
        name: "test",
        description: "Editable workflow",
        steps: [{ name: "draft", agent: "writer", description: "Draft copy" }],
      },
      step_count: 1,
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockEditor),
    } as Response);

    const result = await getWorkflowEditor("test");
    expect(result.source).toContain("name: test");
    expect(result.nodes[0]?.id).toBe("draft");
    expect(fetch).toHaveBeenCalledWith("http://localhost:3000/api/workflows/test/editor", undefined);
  });

  it("listRuns fetches /api/runs with params", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    } as Response);

    await listRuns("code_review", 10);
    const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]?.[0] as string;
    expect(url).toContain("workflow=code_review");
    expect(url).toContain("limit=10");
  });

  it("listEvaluationDatasets fetches /api/eval/datasets", async () => {
    const mockResponse = { repository: [], local: [] };
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    } as Response);

    const result = await listEvaluationDatasets();
    expect(result).toEqual(mockResponse);
    expect(fetch).toHaveBeenCalledWith("http://localhost:3000/api/eval/datasets", undefined);
  });

  it("saveWorkflowEditor sends PUT to /api/workflows/{name}", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          name: "test",
          path: "workflows/test.yaml",
          yaml_text: "name: test\nsteps: []\n",
          document: { name: "test", steps: [] },
          step_count: 0,
        }),
    } as Response);

    await saveWorkflowEditor("test", { source: "steps: []" });
    expect(fetch).toHaveBeenCalledWith("http://localhost:3000/api/workflows/test", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ yaml_text: "steps: []" }),
    });
  });

  it("validateWorkflowEditor sends POST to /api/workflows/validate", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          valid: true,
          name: "test",
          step_count: 0,
          yaml_text: "name: test\nsteps: []\n",
        }),
    } as Response);

    await validateWorkflowEditor("test", { source: "steps: []" });
    expect(fetch).toHaveBeenCalledWith("http://localhost:3000/api/workflows/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: "steps: []", name: "test" }),
    });
  });

  it("throws on non-OK response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 404,
      text: () => Promise.resolve("Not Found"),
    } as Response);

    await expect(listWorkflows()).rejects.toThrow("API 404");
  });
});
