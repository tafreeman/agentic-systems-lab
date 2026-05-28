"""Adapter layer — pluggable execution engine backends.

Provides :func:`get_registry` for discovering and instantiating
execution engine adapters.  Built-in adapters are auto-registered
on import.

Usage::

    from agentic_v2.adapters import get_registry

    registry = get_registry()
    engine = registry.get_adapter("native")
    result = await engine.execute(dag, ctx)
"""

from ..langchain.dependencies import (
    is_missing_langchain_dependency_error,
)

# Auto-register built-in adapters
from . import native as _native_adapter
from .registry import AdapterRegistry, get_registry

try:
    from . import langchain as _langchain_adapter
except ImportError as exc:  # pragma: no cover — optional dependency
    if not is_missing_langchain_dependency_error(exc):
        raise

__all__ = [
    "AdapterRegistry",
    "get_registry",
]
