"""Evaluation dataset listing and preview routes.

Provides:

* ``GET /api/eval/datasets`` -- list repository and local datasets for the
  evaluation picker UI.
* ``GET /api/workflows/{workflow_name}/preview-dataset-inputs`` -- preview
  dataset-to-input field mapping before execution.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from ...workflows.run_logger import RunLogger
from ..evaluation import (
    adapt_sample_to_workflow_inputs,
    list_eval_sets,
    list_local_datasets,
    list_repository_datasets,
    load_local_dataset_sample,
    load_local_dataset_samples,
    load_repository_dataset_sample,
    load_repository_dataset_samples,
    match_workflow_dataset,
)
from ..models import (
    DatasetSampleDetailResponse,
    DatasetSampleListResponse,
    DatasetSampleSummary,
    ListEvaluationDatasetsResponse,
)

# LangChain imports — optional.
try:
    from ...langchain import load_workflow_config

    _LANGCHAIN_AVAILABLE = True
except ImportError:
    _LANGCHAIN_AVAILABLE = False

logger = logging.getLogger(__name__)
router = APIRouter(tags=["evaluation"])
run_logger = RunLogger()


def _make_sample_summary(
    sample: dict[str, Any], sample_index: int, meta: dict[str, Any]
) -> DatasetSampleSummary:
    """Build a compact summary from a raw dataset sample."""
    field_names = list(sample.keys())

    sample_id = (
        str(sample.get("id", sample.get("sample_id", sample.get("task_id", ""))))
        or None
    )
    task_id = str(sample.get("task_id", "")) or None

    title = f"Sample {sample_index}"
    for title_key in ("title", "name", "problem", "question", "task"):
        raw = sample.get(title_key)
        if isinstance(raw, str) and raw.strip():
            title = raw[:120]
            break

    summary = ""
    for key in field_names:
        val = sample.get(key)
        if isinstance(val, str) and val.strip() and key not in ("id", "task_id", "sample_id"):
            summary = val[:200]
            break

    return DatasetSampleSummary(
        sample_index=sample_index,
        sample_id=sample_id,
        task_id=task_id,
        title=title,
        summary=summary,
        field_names=field_names,
    )


def _require_langchain() -> None:
    """Raise 501 if langchain extras are missing."""
    if not _LANGCHAIN_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="LangChain extras not installed. Install with: pip install -e '.[langchain]'",
        )


@router.get("/eval/datasets", response_model=ListEvaluationDatasetsResponse)
async def list_evaluation_datasets(workflow: str | None = None):
    """List repository and local dataset options for workflow evaluation."""
    if workflow:
        _require_langchain()
    repository = list_repository_datasets()
    local = list_local_datasets()
    eval_sets = list_eval_sets()

    if workflow:
        try:
            workflow_def = load_workflow_config(workflow)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        filtered_local: list[dict[str, Any]] = []
        for dataset in local:
            try:
                sample, _ = load_local_dataset_sample(dataset["id"], sample_index=0)
            except Exception:
                continue
            compatible, _ = match_workflow_dataset(workflow_def, sample)
            if compatible:
                filtered_local.append(dataset)

        filtered_repository: list[dict[str, Any]] = []
        for dataset in repository:
            try:
                sample, _ = load_repository_dataset_sample(
                    dataset["id"], sample_index=0
                )
            except Exception:
                continue
            compatible, _ = match_workflow_dataset(workflow_def, sample)
            if compatible:
                filtered_repository.append(dataset)

        repository = filtered_repository
        local = filtered_local

    return ListEvaluationDatasetsResponse(
        repository=repository,
        local=local,
        eval_sets=eval_sets,
    )


@router.get("/workflows/{workflow_name}/preview-dataset-inputs")
async def preview_dataset_inputs(
    workflow_name: str,
    dataset_source: str,
    dataset_id: str,
    sample_index: int = 0,
):
    """Preview how dataset sample fields will map to workflow inputs."""
    _require_langchain()
    try:
        workflow_def = load_workflow_config(workflow_name)
    except Exception as exc:
        raise HTTPException(
            status_code=404, detail=f"Workflow not found: {exc}"
        ) from exc

    try:
        if dataset_source == "repository":
            dataset_sample, dataset_meta = load_repository_dataset_sample(
                dataset_id,
                sample_index=sample_index,
            )
        elif dataset_source == "local":
            dataset_sample, dataset_meta = load_local_dataset_sample(
                dataset_id,
                sample_index=sample_index,
            )
        else:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid dataset_source: {dataset_source}",
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    compatible, reasons = match_workflow_dataset(workflow_def, dataset_sample)
    if not compatible:
        return {
            "compatible": False,
            "reasons": reasons,
            "adapted_inputs": {},
            "dataset_meta": dataset_meta,
        }

    adapted_inputs = adapt_sample_to_workflow_inputs(
        workflow_def.inputs,
        dataset_sample,
        run_id="preview",
        artifacts_dir=run_logger.runs_dir / "_inputs",
    )

    return {
        "compatible": True,
        "reasons": [],
        "adapted_inputs": adapted_inputs,
        "dataset_meta": dataset_meta,
    }


@router.get("/eval/datasets/sample-list", response_model=DatasetSampleListResponse)
async def list_dataset_samples(
    dataset_source: str,
    dataset_id: str,
    offset: int = 0,
    limit: int = 20,
    workflow: str | None = None,
):
    """List paginated dataset sample summaries."""
    if dataset_source not in ("repository", "local"):
        raise HTTPException(
            status_code=422, detail=f"Invalid dataset_source: {dataset_source!r}"
        )
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100")
    if offset < 0:
        raise HTTPException(status_code=422, detail="offset must be >= 0")

    try:
        if dataset_source == "repository":
            batch = load_repository_dataset_samples(
                dataset_id, offset=offset, limit=limit
            )
        else:
            batch = load_local_dataset_samples(
                dataset_id, offset=offset, limit=limit
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to load dataset: {exc}"
        ) from exc

    sample_count = 0
    if batch:
        meta_count = batch[0][1].get("sample_count")
        if isinstance(meta_count, int) and meta_count > 0:
            sample_count = meta_count
        else:
            sample_count = len(batch)

    summaries: list[DatasetSampleSummary] = [
        _make_sample_summary(sample, s_meta["sample_index"], s_meta)
        for sample, s_meta in batch
    ]

    return DatasetSampleListResponse(
        dataset_source=dataset_source,
        dataset_id=dataset_id,
        sample_count=sample_count,
        offset=offset,
        limit=limit,
        samples=summaries,
    )


@router.get("/eval/datasets/sample-detail", response_model=DatasetSampleDetailResponse)
async def get_dataset_sample_detail(
    dataset_source: str,
    dataset_id: str,
    sample_index: int = 0,
    workflow: str | None = None,
):
    """Get full detail for a single dataset sample."""
    if dataset_source not in ("repository", "local"):
        raise HTTPException(
            status_code=422, detail=f"Invalid dataset_source: {dataset_source!r}"
        )

    try:
        if dataset_source == "repository":
            sample, meta = load_repository_dataset_sample(
                dataset_id, sample_index=sample_index
            )
        else:
            sample, meta = load_local_dataset_sample(
                dataset_id, sample_index=sample_index
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to load sample: {exc}"
        ) from exc

    field_names = list(sample.keys())
    sample_id = str(sample.get("id", sample.get("sample_id", ""))) or None
    task_id = str(sample.get("task_id", "")) or None

    summary = ""
    for key in field_names:
        val = sample.get(key)
        if isinstance(val, str) and val.strip() and key not in ("id", "task_id", "sample_id"):
            summary = val[:200]
            break

    workflow_preview: dict[str, Any] | None = None
    if workflow and _LANGCHAIN_AVAILABLE:
        try:
            workflow_def = load_workflow_config(workflow)
            compatible, _ = match_workflow_dataset(workflow_def, sample)
            if compatible:
                adapted = adapt_sample_to_workflow_inputs(
                    workflow_def.inputs,
                    sample,
                    run_id="preview",
                    artifacts_dir=run_logger.runs_dir / "_inputs",
                )
                workflow_preview = {"compatible": True, "adapted_inputs": adapted}
            else:
                workflow_preview = {"compatible": False}
        except Exception as exc:
            logger.debug("Workflow preview failed for %s: %s", workflow, exc)

    return DatasetSampleDetailResponse(
        dataset_source=dataset_source,
        dataset_id=dataset_id,
        sample_index=sample_index,
        sample_id=sample_id,
        task_id=task_id,
        field_names=field_names,
        summary=summary,
        sample=sample,
        dataset_meta=meta,
        workflow_preview=workflow_preview,
    )
