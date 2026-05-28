"""Structured JSON run logger for workflow evaluations.

Captures per-step and per-workflow data for offline evaluation:
- Step: input, output, model, tier, duration, tokens, errors, retries
- Workflow: status, success_rate, total_duration, dataset metadata

Runs are stored as JSON files under a configurable directory (default: runs/).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..contracts import StepStatus, WorkflowResult

logger = logging.getLogger(__name__)

_DEFAULT_RUNS_DIR = Path(__file__).resolve().parents[3] / "runs"


def _safe_serialize(obj: Any) -> Any:
    """Make an object JSON-serializable."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, StepStatus):
        return obj.value
    # _NullSafe sentinels from expression evaluation should serialize as None
    if type(obj).__name__ == "_NullSafe":
        return None
    if hasattr(obj, "model_dump") and callable(obj.model_dump):
        return obj.model_dump(mode="json")
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


def _truncate(value: Any, max_len: int = 10_000) -> Any:
    """Truncate very long string values for readable logs.

    Default limit is generous (10k chars) so generated code is fully
    captured.  Only truly enormous blobs get trimmed.
    """
    if isinstance(value, str) and len(value) > max_len:
        return value[:max_len] + f"... ({len(value)} chars)"
    if isinstance(value, dict):
        return {k: _truncate(v, max_len) for k, v in value.items()}
    if isinstance(value, list):
        return [_truncate(v, max_len) for v in value]
    return value


def build_step_record(step: Any) -> dict[str, Any]:
    """Build a structured record for a single step."""
    return {
        "step_name": step.step_name,
        "status": (
            step.status.value if hasattr(step.status, "value") else str(step.status)
        ),
        "agent_role": step.agent_role,
        "tier": step.tier,
        "model_used": step.model_used,
        "duration_ms": step.duration_ms,
        "retry_count": step.retry_count,
        "tokens_used": step.metadata.get("tokens_used"),
        "input": _truncate(step.input_data),
        "output": _truncate(step.output_data),
        "error": step.error,
        "error_type": step.error_type,
        "start_time": step.start_time.isoformat() if step.start_time else None,
        "end_time": step.end_time.isoformat() if step.end_time else None,
        "metadata": {k: v for k, v in step.metadata.items() if k != "tokens_used"}
        or None,
    }


def build_run_record(
    result: WorkflowResult,
    *,
    dataset_meta: dict[str, Any] | None = None,
    workflow_inputs: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a complete run record from a WorkflowResult.

    Args:
        result: The completed workflow result.
        dataset_meta: The _meta dict from the dataset adapter (source, task_id, etc.)
        workflow_inputs: The raw inputs passed to the workflow.
        extra: Any additional metadata to attach.
    """
    evaluation_score: float | None = None
    if isinstance(extra, dict):
        evaluation = extra.get("evaluation")
        if isinstance(evaluation, dict):
            weighted = evaluation.get("weighted_score")
            overall = evaluation.get("overall_score")
            if isinstance(weighted, (int, float)):
                evaluation_score = float(weighted)
            elif isinstance(overall, (int, float)):
                evaluation_score = float(overall)

    record: dict[str, Any] = {
        "run_id": result.workflow_id,
        "workflow_name": result.workflow_name,
        "status": result.overall_status.value,
        "score": (
            evaluation_score if evaluation_score is not None else result.success_rate
        ),
        "success_rate": result.success_rate,
        "total_duration_ms": result.total_duration_ms,
        "total_retries": result.total_retries,
        "step_count": len(result.steps),
        "failed_step_count": len(result.failed_steps),
        "start_time": result.start_time.isoformat(),
        "end_time": result.end_time.isoformat() if result.end_time else None,
        "dataset": dataset_meta,
        "inputs": _truncate(workflow_inputs) if workflow_inputs else None,
        "steps": [build_step_record(s) for s in result.steps],
        "final_output": _truncate(result.final_output),
    }

    if extra:
        record["extra"] = extra

    return record


class RunLogger:
    """Persists workflow run records as JSON files.

    Usage:
        rl = RunLogger()               # defaults to runs/ dir
        rl.log(result, dataset_meta={...}, workflow_inputs={...})
    """

    def __init__(self, runs_dir: Path | str | None = None):
        self._runs_dir = Path(runs_dir) if runs_dir else _DEFAULT_RUNS_DIR
        self._runs_dir.mkdir(parents=True, exist_ok=True)

    @property
    def runs_dir(self) -> Path:
        return self._runs_dir

    def log(
        self,
        result: WorkflowResult,
        *,
        dataset_meta: dict[str, Any] | None = None,
        workflow_inputs: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> Path:
        """Serialize a workflow result to a JSON file.

        Returns:
            Path to the written JSON file.
        """
        record = build_run_record(
            result,
            dataset_meta=dataset_meta,
            workflow_inputs=workflow_inputs,
            extra=extra,
        )

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"{ts}_{result.workflow_name}_{result.overall_status.value}.json"
        path = self._runs_dir / filename

        path.write_text(
            json.dumps(record, indent=2, default=_safe_serialize),
            encoding="utf-8",
        )
        logger.info("Run logged: %s", path)
        return path

    def list_runs(self, workflow_name: str | None = None) -> list[Path]:
        """List all logged run files, optionally filtered by workflow name."""
        pattern = f"*_{workflow_name}_*.json" if workflow_name else "*.json"
        return sorted(self._runs_dir.glob(pattern))

    def load_run(self, path: Path) -> dict[str, Any]:
        """Load a run record from disk."""
        return json.loads(path.read_text(encoding="utf-8"))

    def summary(self, workflow_name: str | None = None) -> dict[str, Any]:
        """Quick summary of all logged runs."""
        runs = self.list_runs(workflow_name)
        if not runs:
            return {"total_runs": 0}

        records: list[dict[str, Any]] = []
        for path in runs:
            try:
                record = self.load_run(path)
            except Exception as exc:
                logger.warning("Failed to load run %s: %s", path.name, exc)
                continue

            if not isinstance(record, dict):
                continue

            status = record.get("status")
            workflow = record.get("workflow_name")
            if not isinstance(status, str) or not isinstance(workflow, str):
                # Skip non-run JSON artifacts (for example provider checks/ranking).
                continue

            records.append(record)

        if not records:
            return {"total_runs": 0}

        statuses = [str(r.get("status", "")) for r in records]
        durations = [
            r.get("total_duration_ms")
            for r in records
            if isinstance(r.get("total_duration_ms"), (int, float))
        ]

        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        tokens_30d = 0
        for r in records:
            try:
                start_raw = r.get("start_time")
                if not isinstance(start_raw, str):
                    continue
                start_dt = datetime.fromisoformat(start_raw)
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                if start_dt < cutoff:
                    continue
                for step in r.get("steps", []):
                    t = step.get("tokens_used")
                    if isinstance(t, int):
                        tokens_30d += t
            except Exception:
                continue

        return {
            "total_runs": len(records),
            "success": statuses.count("success"),
            "failed": statuses.count("failed"),
            "avg_duration_ms": sum(durations) / len(durations) if durations else None,
            "workflows": sorted({str(r.get("workflow_name")) for r in records}),
            "tokens_30d": tokens_30d,
        }
