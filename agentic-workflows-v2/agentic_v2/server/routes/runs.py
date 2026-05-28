"""Run history routes for the Agentic Workflows V2 server.

Provides:

* ``GET /api/runs`` -- list past runs with summary metadata.
* ``GET /api/runs/summary`` -- aggregate statistics across runs.
* ``GET /api/runs/{filename}`` -- full run detail with step data.
* ``GET /api/runs/{run_id}/stream`` -- SSE event stream for a running workflow.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ...models.secrets import get_secret
from ...utils.path_safety import is_within_base

# LangChain imports — optional at the package level.
try:
    from ...langchain import load_workflow_config

    _LANGCHAIN_AVAILABLE = True
except ImportError:
    _LANGCHAIN_AVAILABLE = False
from ...workflows.run_logger import RunLogger
from .. import websocket
from ..models import RunsSummaryResponse, RunSummaryModel, RunEvaluationDetailResponse, RunEvaluationDetail

logger = logging.getLogger(__name__)
router = APIRouter(tags=["workflows"])
run_logger = RunLogger()


def _is_within_base(path, base_dir) -> bool:
    """Compatibility shim for tests importing this helper directly."""
    return is_within_base(path, base_dir)


@router.get("/runs", response_model=list[RunSummaryModel])
async def list_runs(
    workflow: str | None = None,
    limit: int = 50,
):
    """List past workflow runs with summary data."""
    paths = run_logger.list_runs(workflow_name=workflow)
    results = []
    # Reverse iterate, take at most limit valid runs
    for p in reversed(paths):
        if len(results) >= limit:
            break
        try:
            record = run_logger.load_run(p)
            # Skip invalid runs (e.g., config files)
            if (
                not isinstance(record, dict)
                or "workflow_name" not in record
                or "status" not in record
            ):
                continue

            extra = record.get("extra") if isinstance(record.get("extra"), dict) else {}
            evaluation = (
                extra.get("evaluation")
                if isinstance(extra.get("evaluation"), dict)
                else {}
            )
            results.append(
                {
                    "filename": p.name,
                    **{
                        k: v
                        for k, v in record.items()
                        if k
                        in (
                            "run_id",
                            "workflow_name",
                            "status",
                            "success_rate",
                            "total_duration_ms",
                            "step_count",
                            "failed_step_count",
                            "start_time",
                            "end_time",
                        )
                    },
                    "evaluation_score": evaluation.get("weighted_score"),
                    "evaluation_grade": evaluation.get("grade"),
                }
            )
        except Exception as e:
            logger.warning("Failed to load run %s: %s", p.name, e)
    return results


@router.get("/runs/summary", response_model=RunsSummaryResponse)
async def runs_summary(workflow: str | None = None):
    """Aggregate stats across runs."""
    return run_logger.summary(workflow_name=workflow)


@router.get("/runs/{filename}")
async def get_run(filename: str):
    """Get full run detail including all step data."""
    base_dir = run_logger.runs_dir
    candidate = (base_dir / filename).resolve()
    if not _is_within_base(candidate, base_dir):
        # Do not leak filesystem layout; treat as not found
        raise HTTPException(status_code=404, detail=f"Run not found: {filename}")
    if not Path(candidate).exists():
        raise HTTPException(status_code=404, detail=f"Run not found: {filename}")

    run_data = run_logger.load_run(candidate)

    # Best-effort retroactive model identification
    # If model_used is missing in the run log, try to infer it from current workflow config
    workflow_name = run_data.get("workflow_name")
    if workflow_name and _LANGCHAIN_AVAILABLE:
        try:
            config = load_workflow_config(workflow_name)
            steps_cfg = {s.name: s for s in config.steps}

            for step in run_data.get("steps", []):
                # Skip if we already have a model
                if step.get("model_used"):
                    continue

                # Skip tier 0 (no model)
                if step.get("tier") == 0:
                    continue

                s_name = step.get("step_name")
                if s_name in steps_cfg:
                    step_cfg = steps_cfg[s_name]

                    # 1. Check specific model override
                    if step_cfg.model_override:
                        val = step_cfg.model_override
                        # Handle "env:VAR|fallback"
                        if val.startswith("env:"):
                            parts = val.split("|", 1)
                            if len(parts) > 1:
                                env_key = parts[0][4:]
                                val = get_secret(env_key, default=parts[1])
                            else:
                                env_key = val[4:]
                                val = get_secret(env_key, default=val)

                        step["model_used"] = val
                        # Mark as inferred (optional, maybe distinct UI style?)
                        step["metadata"] = step.get("metadata", {})
                        step["metadata"]["model_inferred"] = True
        except Exception as exc:
            # Workflow definition might have changed or been deleted; ignore errors
            # but log at debug level for operational diagnostics
            logger.debug(
                "Failed to infer model_used for run %s: %s",
                filename,
                exc,
                exc_info=True,
            )

    return run_data


@router.get("/runs/{filename}/evaluation", response_model=RunEvaluationDetailResponse)
async def get_run_evaluation(filename: str):
    """Get full rubric evaluation detail for a scored workflow run."""
    base_dir = run_logger.runs_dir
    candidate = (base_dir / filename).resolve()
    if not _is_within_base(candidate, base_dir):
        raise HTTPException(status_code=404, detail=f"Run not found: {filename}")
    if not candidate.exists():
        raise HTTPException(status_code=404, detail=f"Run not found: {filename}")

    run_data = run_logger.load_run(candidate)

    extra = run_data.get("extra") or {}
    evaluation_requested = bool(extra.get("evaluation_requested", False))
    evaluation_raw = extra.get("evaluation") if isinstance(extra.get("evaluation"), dict) else None

    evaluation: RunEvaluationDetail | None = None
    if evaluation_raw and evaluation_raw.get("enabled"):
        try:
            evaluation = RunEvaluationDetail.model_validate(evaluation_raw)
        except Exception as exc:
            logger.warning("Failed to parse evaluation for %s: %s", filename, exc)

    return RunEvaluationDetailResponse(
        filename=filename,
        run_id=run_data.get("run_id"),
        workflow_name=run_data.get("workflow_name"),
        status=run_data.get("status"),
        evaluation_requested=evaluation_requested,
        dataset=run_data.get("dataset"),
        evaluation=evaluation,
    )


@router.get("/runs/{run_id}/stream")
async def stream_run_events(run_id: str):
    """SSE stream of execution events for a running workflow."""

    async def event_generator():
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        websocket.manager.register_sse_listener(run_id, queue)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") in {
                        "evaluation_complete",
                        "workflow_end",
                    }:
                        break
                except TimeoutError:
                    yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
        finally:
            websocket.manager.unregister_sse_listener(run_id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
