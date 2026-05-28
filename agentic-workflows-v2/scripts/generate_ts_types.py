#!/usr/bin/env python
"""Dump the ExecutionEvent discriminated union to a committed JSON Schema.

This is the Python half of the Sprint B #3 wire-format drift gate. The
artifact written here (``tests/schemas/events.schema.json``) is consumed by
``ui/scripts/generate-ts-types.mjs`` to produce the TypeScript mirror of
``agentic_v2.contracts.events.ExecutionEvent``.

Source of truth: ``agentic_v2/contracts/events.py``.

Run it manually when editing the event contract:

    cd agentic-workflows-v2
    python scripts/generate_ts_types.py

CI regenerates this file and fails the ``wire-format-drift`` job if the
output does not match what's committed.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter

from agentic_v2.contracts.events import ExecutionEvent

OUT_PATH = (
    Path(__file__).parent.parent / "tests" / "schemas" / "events.schema.json"
)


def main() -> None:
    """Dump the ExecutionEvent JSON Schema to the committed artifact."""
    adapter: TypeAdapter[ExecutionEvent] = TypeAdapter(ExecutionEvent)
    schema = adapter.json_schema()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # sort_keys=True + trailing newline → deterministic output so CI diff
    # stays stable across Python + Pydantic patch versions.
    OUT_PATH.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
