import { useState } from "react";
import { Link } from "react-router-dom";
import { FileText, Filter } from "lucide-react";
import StatusBadge from "../common/StatusBadge";
import DurationDisplay from "../common/DurationDisplay";
import type { RunSummary, StepStatus } from "../../api/types";

interface Props {
  runs: RunSummary[] | undefined;
  isLoading: boolean;
}

export default function RunList({ runs, isLoading }: Props) {
  const [statusFilter, setStatusFilter] = useState<string>("all");

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="card animate-pulse h-16" />
        ))}
      </div>
    );
  }

  const filtered =
    statusFilter === "all"
      ? runs
      : runs?.filter((r) => r.status === statusFilter);

  return (
    <div>
      {/* Filters */}
      <div className="mb-4 flex items-center gap-2">
        <Filter className="h-4 w-4 text-gray-500" />
        {["all", "success", "failed"].map((f) => (
          <button
            key={f}
            onClick={() => setStatusFilter(f)}
            className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
              statusFilter === f
                ? "bg-accent-blue/20 text-accent-blue"
                : "text-gray-500 hover:bg-white/5 hover:text-gray-300"
            }`}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-lg border border-white/5">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-white/5 bg-surface-2/50">
              <th className="px-4 py-3 text-xs font-medium text-gray-500">
                Workflow
              </th>
              <th className="px-4 py-3 text-xs font-medium text-gray-500">
                Status
              </th>
              <th className="px-4 py-3 text-xs font-medium text-gray-500">
                Steps
              </th>
              <th className="px-4 py-3 text-xs font-medium text-gray-500">
                Duration
              </th>
              <th className="px-4 py-3 text-xs font-medium text-gray-500">
                Score
              </th>
              <th className="px-4 py-3 text-xs font-medium text-gray-500">
                Time
              </th>
            </tr>
          </thead>
          <tbody>
            {filtered?.length === 0 && (
              <tr>
                <td
                  colSpan={6}
                  className="px-4 py-8 text-center text-gray-600"
                >
                  No runs found
                </td>
              </tr>
            )}
            {filtered?.map((run) => (
              <tr
                key={run.filename}
                className="border-b border-white/5 transition-colors hover:bg-surface-2/30"
              >
                <td className="px-4 py-3">
                  <Link
                    to={`/runs/${run.filename}`}
                    className="flex items-center gap-2 text-gray-200 hover:text-accent-blue"
                  >
                    <FileText className="h-4 w-4 text-gray-600" />
                    <div>
                      <div className="font-medium">
                        {run.workflow_name ?? "Unknown"}
                      </div>
                      <div className="text-xs text-gray-600">
                        {run.run_id ?? run.filename}
                      </div>
                    </div>
                  </Link>
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={(run.status ?? "pending") as StepStatus} />
                </td>
                <td className="px-4 py-3 text-gray-400">
                  {run.step_count ?? "--"}
                  {run.failed_step_count
                    ? ` (${run.failed_step_count} failed)`
                    : ""}
                </td>
                <td className="px-4 py-3">
                  <DurationDisplay
                    ms={run.total_duration_ms}
                    className="text-gray-400"
                  />
                </td>
                <td className="px-4 py-3 text-xs">
                  {run.evaluation_score != null ? (
                    <span className="rounded bg-amber-500/10 px-2 py-1 text-amber-300">
                      {run.evaluation_score.toFixed(1)}
                    </span>
                  ) : (
                    <span className="text-gray-600">--</span>
                  )}
                </td>
                <td className="px-4 py-3 text-xs text-gray-600">
                  {run.start_time
                    ? new Date(run.start_time).toLocaleString()
                    : "--"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
