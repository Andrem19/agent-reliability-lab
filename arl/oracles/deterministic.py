from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OracleResult:
    passed: bool
    expected: Any
    observed: Any
    reason: str


def _is_subset(expected: Any, observed: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(observed, dict) and all(
            key in observed and _is_subset(value, observed[key]) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(observed, list)
            and len(expected) == len(observed)
            and all(_is_subset(left, right) for left, right in zip(expected, observed, strict=True))
        )
    return expected == observed


def evaluate_expected_subset(expected: Any, observed: Any) -> OracleResult:
    passed = _is_subset(expected, observed)
    return OracleResult(
        passed=passed,
        expected=expected,
        observed=observed,
        reason="expected subset matched" if passed else "expected subset did not match",
    )
