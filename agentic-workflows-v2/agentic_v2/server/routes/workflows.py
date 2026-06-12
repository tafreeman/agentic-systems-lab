"""Workflow execution, DAG visualization, and evaluation routes.

This is the primary route module, providing:

* ``GET /api/workflows`` -- list available workflow definitions.
* ``GET /api/workflows/{name}/dag`` -- return DAG nodes, edges, and input
  schema for React Flow visualization.
* ``GET /api/workflows/{name}/capabilities`` -- return workflow I/O declarations.
* ``POST /api/run`` -- execute a workflow asynchronously with optional
  dataset-backed evaluation scoring.

Run-history routes (``GET /api/runs``, ``GET /api/runs/summary``,
``GET /api/runs/{filename}``, ``GET /api/runs/{run_id}/stream``) are provided
by :mod:`~agentic_v2.server.routes.runs`.

Evaluation routes (``GET /api/eval/datasets``,
``GET /api/workflows/{name}/preview-dataset-inputs``) are provided by
:mod:`~agentic_v2.server.routes.evaluation_routes`.

Execution orchestration is provided by :mod:`~agentic_v2.server.execution`.
Pure result helpers live in :mod:`~agentic_v2.server.result_normalization`.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from ...contracts import StepStatus
from ...workflows.run_logger import RunLogger


def _lc_config() -> Any:
    """Lazily import and return the agentic_v2.langchain.config module.

    All callers that need the langchain config functions go through this
    helper so that the DeprecationWarning in agentic_v2/langchain/__init__.py
    is only triggered by actual langchain-adapter requests, not on startup.
    """
    from ...langchain import config as _cfg

    return _cfg


def _lc_deps() -> Any:
    """Lazily import agentic_v2.langchain.dependencies."""
    from ...langchain import dependencies as _deps

    return _deps


def load_workflow_config(name: str, definitions_dir: Any = None) -> Any:
    """Module-level shim — delegates to langchain.config.load_workflow_config.

    Defined at module level so test fixtures can monkeypatch this name on
    the ``workflows`` module.  The actual import of the langchain package is
    deferred to the first call, keeping server startup free of the
    DeprecationWarning.
    """
    return _lc_config().load_workflow_config(name)


def load_workflow_document(name: str, definitions_dir: Any = None) -> Any:
    """Module-level shim — delegates to langchain.config.load_workflow_document."""
    return _lc_config().load_workflow_document(name)


def save_workflow_document(name: str, document: Any, definitions_dir: Any = None) -> Any:
    """Module-level shim — delegates to langchain.config.save_workflow_document."""
    return _lc_config().save_workflow_document(name, document)


from ..execution import _run_and_evaluate
from ..models import (
    ListWorkflowsResponse,
    WorkflowEditorRequest,
    WorkflowEditorResponse,
    WorkflowRunRequest,
    WorkflowRunResponse,
    WorkflowValidationResponse,
)
from ..result_normalization import _resolve_evaluation_inputs

logger = logging.getLogger(__name__)
router = APIRouter(tags=["workflows"])
run_logger = RunLogger()


async def _sanitize_inputs(
    request_obj: WorkflowRunRequest,
    app_state: Any,
) -> None:
    """Sanitize workflow inputs if middleware is available.

    Raises HTTPException 400 if inputs are blocked.
    """
    sanitization = getattr(app_state, "sanitization", None)
    if sanitization is None:
        return

    import json

    input_text = json.dumps(request_obj.input_data, default=str)
    result = await sanitization.process(input_text, {"source": "api_run_workflow"})

    if not result.is_safe:
        logger.warning(
            "Workflow input blocked: classification=%s, findings=%d",
            result.classification.value,
            len(result.findings),
        )
        raise HTTPException(
            status_code=400,
            detail=f"Input blocked by security policy: {result.classification.value}",
        )


def _require_langchain_runtime() -> None:
    """Raise 501 if LangChain runtime extras are missing."""
    try:
        from ...langchain import WorkflowRunner
    except ImportError as exc:
        deps = _lc_deps()
        if deps.is_missing_langchain_dependency_error(exc):
            raise HTTPException(
                status_code=501,
                detail=str(deps.to_missing_langchain_dependency_error()),
            ) from exc
        raise


def _compile_workflow_for_validation(config: Any) -> None:
    """Validate workflow graph topology without executing it."""
    try:
        from ...langchain.graph import compile_workflow
    except ImportError as exc:
        deps = _lc_deps()
        if deps.is_missing_langchain_dependency_error(exc):
            raise HTTPException(
                status_code=501,
                detail=str(deps.to_missing_langchain_dependency_error()),
            ) from exc
        raise

    compile_workflow(config, validate_only=True)


def _workflow_editor_response(
    name: str,
    path: str,
    document: dict[str, Any],
    yaml_text: str,
) -> WorkflowEditorResponse:
    cfg = _lc_config()
    config = cfg.validate_workflow_document(document, expected_name=name)
    return WorkflowEditorResponse(
        name=config.name,
        path=path,
        yaml_text=yaml_text,
        document=document,
        step_count=len(config.steps),
    )


@router.get("/workflows", response_model=ListWorkflowsResponse)
async def list_workflows() -> ListWorkflowsResponse:
    """List available workflows."""
    workflows = _lc_config().list_workflows()
    return ListWorkflowsResponse(workflows=workflows)


@router.get("/adapters")
async def list_adapters():
    """List available execution engine adapters.

    Returns:
        JSON object with ``adapters`` key containing a list of registered
        adapter names (e.g. ``["native", "langchain"]``).
    """
    from ...adapters import get_registry

    registry = get_registry()
    names = registry.list_adapters()
    return {"adapters": names}


@router.get("/workflows/{name}/dag")
async def get_workflow_dag(name: str):
    """Return the DAG structure for visualization."""
    try:
        wf = load_workflow_config(name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    nodes = []
    edges = []
    for step in wf.steps:
        nodes.append(
            {
                "id": step.name,
                "agent": step.agent,
                "description": step.description,
                "depends_on": list(step.depends_on),
                "tier": None,  # tier is embedded in agent name (e.g. tier2_reviewer)
            }
        )
        for dep in step.depends_on:
            edges.append({"source": dep, "target": step.name})

    # Include input schema so the UI can render a proper form
    input_schema = []
    for inp_name, inp in wf.inputs.items():
        input_schema.append(
            {
                "name": inp_name,
                "type": inp.type,
                "description": inp.description,
                "default": inp.default,
                "required": inp.required,
                "enum": inp.enum,
            }
        )

    return {
        "name": wf.name,
        "description": wf.description,
        "nodes": nodes,
        "edges": edges,
        "inputs": input_schema,
    }


@router.get("/workflows/{name}/capabilities")
async def get_workflow_capabilities(name: str):
    """Return workflow capability declarations (inputs/outputs)."""
    try:
        wf = load_workflow_config(name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return {
        "workflow": wf.name,
        "capabilities": wf.capabilities,
    }


@router.get("/workflows/{name}/editor", response_model=WorkflowEditorResponse)
async def get_workflow_editor(name: str) -> WorkflowEditorResponse:
    """Return the raw YAML workflow document for editor clients."""
    try:
        path, document, yaml_text = load_workflow_document(name)
        return _workflow_editor_response(name, str(path), document, yaml_text)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/workflows/{name}", response_model=WorkflowEditorResponse)
async def save_workflow_editor(name: str, request: WorkflowEditorRequest) -> WorkflowEditorResponse:
    """Validate and persist a workflow document."""
    try:
        path, persisted_document, _config, yaml_text = save_workflow_document(
            name, request.document
        )
        _lc_config().load_workflow_config.cache_clear()
        return _workflow_editor_response(
            name,
            str(path),
            persisted_document,
            yaml_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Workflow definitions directory is not writable: {exc}",
        ) from exc


@router.post(
    "/workflows/validate",
    response_model=WorkflowValidationResponse,
)
async def validate_workflow_editor(request: WorkflowEditorRequest) -> WorkflowValidationResponse:
    """Validate a workflow document without persisting it."""
    document = request.document
    cfg = _lc_config()
    try:
        if not isinstance(document, dict):
            raise ValueError("Workflow document must be a mapping.")
        expected_name = document.get("name")
        config = cfg.validate_workflow_document(document, expected_name=expected_name)
        _compile_workflow_for_validation(config)
        return WorkflowValidationResponse(
            valid=True,
            name=config.name,
            step_count=len(config.steps),
            yaml_text=cfg.render_workflow_document(document),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/run", response_model=WorkflowRunResponse)
async def run_workflow(
    request: WorkflowRunRequest,
    background_tasks: BackgroundTasks,
    http_request: Request,
):
    """Execute a workflow asynchronously."""
    # Sanitize inputs
    await _sanitize_inputs(request, http_request.app.state)

    adapter_name = request.adapter
    from ...adapters import get_registry as _get_adapter_registry

    try:
        _get_adapter_registry().get_adapter(adapter_name)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown adapter: {adapter_name!r}. "
            f"Available: {_get_adapter_registry().list_adapters()}",
        ) from exc

    if adapter_name == "langchain":
        _require_langchain_runtime()
    try:
        workflow_def = load_workflow_config(request.workflow)
        run_id = request.run_id or f"{workflow_def.name}-{uuid.uuid4().hex[:8]}"
        workflow_inputs = dict(request.input_data)
        evaluation = request.evaluation
        dataset_sample: dict[str, Any] | None = None
        dataset_meta: dict[str, Any] | None = None

        if evaluation and evaluation.enabled:
            workflow_inputs, dataset_sample, dataset_meta = _resolve_evaluation_inputs(
                workflow_def,
                evaluation,
                run_id,
                workflow_inputs,
                artifacts_dir=run_logger.runs_dir / "_inputs",
            )

        background_tasks.add_task(
            _run_and_evaluate,
            request.workflow,
            run_id,
            workflow_inputs,
            workflow_def,
            evaluation,
            dataset_sample,
            dataset_meta,
            adapter_name,
        )
        return WorkflowRunResponse(run_id=run_id, status=StepStatus.PENDING)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
