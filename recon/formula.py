"""Safe derived-column formula evaluator.

Answers Cointab's "AI-generated Excel-style formula" feature honestly:
theirs uses an LLM to write a formula from a natural-language ask; this
evaluates a formula against a real row deterministically, no LLM required
(matching this project's stance that a real number should never come from
a model when it can just be computed). Only +, -, *, / over a fixed
whitelist of known transaction fields are allowed -- built on Python's
`ast` module rather than `eval()`, since evaluating arbitrary
attacker-supplied strings with eval() is a code-execution vulnerability,
not a formula evaluator.
"""
import ast
import operator

ALLOWED_FIELDS = {"amount", "ledger_amount", "settlement_amount", "fee", "tax"}

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


class FormulaError(ValueError):
    pass


def evaluate(expr, row):
    """expr is a string like "amount - fee - tax"; row is a dict whose
    numeric fields (a subset of ALLOWED_FIELDS) can be referenced by name.
    Raises FormulaError for anything outside the whitelisted grammar --
    unknown fields, function calls, attribute access, string literals,
    anything -- rather than silently coercing or guessing."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise FormulaError(f"couldn't parse '{expr}' as a formula: {e}") from e
    return _eval_node(tree.body, row, expr)


def _eval_node(node, row, expr):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in ALLOWED_FIELDS:
            raise FormulaError(
                f"'{node.id}' isn't a known field -- allowed: {', '.join(sorted(ALLOWED_FIELDS))}"
            )
        if node.id not in row:
            raise FormulaError(f"'{node.id}' isn't present on this row")
        return float(row[node.id] or 0.0)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.left, row, expr), _eval_node(node.right, row, expr))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.operand, row, expr))
    raise FormulaError(
        f"'{expr}' uses something other than +, -, *, / over known fields -- not evaluated"
    )
