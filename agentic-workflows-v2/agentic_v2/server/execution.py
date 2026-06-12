"""Workflow execution orchestration.

Contains the background-task lifecycle for running workflows, streaming
LangGraph events via WebSocket, and optionally scoring with an LLM judge.

Public API
----------
_get_lc_runner
    Lazily initialise the LangChain runner singleton.
_resolve_judge_model
    Resolve the LLM model identifier for the evaluation judge.
_merge_stream_state
    Merge a streamed LangGraph node update into aggregate state.
_run_via_native_adapter
    Execute a workflow through a non-LangChain adapter.
_stream_and_run
    Stream LangGraph events then build a WorkflowResult.
_run_and_evaluate
    Full background task: execute, evaluate, broadcast, log.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, Mapping

from ..contracts import StepStatus, WorkflowResult
from ..integrations.otel import create_trace_adapter
from ..workflows.run_logger import RunLogger
from . import websocket
from .evaluation import score_workflow_result
from .judge import LLMJudge
from .result_normalization import as_dict, extract_tokens, normalize_workflow_result

logger = logging.getLogger(__name__)


def load_workflow_config(
    name: str,
    definitions_dir: Path | None = None,
) -> Any:
    """Lazy shim: defers the deprecated langchain import until actually called.

    Exposes ``load_workflow_config`` as a patchable module-level attribute
    without importing ``agentic_v2.langchain`` at module load time (which
    would trigger its :class:`DeprecationWarning`).
    """
    from ..langchain.config import load_workflow_config as _impl  # lazy — no import-time DeprecationWarning

    if definitions_dir is not None:
        return _impl(name, definitions_dir)
    return _impl(name)


# LangChain runner — lazily initialised on first langchain-adapter request
# so that importing this module never triggers the LangGraph DeprecationWarning.
_lc_runner = None
run_logger = RunLogger()


def _get_lc_runner() -> Any:
    """Lazily import and initialise the LangChain runner singleton.

    All ``agentic_v2.langchain`` imports are deferred to here so that
    importing ``agentic_v2.server.execution`` (and by extension starting
    the server) never triggers the :class:`DeprecationWarning` emitted by
    ``agentic_v2/langchain/__init__.py``.  The warning fires only when an
    explicit ``adapter=langchain`` request arrives.

    Raises:
        fastapi.HTTPException: (501) if the langchain extras are not
            installed or the optional dependencies are missing.
    """
    global _lc_runner
    from ..langchain.dependencies import (
        is_missing_langchain_dependency_error,
        to_missing_langchain_dependency_error,
    )

    try:
        from ..langchain import WorkflowRunner as LangChainRunner
    except ImportError as exc:
        from fastapi import HTTPException

        if is_missing_langchain_dependency_error(exc):
            err = to_missing_langchain_dependency_error()
            raise HTTPException(status_code=501, detail=str(err)) from exc
        raise

    if _lc_runner is None:
        from ..langchain import WorkflowRunner as _LangChainRunner

        _lc_runner = _LangChainRunner(trace_adapter=create_trace_adapter())
    return _lc_runner


def _resolve_judge_model() -> str | None:
    """Resolve the LLM model identifier for the evaluation judge.

    Checks environment variables in priority order:
    ``AGENTIC_JUDGE_MODEL``, ``AGENTIC_MODEL_TIER_2``, ``AGENTIC_MODEL_TIER_1``.

    Returns:
        Model identifier string, or None if no judge model is configured.
    """
    for key in ("AGENTIC_JUDGE_MODEL", "AGENTIC_MODEL_TIER_2", "AGENTIC_MODEL_TIER_1"):
        value = os.getenv(key)  # env-pass: dynamic model tier config
        if value and value.strip():
            return value.strip()
    return None


def _merge_stream_state(
    aggregated: dict[str, Any], node_update: Mapping[str, Any]
) -> None:
    """Merge a streamed LangGraph node update into the aggregate run state.

    Incrementally updates ``context``, ``outputs``, ``steps``, and
    ``errors`` in the ``aggregated`` dict.  Step data is merged
    key-by-key so partial updates do not overwrite earlier fields.

    Args:
        aggregated: Mutable aggregate state dict (modified in place).
        node_update: Single LangGraph stream update mapping.
    """
    for payload in node_update.values():
        if not isinstance(payload, Mapping):
            continue

        context = payload.get("context")
        if isinstance(context, Mapping):
            aggregated["context"].update(context)

        outputs = payload.get("outputs")
        if isinstance(outputs, Mapping):
            aggregated["outputs"].update(outputs)

        steps = payload.get("steps")
        if isinstance(steps, Mapping):
            for step_name, step_data in steps.items():
                if not isinstance(step_data, Mapping):
                    continue
                existing = aggregated["steps"].get(step_name)
                if isinstance(existing, dict):
                    merged = dict(existing)
                    merged.update(step_data)
                    aggregated["steps"][step_name] = merged
                else:
                    aggregated["steps"][step_name] = dict(step_data)

        errors = payload.get("errors")
        if isinstance(errors, list):
            for err in errors:
                if err:
                    aggregated["errors"].append(str(err))


async def _run_via_native_adapter(
    adapter_name: str,
    workflow_name: str,
    run_id: str,
    workflow_inputs: dict[str, Any],
    on_update: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> WorkflowResult:
    """Execute a workflow through a non-LangChain adapter and return a normalised
    :class:`WorkflowResult`.

    Args:
        adapter_name: Registered adapter name (e.g. ``"native"``).
        workflow_name: Name of the workflow to execute.
        run_id: Unique run identifier (used as ``workflow_id``).
        workflow_inputs: Input variables for the workflow.

    Returns:
        A fully populated :class:`WorkflowResult`.
    """
    from ..adapters import get_registry
    from ..engine.context import ExecutionContext
    from ..workflows.loader import WorkflowLoader

    loader = WorkflowLoader()
    workflow_def = loader.load(workflow_name)
    dag = workflow_def.dag
    ctx = ExecutionContext(_variables=dict(workflow_inputs), workflow_id=run_id)

    engine = get_registry().get_adapter(adapter_name)
    raw = await engine.execute(
        dag,
        ctx,
        on_update=on_update,
        thread_id=run_id,
    )

    return normalize_workflow_result(raw, workflow_name=workflow_name, run_id=run_id)


async def _stream_and_run(
    workflow_name: str,
    run_id: str,
    workflow_inputs: dict[str, Any],
    adapter_name: str = "native",
) -> WorkflowResult:
    """Stream LangGraph node events to WebSocket clients, then build a final
    WorkflowResult.

    When *adapter_name* is ``"langchain"``, iterates over the
    LangGraph async stream, broadcasting ``step_start`` and ``step_end``
    events via WebSocket.  Falls back to a non-streaming ``invoke`` if the
    stream raises an exception.

    Args:
        workflow_name: Name of the workflow to execute.
        run_id: Unique run identifier.
        workflow_inputs: Input variables for the workflow.
        adapter_name: Execution adapter to use (default ``"native"``).

    Returns:
        The completed :class:`WorkflowResult`.
    """
    if adapter_name != "langchain":

        async def _broadcast_native_update(event: dict[str, Any]) -> None:
            await websocket.manager.broadcast(run_id, event)

        return await _run_via_native_adapter(
            adapter_name,
            workflow_name,
            run_id,
            workflow_inputs,
            on_update=_broadcast_native_update,
        )

    started_perf = time.perf_counter()
    step_start_times: dict[str, float] = {}
    last_status_by_step: dict[str, str] = {}
    aggregated_state: dict[str, Any] = {
        "context": {},
        "steps": {},
        "outputs": {},
        "errors": [],
    }

    try:
        async for node_update in _get_lc_runner().astream(
            workflow_name,
            thread_id=run_id,
            **workflow_inputs,
        ):
            if not isinstance(node_update, Mapping):
                continue

            _merge_stream_state(aggregated_state, node_update)
            now = datetime.now(timezone.utc).isoformat()

            for step_state in node_update.values():
                if not isinstance(step_state, Mapping):
                    continue
                step_map = step_state.get("steps")
                if not isinstance(step_map, Mapping):
                    continue

                for step_name, step_data in step_map.items():
                    if not isinstance(step_data, Mapping):
                        continue

                    status = str(step_data.get("status", "running")).strip().lower()
                    previous_status = last_status_by_step.get(str(step_name))

                    if status in {"running", "pending"}:
                        if previous_status == "running":
                            continue
                        last_status_by_step[str(step_name)] = "running"
                        step_start_times.setdefault(str(step_name), time.time())
                        await websocket.manager.broadcast(
                            run_id,
                            {
                                "type": "step_start",
                                "run_id": run_id,
                                "step": str(step_name),
                                "timestamp": now,
                            },
                        )
                        continue

                    if status not in {"success", "failed", "skipped"}:
                        continue
                    if previous_status == status:
                        continue

                    last_status_by_step[str(step_name)] = status
                    duration_from_state = step_data.get("duration_ms")

                    calc_duration = 0
                    if duration_from_state is not None:
                        calc_duration = int(duration_from_state)
                    else:
                        start_ts_str = step_data.get("start_time")
                        end_ts_str = step_data.get("end_time")
                        if isinstance(start_ts_str, str) and isinstance(
                            end_ts_str, str
                        ):
                            try:
                                st = datetime.fromisoformat(start_ts_str)
                                et = datetime.fromisoformat(end_ts_str)
                                calc_duration = int((et - st).total_seconds() * 1000)
                            except ValueError:
                                pass

                        if calc_duration <= 0:
                            step_start = step_start_times.pop(
                                str(step_name), time.time()
                            )
                            calc_duration = int((time.time() - step_start) * 1000)

                    duration_ms = max(0, calc_duration)

                    metadata_raw = step_data.get("metadata")
                    metadata = metadata_raw if isinstance(metadata_raw, Mapping) else {}
                    model_used = metadata.get("model")
                    if not isinstance(model_used, str):
                        model_used = None
                    tokens_used = extract_tokens(metadata)
                    error_val = step_data.get("error")

                    await websocket.manager.broadcast(
                        run_id,
                        {
                            "type": "step_end",
                            "run_id": run_id,
                            "step": str(step_name),
                            "status": status,
                            "duration_ms": duration_ms,
                            "model_used": model_used,
                            "tokens_used": tokens_used,
                            "tier": step_data.get("tier"),
                            "input": as_dict(step_data.get("inputs")),
                            "output": as_dict(step_data.get("outputs")),
                            "outputs": as_dict(step_data.get("outputs")),
                            "error": str(error_val) if error_val else None,
                            "timestamp": now,
                        },
                    )

        workflow_cfg = load_workflow_config(workflow_name)
        resolved_outputs = _get_lc_runner().resolve_outputs(
            workflow_cfg, aggregated_state
        )
        if not isinstance(resolved_outputs, dict):
            resolved_outputs = {}
        if not resolved_outputs:
            resolved_outputs = as_dict(aggregated_state.get("outputs"))

        token_counts, models_used = _get_lc_runner().extract_metadata(aggregated_state)
        errors = [str(err) for err in aggregated_state.get("errors", []) if err]

        overall_status = StepStatus.SUCCESS
        step_state = aggregated_state.get("steps", {})
        if errors or any(
            isinstance(step_data, Mapping)
            and str(step_data.get("status", "")).strip().lower() == "failed"
            for step_data in step_state.values()
        ):
            overall_status = StepStatus.FAILED

        raw_result = SimpleNamespace(
            steps=step_state,
            token_counts=token_counts,
            models_used=models_used,
            errors=errors,
            overall_status=overall_status,
            elapsed_seconds=max(0.0, time.perf_counter() - started_perf),
            final_output=resolved_outputs,
        )
        return normalize_workflow_result(
            raw_result,
            workflow_name=workflow_name,
            run_id=run_id,
        )
    except Exception as stream_err:
        logger.warning("Streaming failed (%s); falling back to invoke", stream_err)
        fallback = await _get_lc_runner().run(
            workflow_name,
            thread_id=run_id,
            **workflow_inputs,
        )
        return normalize_workflow_result(
            fallback,
            workflow_name=workflow_name,
            run_id=run_id,
        )


async def _run_and_evaluate(
    workflow_name: str,
    run_id: str,
    workflow_inputs: dict[str, Any],
    workflow_def: Any,
    evaluation: Any,
    dataset_sample: dict[str, Any] | None,
    dataset_meta: dict[str, Any] | None,
    adapter_name: str = "native",
) -> None:
    """Background task: execute workflow, optionally evaluate, broadcast
    events, and log.

    Orchestrates the full run lifecycle:
    1. Broadcast ``workflow_start`` event.
    2. Execute via :func:`_stream_and_run` (with WebSocket step events).
    3. Broadcast ``workflow_end`` event.
    4. If evaluation is enabled, score the result and broadcast
       ``evaluation_complete``.
    5. Persist the run log.

    Args:
        workflow_name: Name of the workflow to execute.
        run_id: Unique run identifier.
        workflow_inputs: Input variables for the workflow.
        workflow_def: Loaded workflow definition.
        evaluation: Evaluation settings from the request (or None).
        dataset_sample: Dataset sample dict for scoring (or None).
        dataset_meta: Dataset metadata dict for scoring (or None).
        adapter_name: Execution adapter to use (default ``"native"``).
    """
    try:
        logger.info("Starting background execution for run_id=%s", run_id)
        await websocket.manager.broadcast(
            run_id,
            {
                "type": "workflow_start",
                "run_id": run_id,
                "workflow_name": workflow_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        result = await _stream_and_run(
            workflow_name, run_id, workflow_inputs, adapter_name=adapter_name
        )

        status = result.overall_status.value
        workflow_errors = [
            step.error
            for step in result.steps
            if step.status == StepStatus.FAILED and step.error
        ]
        metadata_errors = result.metadata.get("errors")
        if isinstance(metadata_errors, list):
            workflow_errors.extend(str(err) for err in metadata_errors if err)

        await websocket.manager.broadcast(
            run_id,
            {
                "type": "workflow_end",
                "run_id": run_id,
                "status": status,
                "outputs": result.final_output,
                "elapsed_seconds": (
                    (result.total_duration_ms or 0.0) / 1000.0
                    if result.total_duration_ms is not None
                    else 0.0
                ),
                "errors": workflow_errors,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        scored_evaluation: dict[str, Any] | None = None
        if evaluation and evaluation.enabled:
            await websocket.manager.broadcast(
                run_id,
                {
                    "type": "evaluation_start",
                    "run_id": run_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            judge_model = _resolve_judge_model()
            judge = LLMJudge(model=judge_model) if judge_model else LLMJudge()

            scored_evaluation = score_workflow_result(
                result,
                dataset_meta=dataset_meta,
                dataset_sample=dataset_sample,
                rubric=(evaluation.rubric_id or evaluation.rubric),
                workflow_definition=workflow_def,
                enforce_hard_gates=evaluation.enforce_hard_gates,
                judge=judge,
            )
            await websocket.manager.broadcast(
                run_id,
                {
                    "type": "evaluation_complete",
                    "run_id": run_id,
                    **{
                        k: scored_evaluation[k]
                        for k in (
                            "rubric",
                            "rubric_id",
                            "rubric_version",
                            "weighted_score",
                            "overall_score",
                            "grade",
                            "passed",
                            "pass_threshold",
                            "criteria",
                            "hard_gates",
                            "hard_gate_failures",
                            "step_scores",
                        )
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

        run_logger.log(
            result,
            dataset_meta=dataset_meta,
            workflow_inputs=workflow_inputs,
            extra={
                "evaluation_requested": bool(evaluation and evaluation.enabled),
                "evaluation": scored_evaluation,
            },
        )
        logger.info("Completed background execution for run_id=%s", run_id)
    except Exception as e:
        logger.exception(
            "Error in background execution for run_id=%s",
            run_id,
        )
        await websocket.manager.broadcast(
            run_id,
            {"type": "error", "run_id": run_id, "error": str(e)},
        )
