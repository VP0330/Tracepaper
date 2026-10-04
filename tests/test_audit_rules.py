"""Tests for user-configured discrepancy conditions."""

from types import SimpleNamespace

import pytest

from tracepaper.agent.rules import evaluate_rule


def make_rule(operator, expected, field_name="amount"):
    return SimpleNamespace(
        rule_id="rule-1", name="Threshold", field_name=field_name,
        operator=operator, expected_value=expected, severity="high",
    )


def test_numeric_rule_returns_flag_for_failed_condition():
    flag = evaluate_rule(make_rule("lt", 10000), {"amount": 15000})
    assert flag["observed_value"] == 15000
    assert flag["expected_value"] == 10000
    assert "violates lt" in flag["message"]
    assert evaluate_rule(make_rule("lt", 10000), {"amount": 9000}) is None


def test_missing_and_contains_rules():
    assert evaluate_rule(make_rule("not_missing", None, "approver"), {"approver": None})
    assert evaluate_rule(make_rule("contains", "approved", "approval_status"), {"approval_status": "PENDING"})
    assert evaluate_rule(make_rule("contains", "approved", "approval_status"), {"approval_status": "APPROVED"}) is None


def test_nested_fields_and_invalid_operator():
    assert evaluate_rule(make_rule("eq", "USD", "invoice.currency"), {"invoice": {"currency": "CAD"}})
    with pytest.raises(ValueError, match="Unsupported audit rule operator"):
        evaluate_rule(make_rule("exec", "bad"), {"amount": 1})
