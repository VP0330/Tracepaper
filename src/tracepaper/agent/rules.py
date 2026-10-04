"""Safe evaluator for user-configured audit rules."""

from datetime import date
from typing import Any

SUPPORTED_OPERATORS = {"eq", "neq", "gt", "gte", "lt", "lte", "contains", "missing", "not_missing"}


def get_field(fields: dict[str, Any], field_name: str) -> Any:
    value: Any = fields
    for part in field_name.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _comparable(left: Any, right: Any) -> tuple[Any, Any]:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return float(left), float(right)
    if isinstance(left, str) and isinstance(right, str):
        try:
            return date.fromisoformat(left), date.fromisoformat(right)
        except ValueError:
            return left.casefold(), right.casefold()
    return left, right


def evaluate_rule(rule: Any, fields: dict[str, Any]) -> dict[str, Any] | None:
    """Return a review flag when the observed field violates the rule condition."""
    operator = rule.operator
    if operator not in SUPPORTED_OPERATORS:
        raise ValueError(f"Unsupported audit rule operator: {operator}")
    observed = get_field(fields, rule.field_name)
    expected = rule.expected_value
    if operator == "missing":
        condition_met = observed is None or observed == ""
    elif operator == "not_missing":
        condition_met = observed is not None and observed != ""
    elif observed is None:
        condition_met = False
    elif operator == "eq":
        condition_met = observed == expected
    elif operator == "neq":
        condition_met = observed != expected
    elif operator == "contains":
        condition_met = str(expected).casefold() in str(observed).casefold()
    else:
        left, right = _comparable(observed, expected)
        try:
            condition_met = {
                "gt": left > right,
                "gte": left >= right,
                "lt": left < right,
                "lte": left <= right,
            }[operator]
        except TypeError:
            condition_met = False
    if condition_met:
        return None
    return {
        "rule_id": rule.rule_id,
        "rule_name": rule.name,
        "field_name": rule.field_name,
        "operator": operator,
        "observed_value": observed,
        "expected_value": expected,
        "severity": rule.severity,
        "message": f"{rule.name}: {rule.field_name}={observed!r} violates {operator} {expected!r}",
    }
