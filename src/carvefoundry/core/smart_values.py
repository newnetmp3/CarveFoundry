from __future__ import annotations

import ast
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CONSTANTS = {"pi": math.pi, "e": math.e}
_FUNCTIONS = {
    "abs": abs,
    "ceil": math.ceil,
    "floor": math.floor,
    "max": max,
    "min": min,
    "round": round,
    "sqrt": math.sqrt,
}


class SmartValueError(ValueError):
    """Raised when a named project value or expression is invalid."""


@dataclass(slots=True)
class SmartValues:
    """Safe named arithmetic expressions shared across one project.

    This evaluator deliberately supports only numeric arithmetic. It cannot
    access Python attributes, imports, files, or arbitrary callables.
    """

    expressions: dict[str, str] = field(default_factory=dict)

    def set(self, name: str, expression: str | float | int) -> None:
        key = str(name).strip()
        if not _NAME_RE.fullmatch(key):
            raise SmartValueError(
                "Names must start with a letter or underscore and contain only "
                "letters, numbers, and underscores."
            )
        text = str(expression).strip()
        if not text:
            raise SmartValueError("Smart Value expression cannot be empty.")
        previous = self.expressions.get(key)
        self.expressions[key] = text
        try:
            self.resolve(key)
        except Exception:
            if previous is None:
                self.expressions.pop(key, None)
            else:
                self.expressions[key] = previous
            raise

    def remove(self, name: str) -> None:
        self.expressions.pop(str(name).strip(), None)

    def resolve(self, name: str) -> float:
        key = str(name).strip()
        if key not in self.expressions:
            raise SmartValueError(f"Unknown Smart Value: {key}")
        return self._resolve_name(key, stack=[])

    def resolve_all(self) -> dict[str, float]:
        return {name: self.resolve(name) for name in self.expressions}

    def evaluate(
        self,
        expression: str | float | int,
        *,
        extra_values: Mapping[str, float] | None = None,
    ) -> float:
        if isinstance(expression, (int, float)):
            result = float(expression)
            if not math.isfinite(result):
                raise SmartValueError("Expression result must be finite.")
            return result
        try:
            tree = ast.parse(str(expression), mode="eval")
        except SyntaxError as exc:
            raise SmartValueError(f"Invalid expression: {expression!r}") from exc
        return self._evaluate_node(
            tree.body,
            stack=[],
            extra_values=dict(extra_values or {}),
        )

    def _resolve_name(self, name: str, *, stack: list[str]) -> float:
        if name in stack:
            chain = " -> ".join((*stack, name))
            raise SmartValueError(f"Smart Value cycle detected: {chain}")
        try:
            tree = ast.parse(self.expressions[name], mode="eval")
        except SyntaxError as exc:
            raise SmartValueError(
                f"Invalid expression for Smart Value {name!r}."
            ) from exc
        return self._evaluate_node(
            tree.body,
            stack=[*stack, name],
            extra_values={},
        )

    def _evaluate_node(
        self,
        node: ast.AST,
        *,
        stack: list[str],
        extra_values: Mapping[str, float],
    ) -> float:
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)):
                raise SmartValueError("Only numeric constants are allowed.")
            result = float(node.value)
        elif isinstance(node, ast.Name):
            if node.id in extra_values:
                result = float(extra_values[node.id])
            elif node.id in _CONSTANTS:
                result = float(_CONSTANTS[node.id])
            elif node.id in self.expressions:
                result = self._resolve_name(node.id, stack=stack)
            else:
                raise SmartValueError(f"Unknown value in expression: {node.id}")
        elif isinstance(node, ast.UnaryOp) and isinstance(
            node.op, (ast.UAdd, ast.USub)
        ):
            value = self._evaluate_node(
                node.operand,
                stack=stack,
                extra_values=extra_values,
            )
            result = value if isinstance(node.op, ast.UAdd) else -value
        elif isinstance(node, ast.BinOp) and isinstance(
            node.op,
            (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow),
        ):
            left = self._evaluate_node(
                node.left,
                stack=stack,
                extra_values=extra_values,
            )
            right = self._evaluate_node(
                node.right,
                stack=stack,
                extra_values=extra_values,
            )
            if isinstance(node.op, ast.Add):
                result = left + right
            elif isinstance(node.op, ast.Sub):
                result = left - right
            elif isinstance(node.op, ast.Mult):
                result = left * right
            elif isinstance(node.op, ast.Div):
                result = left / right
            elif isinstance(node.op, ast.FloorDiv):
                result = left // right
            elif isinstance(node.op, ast.Mod):
                result = left % right
            else:
                result = left**right
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _FUNCTIONS
            and not node.keywords
        ):
            arguments = [
                self._evaluate_node(
                    argument,
                    stack=stack,
                    extra_values=extra_values,
                )
                for argument in node.args
            ]
            try:
                result = float(_FUNCTIONS[node.func.id](*arguments))
            except (TypeError, ValueError, ZeroDivisionError) as exc:
                raise SmartValueError(
                    f"Could not evaluate {node.func.id}()."
                ) from exc
        else:
            raise SmartValueError(
                "Expressions may contain only numbers, named values, arithmetic, "
                "and abs, ceil, floor, min, max, round, or sqrt."
            )

        result = float(result)
        if not math.isfinite(result):
            raise SmartValueError("Expression result must be finite.")
        return result

    @classmethod
    def from_lines(cls, text: str) -> SmartValues:
        table = cls()
        pending: list[tuple[int, str, str]] = []
        for line_number, raw_line in enumerate(str(text).splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise SmartValueError(
                    f"Line {line_number} must use name = expression."
                )
            name, expression = line.split("=", 1)
            key = name.strip()
            if not _NAME_RE.fullmatch(key):
                raise SmartValueError(f"Invalid Smart Value name on line {line_number}.")
            pending.append((line_number, key, expression.strip()))
            table.expressions[key] = expression.strip()

        for line_number, name, expression in pending:
            if not expression:
                raise SmartValueError(
                    f"Smart Value {name!r} on line {line_number} is empty."
                )
        table.resolve_all()
        return table

    def to_lines(self) -> str:
        return "\n".join(
            f"{name} = {expression}"
            for name, expression in self.expressions.items()
        )
