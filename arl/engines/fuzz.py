from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from arl.safety.risk_class import HIGH_RISK, RiskClass


class FuzzOutcome(StrEnum):
    ACCEPTED_VALID = "accepted_valid"
    VALID_REJECT = "valid_reject"
    INVALID_REJECT = "invalid_reject"
    SILENT_SUCCESS = "silent_success_on_garbage"
    CRASH = "crash"
    UNINFORMATIVE_ERROR = "uninformative_error"


@dataclass(frozen=True)
class FuzzCase:
    name: str
    arguments: dict[str, Any]
    valid: bool


@dataclass(frozen=True)
class FuzzResult:
    case: FuzzCase
    outcome: FuzzOutcome
    detail: str = ""


def schema_cases(schema: dict[str, Any]) -> tuple[FuzzCase, ...]:
    """Create deterministic boundary cases from the MCP tool input schema."""
    properties = schema.get("properties", {})
    required = list(schema.get("required", []))
    valid: dict[str, Any] = {}
    cases: list[FuzzCase] = []
    for name, definition in properties.items():
        kind = definition.get("type")
        if kind == "integer":
            valid[name] = definition.get("minimum", 0)
            if "maximum" in definition:
                cases.append(
                    FuzzCase(
                        f"{name}:above_maximum",
                        {**valid, name: definition["maximum"] + 1},
                        False,
                    )
                )
            cases.append(FuzzCase(f"{name}:huge_integer", {**valid, name: 2**63}, False))
        elif kind == "string":
            valid[name] = "x"
            cases.extend(
                (
                    FuzzCase(f"{name}:empty", {**valid, name: ""}, True),
                    FuzzCase(f"{name}:unicode", {**valid, name: "λ🙂"}, True),
                    FuzzCase(f"{name}:long", {**valid, name: "x" * 10_000}, False),
                )
            )
        elif kind == "boolean":
            valid[name] = False
        else:
            valid[name] = None
        cases.append(FuzzCase(f"{name}:wrong_type", {**valid, name: []}, False))
    for name in required:
        cases.append(
            FuzzCase(f"{name}:missing", {k: v for k, v in valid.items() if k != name}, False)
        )
    cases.extend(
        (
            FuzzCase("valid", valid, True),
            FuzzCase("unexpected_field", {**valid, "__unexpected__": True}, False),
            FuzzCase("null_payload", {name: None for name in properties}, False),
        )
    )
    return tuple(cases)


def assert_safe_fuzz_target(risks: set[RiskClass], environment: str) -> None:
    if risks & HIGH_RISK and environment not in {"mock", "sandbox", "sandbox_fs"}:
        raise PermissionError("high-risk tools may only be fuzzed against mock/sandbox")


def run_fuzz(
    handler: Callable[[dict[str, Any]], Any], cases: tuple[FuzzCase, ...]
) -> tuple[FuzzResult, ...]:
    results: list[FuzzResult] = []
    for case in cases:
        try:
            handler(case.arguments)
            outcome = FuzzOutcome.ACCEPTED_VALID if case.valid else FuzzOutcome.SILENT_SUCCESS
            results.append(FuzzResult(case, outcome))
        except (TypeError, ValueError) as exc:
            message = str(exc)
            if not message.strip():
                outcome = FuzzOutcome.UNINFORMATIVE_ERROR
            else:
                outcome = FuzzOutcome.VALID_REJECT if case.valid else FuzzOutcome.INVALID_REJECT
            results.append(FuzzResult(case, outcome, message))
        except Exception as exc:
            results.append(FuzzResult(case, FuzzOutcome.CRASH, f"{type(exc).__name__}: {exc}"))
    return tuple(results)
