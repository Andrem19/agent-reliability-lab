from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from arl.engines.fuzz import FuzzCase, FuzzOutcome
from arl.safety.risk_class import HIGH_RISK, classify_tool
from arl.targets.contract import TargetContract
from arl.tracing.otel_model import new_trace_id

SAFE_FUZZ_TOOLS = ("get_status", "list_stored_jobs", "get_job", "check_applied")


@dataclass(frozen=True)
class LiveFuzzObservation:
    tool_name: str
    case_name: str
    expected_valid: bool
    outcome: FuzzOutcome
    passed: bool
    detail: str


@dataclass(frozen=True)
class LiveFuzzRunResult:
    passed: bool
    trace_id: str
    trace_path: Path
    observations: tuple[LiveFuzzObservation, ...]
    reason: str

    @property
    def total(self) -> int:
        return len(self.observations)

    @property
    def successes(self) -> int:
        return sum(item.passed for item in self.observations)


def _json_types(schema: dict[str, Any]) -> set[str]:
    types: set[str] = set()
    kind = schema.get("type")
    if isinstance(kind, str):
        types.add(kind)
    elif isinstance(kind, list):
        types.update(item for item in kind if isinstance(item, str))
    for option in schema.get("anyOf", []):
        if isinstance(option, dict):
            types.update(_json_types(option))
    return types


def _sample_value(schema: dict[str, Any]) -> Any:
    if schema.get("enum"):
        return schema["enum"][0]
    for option in schema.get("anyOf", []):
        if isinstance(option, dict) and option.get("type") != "null":
            return _sample_value(option)
    kind = schema.get("type")
    if kind == "string":
        return "arl-fuzz"
    if kind == "integer":
        return max(int(schema.get("minimum", 1)), 1)
    if kind == "number":
        return float(schema.get("minimum", 1.0))
    if kind == "boolean":
        return False
    if kind == "array":
        return []
    if kind == "object":
        return {}
    return None


def _invalid_value(schema: dict[str, Any]) -> Any:
    if schema.get("enum"):
        candidate = "__arl_invalid_enum__"
        if candidate not in schema["enum"]:
            return candidate
    accepted = _json_types(schema)
    candidates = (
        ("object", {}),
        ("array", []),
        ("string", "arl-invalid"),
        ("integer", 42),
        ("boolean", False),
        ("null", None),
    )
    for kind, value in candidates:
        if kind not in accepted:
            return value
    raise ValueError("schema accepts every supported JSON type")


def schema_fuzz_cases(schema: dict[str, Any]) -> tuple[FuzzCase, ...]:
    properties = schema.get("properties", {})
    required = tuple(schema.get("required", ()))
    baseline = {
        name: _sample_value(properties[name])
        for name in required
        if name in properties
    }
    cases = [FuzzCase("valid_baseline", baseline, True)]
    for name, definition in properties.items():
        try:
            invalid = _invalid_value(definition)
        except ValueError:
            continue
        cases.append(FuzzCase(f"{name}:wrong_type_or_enum", {**baseline, name: invalid}, False))
    for name in required:
        cases.append(
            FuzzCase(
                f"{name}:missing",
                {key: value for key, value in baseline.items() if key != name},
                False,
            )
        )
    return tuple(cases)


async def run_live_schema_fuzz(
    target: TargetContract,
    trace_path: Path,
    *,
    timeout_seconds: float = 60,
) -> LiveFuzzRunResult:
    server = target.topology[0].server
    if server.transport != "stdio" or server.command is None:
        raise ValueError("live schema fuzz requires a stdio target")
    for tool_name in SAFE_FUZZ_TOOLS:
        risks = classify_tool(tool_name)
        if risks & HIGH_RISK:
            raise PermissionError(f"unsafe live fuzz target: {tool_name}")

    trace_id = new_trace_id()
    proxy_args = [
        "-m",
        "arl.tracing.stdio_proxy",
        "--trace-file",
        str(trace_path),
        "--trace-id",
        trace_id,
        "--safety-mode",
        target.environment.default_mode.value,
        *[
            value
            for tool in target.safety.irreversible_tools
            for value in ("--irreversible-tool", tool)
        ],
        "--",
        server.command,
        *server.args,
    ]
    cwd = server.repo.resolve() if server.repo else None
    params = StdioServerParameters(command=sys.executable, args=proxy_args, cwd=cwd)
    observations: list[LiveFuzzObservation] = []
    async with asyncio.timeout(timeout_seconds):
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            catalog = {
                tool.name: tool.model_dump(mode="json", by_alias=True).get("inputSchema", {})
                for tool in tools.tools
            }
            missing = set(SAFE_FUZZ_TOOLS) - set(catalog)
            if missing:
                raise ValueError(f"safe fuzz tools missing: {sorted(missing)}")
            for tool_name in SAFE_FUZZ_TOOLS:
                for case in schema_fuzz_cases(catalog[tool_name]):
                    try:
                        result = await session.call_tool(tool_name, case.arguments)
                        rejected = result.is_error is True
                        outcome = (
                            FuzzOutcome.INVALID_REJECT
                            if rejected and not case.valid
                            else FuzzOutcome.VALID_REJECT
                            if rejected
                            else FuzzOutcome.ACCEPTED_VALID
                            if case.valid
                            else FuzzOutcome.SILENT_SUCCESS
                        )
                        detail = "MCP isError=true" if rejected else "MCP isError=false"
                    except Exception as exc:
                        rejected = True
                        outcome = (
                            FuzzOutcome.INVALID_REJECT if not case.valid else FuzzOutcome.CRASH
                        )
                        detail = f"{type(exc).__name__}: {exc}"
                    passed = (case.valid and not rejected) or (not case.valid and rejected)
                    observations.append(
                        LiveFuzzObservation(
                            tool_name, case.name, case.valid, outcome, passed, detail
                        )
                    )
    successes = sum(item.passed for item in observations)
    passed = successes == len(observations) and bool(observations)
    reason = f"schema fuzz assertions {successes}/{len(observations)} passed"
    return LiveFuzzRunResult(passed, trace_id, trace_path, tuple(observations), reason)
