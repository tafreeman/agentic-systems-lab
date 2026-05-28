import { memo, useEffect, useState } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { StepStatus } from "../../api/types";

export interface StepNodeData {
  label: string;
  agent: string | null;
  description: string;
  tier: string | null;
  status: StepStatus;
  startTime?: string;
  durationMs?: number;
  modelUsed?: string;
  tokensUsed?: number;
  /** Optional split input token count. Displayed when present. */
  tokensIn?: number;
  /** Optional split output token count. Displayed when present. */
  tokensOut?: number;
  modelInferred?: boolean;
  error?: string | null;
  /**
   * When true, the WebSocket stream is disconnected — live animations are
   * paused to signal that what's on screen may no longer reflect reality.
   */
  disconnected?: boolean;
}

/**
 * ASCII status glyphs for the B2 redesign. Width-stable (4 printable chars
 * between brackets) so the header row aligns across statuses.
 */
const ASCII_STATUS: Record<StepStatus, string> = {
  pending: "[...]",
  running: "[RUN]",
  success: "[OK ]",
  failed: "[ERR]",
  skipped: "[SKP]",
  cancelled: "[---]",
};

function StepNodeComponent({ id, data }: NodeProps) {
  const nodeData = data as unknown as StepNodeData;
  const { status, label, tier, tokensIn, tokensOut, tokensUsed, error } =
    nodeData;

  const isLiveRunning = status === "running" && !nodeData.disconnected;
  const runningClass = isLiveRunning ? "step-node--running" : "";

  const showTokens =
    tokensIn != null || tokensOut != null || tokensUsed != null;
  const showStreamingBar = isLiveRunning;

  return (
    <>
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-b-line !border-b-bg1 !border !w-2 !h-2"
      />

      <div
        data-testid={`dag-node-${id}`}
        className={`step-node ${runningClass} relative rounded-sm border bg-b-bg1 px-3 py-2 min-w-[220px] max-w-[280px] font-mono text-[11px] text-b-text transition-colors duration-200`}
        style={{
          borderColor: "rgb(var(--b-line))",
        }}
      >
        {/* Region 1: ASCII status + name + tier pill */}
        <div className="flex items-center gap-2">
          <span
            data-testid="step-node-status"
            className="tabular-nums tracking-tight"
            style={{ color: resolveStatusColor(status) }}
          >
            {ASCII_STATUS[status] ?? "[...]"}
          </span>
          <span className="flex-1 truncate text-b-text" title={label}>
            {label}
          </span>
          {tier && (
            <span
              data-testid="step-node-tier"
              className="rounded-sm border px-1.5 py-0 text-[10px] uppercase tracking-wider"
              style={{
                borderColor: "rgb(var(--b-line))",
                color: "rgb(var(--b-purple))",
                backgroundColor: "rgb(var(--b-bg2))",
              }}
            >
              {tier}
            </span>
          )}
        </div>

        {/* Region 2: token in/out counts */}
        {showTokens && (
          <div
            data-testid="step-node-tokens"
            className="mt-1.5 flex items-center gap-3 text-b-text-dim"
          >
            {tokensIn != null || tokensOut != null ? (
              <>
                {tokensIn != null && (
                  <span className="tabular-nums">
                    in: {tokensIn.toLocaleString()}
                  </span>
                )}
                {tokensOut != null && (
                  <span className="tabular-nums">
                    out: {tokensOut.toLocaleString()}
                  </span>
                )}
              </>
            ) : (
              tokensUsed != null && (
                <span className="tabular-nums">
                  tokens: {tokensUsed.toLocaleString()}
                </span>
              )
            )}
            <StepTimer
              status={status}
              startTime={nodeData.startTime}
              durationMs={nodeData.durationMs}
            />
          </div>
        )}

        {/* Region 3: streaming bar (running only, connected only) */}
        {showStreamingBar && <StreamingBar />}

        {/* Region 4: error line (failure only) */}
        {status === "failed" && error && (
          <div
            data-testid="step-node-error"
            className="mt-1.5 max-h-[60px] overflow-y-auto break-words text-[10px]"
            style={{ color: "rgb(var(--b-red))" }}
          >
            {error}
          </div>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-b-line !border-b-bg1 !border !w-2 !h-2"
      />
    </>
  );
}

/** Resolve a theme-aware status color via CSS variables only. */
function resolveStatusColor(status: StepStatus): string {
  switch (status) {
    case "running":
      return "rgb(var(--b-clay))";
    case "success":
      return "rgb(var(--b-green))";
    case "failed":
      return "rgb(var(--b-red))";
    case "skipped":
      return "rgb(var(--b-amber))";
    case "cancelled":
      return "rgb(var(--b-text-dim))";
    case "pending":
    default:
      return "rgb(var(--b-text-dim))";
  }
}

/** Small 8-cell ASCII-ish streaming bar that animates while the step runs. */
function StreamingBar() {
  const [phase, setPhase] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setPhase((p) => (p + 1) % 8), 150);
    return () => clearInterval(id);
  }, []);

  const CELLS = 8;
  const FILLED = 4;
  const cells = Array.from({ length: CELLS }, (_, i) => {
    const active = (i + phase) % CELLS < FILLED;
    return active ? "\u25AE" : "\u25AF"; // ▮ / ▯
  }).join("");

  return (
    <div
      data-testid="step-node-streaming-bar"
      className="mt-1.5 flex items-center gap-2 tabular-nums"
      style={{ color: "rgb(var(--b-clay))" }}
    >
      <span>{cells}</span>
      <span className="text-b-text-dim">streaming</span>
    </div>
  );
}

/** Live elapsed timer (running) or final duration display. */
function StepTimer({
  status,
  startTime,
  durationMs,
}: Readonly<{
  status: StepStatus;
  startTime?: string;
  durationMs?: number;
}>) {
  const [elapsed, setElapsed] = useState<number | null>(null);

  useEffect(() => {
    if (status !== "running" || !startTime) {
      setElapsed(null);
      return;
    }
    const origin = new Date(startTime).getTime();
    setElapsed(Date.now() - origin);
    const id = setInterval(() => setElapsed(Date.now() - origin), 250);
    return () => clearInterval(id);
  }, [status, startTime]);

  const ms =
    status === "running" && elapsed != null ? elapsed : durationMs ?? null;

  if (ms == null) return null;

  return <span className="tabular-nums">{formatMs(ms)}</span>;
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const totalSec = ms / 1000;
  if (totalSec < 60) return `${totalSec.toFixed(1)}s`;
  const m = Math.floor(totalSec / 60);
  const s = Math.floor(totalSec % 60);
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

export default memo(StepNodeComponent);
