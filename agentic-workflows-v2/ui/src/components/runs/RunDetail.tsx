import { useState } from "react";
import StatusBadge from "../common/StatusBadge";
import DurationDisplay from "../common/DurationDisplay";
import JsonViewer from "../common/JsonViewer";
import type { StepResult, StepStatus } from "../../api/types";
import { ChevronDown, ChevronRight, Cpu, Timer } from "lucide-react";

interface Props {
  steps: StepResult[];
  selectedStep: string | null;
  onSelectStep: (name: string | null) => void;
}

export default function RunDetailSteps({
  steps,
  selectedStep,
  onSelectStep,
}: Props) {
  return (
    <div className="space-y-2">
      {steps.map((step) => (
        <StepPanel
          key={step.step_name}
          step={step}
          isOpen={selectedStep === step.step_name}
          onToggle={() =>
            onSelectStep(
              selectedStep === step.step_name ? null : step.step_name
            )
          }
        />
      ))}
    </div>
  );
}

function StepPanel({
  step,
  isOpen,
  onToggle,
}: {
  step: StepResult;
  isOpen: boolean;
  onToggle: () => void;
}) {
  const [tab, setTab] = useState<"output" | "input">("output");

  return (
    <div className="rounded-lg border border-white/5 bg-surface-1 overflow-hidden">
      {/* Header */}
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-surface-2/30 transition-colors"
      >
        {isOpen ? (
          <ChevronDown className="h-4 w-4 text-gray-500" />
        ) : (
          <ChevronRight className="h-4 w-4 text-gray-500" />
        )}

        <span className="flex-1 text-sm font-medium text-gray-200">
          {step.step_name}
        </span>

        <div className="flex items-center gap-3 text-xs text-gray-500">
          {step.duration_ms != null && (
            <span className="flex items-center gap-1">
              <Timer className="h-3 w-3" />
              <DurationDisplay ms={step.duration_ms} />
            </span>
          )}
          {step.tokens_used != null && (
            <span className="flex items-center gap-1">
              <Cpu className="h-3 w-3" />
              {step.tokens_used.toLocaleString()}
            </span>
          )}
          {step.model_used && (
            <span className="flex items-center gap-1 text-gray-600">
              {step.model_used}
              {step.metadata?.model_inferred === true && (
                <span className="text-[10px] text-accent-amber/80 italic">(inferred)</span>
              )}
            </span>
          )}
        </div>

        <StatusBadge status={step.status as StepStatus} />
      </button>

      {/* Expanded content */}
      {isOpen && (
        <div className="border-t border-white/5 px-4 py-3">
          {/* Error message */}
          {step.error && (
            <div className="mb-3 rounded-md bg-red-500/10 border border-red-500/20 px-3 py-2 text-sm text-red-400">
              {step.error}
            </div>
          )}

          {/* Tab bar */}
          <div className="mb-3 flex gap-1">
            {(["output", "input"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                  tab === t
                    ? "bg-white/10 text-gray-200"
                    : "text-gray-500 hover:text-gray-300"
                }`}
              >
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </button>
            ))}
          </div>

          {/* Content */}
          <div className="max-h-80 overflow-y-auto rounded-md bg-surface-0 p-3">
            <JsonViewer
              data={tab === "output" ? step.output : step.input}
              defaultExpanded
              maxDepth={3}
            />
          </div>

          {/* Metadata */}
          <div className="mt-3 flex flex-wrap gap-4 text-xs text-gray-600">
            {step.tier && <span>Tier: {step.tier}</span>}
            {step.model_used && <span>Model: {step.model_used}</span>}
            {step.tokens_used != null && (
              <span>Tokens: {step.tokens_used.toLocaleString()}</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
