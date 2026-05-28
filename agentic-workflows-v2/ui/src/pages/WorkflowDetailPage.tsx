import { useRef, useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { Play, ArrowLeft, Loader2, Pencil } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { useWorkflowDAG } from "../hooks/useWorkflows";
import { useRuns } from "../hooks/useRuns";
import { runWorkflow } from "../api/client";
import WorkflowDAG from "../components/dag/WorkflowDAG";
import BDagMini from "../components/dag/BDagMini";
import RunList from "../components/runs/RunList";
import RunConfigForm, {
  type RunConfigValues,
} from "../components/runs/RunConfigForm";
import { isWorkflowBuilderEnabled } from "../config/featureFlags";
import BTopBar from "../components/layout/BTopBar";
import BBox from "../components/common/BBox";

export default function WorkflowDetailPage() {
  const { name } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const workflowBuilderEnabled = isWorkflowBuilderEnabled();
  const { data: dag, isLoading: dagLoading } = useWorkflowDAG(name);
  const { data: runs, isLoading: runsLoading } = useRuns(name);

  const configRef = useRef<RunConfigValues>({
    inputValues: {},
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

  const buildInputData = (): Record<string, unknown> => {
    const data: Record<string, unknown> = {};
    if (!dag?.inputs) return data;
    const vals = configRef.current.inputValues;
    for (const inp of dag.inputs) {
      const val = vals[inp.name] ?? "";
      if (!val && !inp.required) continue;
      if (inp.type === "object" || inp.type === "array") {
        try {
          data[inp.name] = JSON.parse(val);
        } catch {
          data[inp.name] = val;
        }
      } else {
        data[inp.name] = val;
      }
    }
    return data;
  };

  const [batchProgress, setBatchProgress] = useState<{ done: number; total: number } | null>(null);

  const runMutation = useMutation({
    mutationFn: async () => {
      const { executionProfile, rubricId, evaluation } = configRef.current;

      const buildEvalRequest = (sampleIndex: number) => {
        if (!evaluation.enabled) return undefined;
        if (evaluation.datasetSource === "eval_set" && evaluation.evalSetId) {
          return {
            enabled: true as const,
            dataset_source: "repository" as const,
            dataset_id: evaluation.evalSetId,
            sample_index: sampleIndex,
            rubric_id: rubricId || undefined,
          };
        }
        if (evaluation.datasetSource !== "none" && evaluation.datasetId) {
          return {
            enabled: true as const,
            dataset_source: evaluation.datasetSource as "repository" | "local",
            dataset_id: evaluation.datasetId,
            sample_index: sampleIndex,
            rubric_id: rubricId || undefined,
          };
        }
        return {
          enabled: true as const,
          dataset_source: "none" as const,
          sample_index: sampleIndex,
          rubric_id: rubricId || undefined,
        };
      };

      const samples = evaluation.enabled && evaluation.selectedSamples.length > 0
        ? evaluation.selectedSamples
        : [0];
      const runsPerRecord = evaluation.enabled ? (evaluation.runsPerRecord ?? 1) : 1;
      const isBatch = samples.length > 1 || runsPerRecord > 1;

      const jobs: Array<{ sampleIndex: number }> = [];
      for (const s of samples) {
        for (let r = 0; r < runsPerRecord; r++) {
          jobs.push({ sampleIndex: s });
        }
      }

      if (!isBatch) {
        return runWorkflow({
          workflow: name!,
          input_data: buildInputData(),
          evaluation: buildEvalRequest(jobs[0] ? jobs[0].sampleIndex : 0),
          execution_profile: executionProfile,
        });
      }

      setBatchProgress({ done: 0, total: jobs.length });
      for (let i = 0; i < jobs.length; i++) {
        await runWorkflow({
          workflow: name!,
          input_data: buildInputData(),
          evaluation: buildEvalRequest(jobs[i]?.sampleIndex ?? 0),
          execution_profile: executionProfile,
        });
        setBatchProgress({ done: i + 1, total: jobs.length });
      }
      return null;
    },
    onSuccess: (data) => {
      setBatchProgress(null);
      if (data) {
        navigate(`/live/${data.run_id}`);
      } else {
        navigate(`/workflows/${encodeURIComponent(name!)}`);
      }
    },
    onError: () => {
      setBatchProgress(null);
    },
  });

  const hasInputs = dag?.inputs && dag.inputs.length > 0;

  return (
    <div className="flex h-full flex-col">
      <BTopBar path={`workflows/${name ?? ""}`}>
        <button
          type="button"
          onClick={() => navigate("/workflows")}
          className="btn-ghost"
        >
          <ArrowLeft className="h-3 w-3" />
          <span>[b] back</span>
        </button>
        {workflowBuilderEnabled && name && (
          <Link
            to={`/workflows/${encodeURIComponent(name)}/edit`}
            className="btn-ghost"
          >
            <Pencil className="h-3 w-3" />
            <span>[e] edit</span>
          </Link>
        )}
        <button
          type="button"
          onClick={() => runMutation.mutate()}
          disabled={runMutation.isPending}
          className="btn-primary"
          data-testid="run-button"
        >
          {runMutation.isPending ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <Play className="h-3 w-3" />
          )}
          <span>
            {batchProgress
              ? `${batchProgress.done}/${batchProgress.total}`
              : runMutation.isPending
                ? "[…] starting"
                : configRef.current.evaluation.enabled
                  ? "[▶] run + eval"
                  : "[▶] run"}
          </span>
        </button>
      </BTopBar>

      {/* Header band + config form */}
      <div className="border-b border-b-line bg-b-bg1 px-4 py-3">
        <div className="min-w-0">
          <h1
            className="truncate text-[18px] font-semibold text-b-text"
            style={{ letterSpacing: "-0.3px" }}
          >
            {name}
          </h1>
          {dag?.description && (
            <p className="mt-0.5 truncate font-mono text-[11px] text-b-text-dim">
              {dag.description}
            </p>
          )}
        </div>
        {hasInputs && (
          <div className="mt-3">
            <RunConfigForm
              inputs={dag.inputs!}
              workflowName={name!}
              onChange={(values) => {
                configRef.current = values;
              }}
            />
          </div>
        )}
      </div>

      {/* Content */}
      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 border-r border-b-line">
          {dagLoading ? (
            <div className="flex h-full items-center justify-center font-mono text-[11px] text-b-text-dim">
              $ loading dag…
            </div>
          ) : dag ? (
            <WorkflowDAG dagNodes={dag.nodes} dagEdges={dag.edges} />
          ) : (
            <div className="flex h-full items-center justify-center font-mono text-[11px] text-b-red">
              $ failed to load dag
            </div>
          )}
        </div>

        <div className="w-[340px] overflow-y-auto bg-b-bg0 p-3 space-y-3">
          {dag && (
            <BBox title="dag preview">
              <div className="p-2" style={{ height: 160 }}>
                <BDagMini nodes={dag.nodes} edges={dag.edges} />
              </div>
            </BBox>
          )}
          <BBox title="run history">
            <div className="p-2">
              <RunList runs={runs} isLoading={runsLoading} />
            </div>
          </BBox>
        </div>
      </div>

      {runMutation.isError && (
        <div className="border-t border-b-red bg-b-red/10 px-4 py-2 font-mono text-[11px] text-b-red">
          [!] {(runMutation.error as Error).message}
        </div>
      )}
    </div>
  );
}
