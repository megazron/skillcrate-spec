"""A tiny SAFE expression evaluator for skill pre/postconditions.

Conditions are written as ordinary boolean expressions over named world
facts, e.g.::

    gripper_open and object_visible and table_clearance_m > 0.12

They are parsed with ``ast`` and evaluated against a plain ``dict`` of facts.
Only a whitelisted set of node types is allowed: comparisons, boolean and/or/
not, arithmetic, numeric and string and bool literals, and names that resolve
to facts. There is no attribute access, no call, no subscript, no
comprehension, no ``__import__`` -- anything outside the whitelist raises
``UnsafeExpression`` at PARSE time, before a single fact is read.

This is deliberately the same shape a robot-safety gate wants: a declared,
auditable predicate that cannot execute arbitrary code and fails closed.
"""
from __future__ import annotations

import ast
import operator

__all__ = ["UnsafeExpression", "ConditionError", "evaluate",
           "check_parses", "names_used"]


class UnsafeExpression(ValueError):
    """The expression used syntax that is not on the safe whitelist."""


class ConditionError(ValueError):
    """The expression is safe but could not be evaluated (e.g. missing fact)."""


_BIN = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
}
_CMP = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
    ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
}
_UNARY = {ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Not: operator.not_}

# The only node types allowed anywhere in the tree.
_ALLOWED = (
    ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not,
    ast.USub, ast.UAdd, ast.BinOp, ast.Compare, ast.Name, ast.Load,
    ast.Constant,
) + tuple(_BIN) + tuple(_CMP)


def _check_safe(tree: ast.AST, src: str) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise UnsafeExpression(
                "%r is not allowed in a condition (found %s). Conditions may "
                "use names, numbers, strings, comparisons and and/or/not only."
                % (src, type(node).__name__))
        if isinstance(node, ast.Constant) and not isinstance(
                node.value, (int, float, bool, str)):
            raise UnsafeExpression(
                "constant %r of type %s is not allowed in %r"
                % (node.value, type(node.value).__name__, src))


def _parse(src: str) -> ast.Expression:
    if not isinstance(src, str) or not src.strip():
        raise UnsafeExpression("a condition must be a non-empty string")
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError as e:
        raise UnsafeExpression("condition %r does not parse: %s" % (src, e))
    _check_safe(tree, src)
    return tree


def check_parses(src: str) -> bool:
    """True if `src` is a safe, parseable condition; raises otherwise."""
    _parse(src)
    return True


def names_used(src: str) -> set:
    """Every world-fact name the condition references."""
    tree = _parse(src)
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}


def _eval(node: ast.AST, facts: dict, src: str):
    if isinstance(node, ast.Expression):
        return _eval(node.body, facts, src)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in facts:
            raise ConditionError(
                "condition %r needs the fact %r, which is not in the world "
                "state" % (src, node.id))
        return facts[node.id]
    if isinstance(node, ast.BoolOp):
        vals = [_eval(v, facts, src) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(vals)
        return any(vals)
    if isinstance(node, ast.UnaryOp):
        return _UNARY[type(node.op)](_eval(node.operand, facts, src))
    if isinstance(node, ast.BinOp):
        return _BIN[type(node.op)](
            _eval(node.left, facts, src), _eval(node.right, facts, src))
    if isinstance(node, ast.Compare):
        left = _eval(node.left, facts, src)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval(comp, facts, src)
            if not _CMP[type(op)](left, right):
                return False
            left = right
        return True
    raise UnsafeExpression("unexpected node %s in %r"
                           % (type(node).__name__, src))


def evaluate(src: str, facts: dict) -> bool:
    """Evaluate a safe condition against `facts`, returning a bool.

    Raises `UnsafeExpression` for disallowed syntax and `ConditionError`
    for a missing fact. The result is coerced to bool.
    """
    return bool(_eval(_parse(src), facts, src))
