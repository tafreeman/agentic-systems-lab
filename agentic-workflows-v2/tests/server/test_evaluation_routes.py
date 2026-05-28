"""Route-level tests for /api/eval/datasets/sample-list pagination.

Covers the two Sprint B #4 bugs:

* **Bug A** — ``sample_count`` missing from meta caused the route to cap
  every repository dataset at 1 sample. We assert the response exposes
  the authoritative size from ``BENCHMARK_DEFINITIONS``.
* **Bug B** — N+1 loader pattern. We assert the underlying
  ``load_benchmark`` is called **once** per page, not ``limit`` times.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import pytest
from agentic_v2.server import datasets as datasets_module
from agentic_v2.server.app import create_app
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


@dataclass
class _FakeTask:
    """Minimal stand-in for ``tools.agents.benchmarks.loader.BenchmarkTask``.

    The route code path only consumes ``.to_dict()`` or ``asdict()``, so a
    plain dataclass with a ``to_dict`` method is sufficient.
    """

    task_id: str
    benchmark_id: str
    prompt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "benchmark_id": self.benchmark_id,
            "prompt": self.prompt,
        }


@dataclass
class _FakeBenchmarkDefinition:
    """Minimal stand-in for a ``BenchmarkDefinition`` — only ``size`` is read."""

    size: int = 164


# ---------------------------------------------------------------------------
# Unit tests — exercise the batch helper through the route without HF
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_humaneval_env(monkeypatch: pytest.MonkeyPatch):
    """Patch ``load_benchmark`` and ``BENCHMARK_DEFINITIONS`` for offline use.

    The fixture also records every call to ``load_benchmark`` so tests can
    assert the N+1 fix holds.
    """
    call_log: list[dict[str, Any]] = []
    total = 164

    def fake_load_benchmark(
        benchmark_id: str,
        limit: int | None = None,
        offset: int = 0,
        **_kwargs: Any,
    ) -> list[_FakeTask]:
        call_log.append(
            {"benchmark_id": benchmark_id, "limit": limit, "offset": offset}
        )
        start = max(offset, 0)
        stop = min(start + (limit or total), total)
        return [
            _FakeTask(
                task_id=f"HumanEval/{idx}",
                benchmark_id=benchmark_id,
                prompt=f"prompt-{idx}",
            )
            for idx in range(start, stop)
        ]

    fake_registry = {"humaneval": _FakeBenchmarkDefinition(size=total)}

    # Patch the loader at its real module path so the lazy imports inside
    # ``datasets.load_repository_dataset_samples`` pick up the fake.
    import tools.agents.benchmarks.datasets as bench_datasets
    import tools.agents.benchmarks.loader as bench_loader

    monkeypatch.setattr(bench_loader, "load_benchmark", fake_load_benchmark)
    monkeypatch.setattr(
        bench_datasets, "BENCHMARK_DEFINITIONS", fake_registry, raising=False
    )
    return call_log


def test_sample_list_repository_page_has_correct_size_and_indexes(
    fake_humaneval_env: list[dict[str, Any]],
) -> None:
    """First page returns exactly ``limit`` summaries with sequential indexes."""
    app = create_app()
    client = TestClient(app)

    response = client.get(
        "/api/eval/datasets/sample-list",
        params={
            "dataset_source": "repository",
            "dataset_id": "humaneval",
            "offset": 0,
            "limit": 20,
        },
    )
    assert response.status_code == 200, response.text

    payload = response.json()
    assert payload["sample_count"] == 164
    assert payload["offset"] == 0
    assert payload["limit"] == 20
    assert len(payload["samples"]) == 20

    indexes = [summary["sample_index"] for summary in payload["samples"]]
    assert indexes == list(range(0, 20))


def test_sample_list_repository_middle_page_indexes_are_absolute(
    fake_humaneval_env: list[dict[str, Any]],
) -> None:
    """Offset into the middle returns the requested slice, not 0..limit."""
    app = create_app()
    client = TestClient(app)

    response = client.get(
        "/api/eval/datasets/sample-list",
        params={
            "dataset_source": "repository",
            "dataset_id": "humaneval",
            "offset": 10,
            "limit": 5,
        },
    )
    assert response.status_code == 200, response.text

    payload = response.json()
    assert payload["sample_count"] == 164
    assert [s["sample_index"] for s in payload["samples"]] == [10, 11, 12, 13, 14]


def test_sample_list_repository_calls_load_benchmark_exactly_once(
    fake_humaneval_env: list[dict[str, Any]],
) -> None:
    """Bug B regression: pagination must NOT call load_benchmark per row."""
    app = create_app()
    client = TestClient(app)

    response = client.get(
        "/api/eval/datasets/sample-list",
        params={
            "dataset_source": "repository",
            "dataset_id": "humaneval",
            "offset": 50,
            "limit": 20,
        },
    )
    assert response.status_code == 200, response.text
    assert len(fake_humaneval_env) == 1, (
        "Expected a single load_benchmark() call for the whole page, "
        f"got {len(fake_humaneval_env)}: {fake_humaneval_env}"
    )
    assert fake_humaneval_env[0]["offset"] == 50
    assert fake_humaneval_env[0]["limit"] == 20


def test_sample_count_meta_populated_from_registry(
    fake_humaneval_env: list[dict[str, Any]],
) -> None:
    """Bug A regression: meta.sample_count must reflect the canonical size."""
    _, meta = datasets_module.load_repository_dataset_sample(
        "humaneval", sample_index=0
    )
    assert meta["sample_count"] == 164
    assert meta["dataset_id"] == "humaneval"


# ---------------------------------------------------------------------------
# Integration test — real HuggingFace fetch, skipped offline
# ---------------------------------------------------------------------------


def _hf_datasets_available() -> bool:
    """Return True when the optional ``datasets`` extra is importable."""
    try:
        import datasets as _datasets

        _ = _datasets.__name__
    except ImportError:
        return False
    return True


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("HF_HUB_OFFLINE") == "1"
    or os.environ.get("AGENTIC_SKIP_NETWORK_TESTS") == "1"
    or not _hf_datasets_available(),
    reason="Integration test requires network + `datasets` extra (pip install datasets)",
)
def test_sample_list_humaneval_real_fetch() -> None:
    """End-to-end: pull humaneval from HuggingFace through the route."""
    app = create_app()
    client = TestClient(app)

    response = client.get(
        "/api/eval/datasets/sample-list",
        params={
            "dataset_source": "repository",
            "dataset_id": "humaneval",
            "offset": 0,
            "limit": 5,
        },
    )
    assert response.status_code == 200, response.text

    payload = response.json()
    assert payload["sample_count"] == 164
    assert len(payload["samples"]) == 5
    assert [s["sample_index"] for s in payload["samples"]] == [0, 1, 2, 3, 4]


# ---------------------------------------------------------------------------
# Unit tests — local dataset batch loader
# ---------------------------------------------------------------------------


def test_local_dataset_batch_loader_slices_in_memory(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Local batch loader reads the JSON once and slices the list."""
    import json

    dataset_dir = tmp_path / "tests" / "fixtures" / "datasets"
    dataset_dir.mkdir(parents=True)
    dataset_path = dataset_dir / "synthetic.json"
    dataset_path.write_text(
        json.dumps([{"task_id": f"t-{i}", "prompt": f"p-{i}"} for i in range(50)]),
        encoding="utf-8",
    )

    monkeypatch.setattr(datasets_module, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(datasets_module, "_WORKSPACE_ROOT", tmp_path)

    dataset_ref = "tests/fixtures/datasets/synthetic.json"
    batch = datasets_module.load_local_dataset_samples(
        dataset_ref, offset=10, limit=5
    )

    assert len(batch) == 5
    assert [meta["sample_index"] for _, meta in batch] == [10, 11, 12, 13, 14]
    assert all(meta["sample_count"] == 50 for _, meta in batch)
    assert [sample["task_id"] for sample, _ in batch] == [
        "t-10",
        "t-11",
        "t-12",
        "t-13",
        "t-14",
    ]
