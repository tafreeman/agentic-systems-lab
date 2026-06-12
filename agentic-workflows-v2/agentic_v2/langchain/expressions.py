"""Expression evaluator for YAML conditions.

Evaluates ``${...}`` expressions from YAML ``when`` / ``loop_until``
fields against the current LangGraph ``WorkflowState``.

This is a *minimal* reimplementation that works directly on the state
dict rather than requiring the old ``ExecutionContext``.
"""

from __future__ import annotations

import ast
import operator
import re
from typing import Any

# ${...} extraction pattern
_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")

# coalesce(...) pattern inside an expression
_COALESCE_PATTERN = re.compile(r"^coalesce\((.+)\)$", re.DOTALL)


def evaluate_condition(expr: str | None, state: dict[str, Any]) -> bool:
    """Evaluate a YAML condition expression against workflow state.

    Supports:
    - Variable access: ``${inputs.code_file}``
    - Step outputs: ``${steps.parse_code.outputs.ast}``
    - Comparisons: ``${inputs.review_depth} != 'quick'``
    - Boolean: ``${context.is_valid}``
    - ``in`` operator: ``${steps.review.outputs.status} in ['APPROVED']``

    Returns ``True`` if the condition is met, ``False`` otherwise.
    """
    if not expr or not isinstance(expr, str):
        return True

    expr = expr.strip()

    # Replace all ${...} references with resolved values
    resolved = _VAR_PATTERN.sub(
        lambda m: repr(_resolve_path(m.group(1).strip(), state)),
        expr,
    )

    # Safety: only allow a restricted AST; walk it without eval()
    try:
        tree = ast.parse(resolved, mode="eval")
        _validate_ast(tree.body)
        result = _eval_node(tree.body)
        return bool(result)
    except Exception:
        return False


def resolve_expression(expr: Any, state: dict[str, Any]) -> Any:
    """Resolve a ``${...}`` expression to its value.

    Handles:
    - Simple paths: ``${steps.x.outputs.y}``
    - ``coalesce()``: ``${coalesce(a.b, c.d)}`` → first non-None
    - Dicts: recursively resolves each leaf value
    - Lists: recursively resolves each element
    - Non-strings: returned as-is
    """
    if isinstance(expr, dict):
        return {k: resolve_expression(v, state) for k, v in expr.items()}
    if isinstance(expr, list):
        return [resolve_expression(v, state) for v in expr]
    if not isinstance(expr, str):
        return expr
    expr = expr.strip()
    match = _VAR_PATTERN.fullmatch(expr)
    if match:
        inner = match.group(1).strip()
        return _resolve_coalesce_or_path(inner, state)
    return expr


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_coalesce_or_path(inner: str, state: dict[str, Any]) -> Any:
    """Resolve a coalesce(...) call or a simple dotted path."""
    coal_match = _COALESCE_PATTERN.match(inner)
    if coal_match:
        args = [a.strip() for a in coal_match.group(1).split(",")]
        for arg in args:
            val = _resolve_path(arg, state)
            if val is not None:
                return val
        return None
    return _resolve_path(inner, state)


def _resolve_path(path: str, state: dict[str, Any]) -> Any:
    """Walk a dotted path like ``steps.parse_code.outputs.ast``."""
    parts = path.split(".")
    current: Any = state

    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return None

        if current is None:
            return None

    return current


_ALLOWED_AST_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Set,
    ast.Name,
    ast.Load,  # context node for List/Tuple/Set/Name
    ast.And,
    ast.Or,
    ast.Not,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
    ast.Add,
    ast.Sub,
)

_BINOP_OPS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
}
_UNARYOP_OPS: dict[type, Any] = {
    ast.Not: operator.not_,
}
_CMPOP_OPS: dict[type, Any] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

# Names available in the post-substitution expression (True/False/None
# are builtins but may appear as ast.Name nodes in older Python versions;
# in 3.8+ they are ast.Constant, but keep for robustness).
_SAFE_NAMES: dict[str, Any] = {"True": True, "False": False, "None": None}


def _eval_node(node: ast.expr) -> Any:
    """Recursively evaluate a pre-validated AST node without using eval().

    The input expression has already had all ``${...}`` tokens replaced
    with ``repr()`` literals, so only constants, containers, comparisons,
    boolean ops, and simple names (True/False/None) appear.

    Args:
        node: A validated AST expression node.

    Returns:
        The computed value.

    Raises:
        ValueError: For disallowed node types.
    """
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        if node.id not in _SAFE_NAMES:
            raise ValueError(f"Unsupported name in expression: {node.id!r}")
        return _SAFE_NAMES[node.id]

    if isinstance(node, ast.List):
        return [_eval_node(elt) for elt in node.elts]

    if isinstance(node, ast.Tuple):
        return tuple(_eval_node(elt) for elt in node.elts)

    if isinstance(node, ast.Set):
        return {_eval_node(elt) for elt in node.elts}

    if isinstance(node, ast.BinOp):
        op_fn = _BINOP_OPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"Unsupported binary operator: {type(node.op).__name__}")
        return op_fn(_eval_node(node.left), _eval_node(node.right))

    if isinstance(node, ast.UnaryOp):
        op_fn = _UNARYOP_OPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
        return op_fn(_eval_node(node.operand))

    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            result: Any = True
            for value_node in node.values:
                result = _eval_node(value_node)
                if not result:
                    return result
            return result
        if isinstance(node.op, ast.Or):
            result = False
            for value_node in node.values:
                result = _eval_node(value_node)
                if result:
                    return result
            return result
        raise ValueError(f"Unsupported boolean operator: {type(node.op).__name__}")

    if isinstance(node, ast.Compare):
        left = _eval_node(node.left)
        for op, comparator_node in zip(node.ops, node.comparators):
            op_fn = _CMPOP_OPS.get(type(op))
            if op_fn is None:
                raise ValueError(f"Unsupported comparison operator: {type(op).__name__}")
            right = _eval_node(comparator_node)
            if not op_fn(left, right):
                return False
            left = right
        return True

    raise ValueError(f"Disallowed AST node: {type(node).__name__}")


def _validate_ast(node: ast.AST) -> None:
    """Raise ValueError if the AST contains disallowed node types."""
    if not isinstance(node, _ALLOWED_AST_NODES):
        raise ValueError(f"Disallowed AST node: {type(node).__name__}")
    for child in ast.iter_child_nodes(node):
        _validate_ast(child)
