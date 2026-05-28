"""Core error hierarchy for the agentic workflow system.

All domain-specific exceptions inherit from :class:`AgenticError`,
allowing callers to catch broad or narrow categories.
"""

from __future__ import annotations


class AgenticError(Exception):
    """Base exception for all agentic workflow errors."""


class WorkflowError(AgenticError):
    """Error during workflow execution."""


class StepError(AgenticError):
    """Error during a single step execution."""


class SchemaValidationError(AgenticError):
    """Error during input or configuration validation."""


class AdapterError(AgenticError):
    """Error in an execution engine adapter."""


class AdapterNotFoundError(AdapterError):
    """Requested adapter is not registered."""


class ToolError(AgenticError):
    """Error during tool execution."""


class MemoryStoreError(AgenticError):
    """Error in a memory store operation."""


class ConfigurationError(AgenticError):
    """Error in configuration loading or validation."""
