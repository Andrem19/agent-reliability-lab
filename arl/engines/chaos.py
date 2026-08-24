from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from arl.config import LabConfig
from arl.isolation.hypotheses import Hypothesis
from arl.targets.contract import TargetContract
from arl.tracing.otel_model import new_trace_id


class ChaosKind(StrEnum):
    LATENCY = "latency"
    CONNECTION_DROP = "connection_drop"
    MALFORMED_JSON_RPC = "malformed_json_rpc"
    ERROR_CODE = "error_code"
    KILL_SERVER = "kill_server"
    PARTIAL_RESULT = "partial_result"
    HUGE_RESULT = "huge_result"


@dataclass(frozen=True)
class ChaosEvidence:
    kind: ChaosKind
    injection_id: str
    observed_error: str
    proxy_confirmed: bool = True


@dataclass(frozen=True)
class LiveChaosResult:
    kind: ChaosKind
    injection_id: str
    passed: bool
    fault_observed: str
    recovery_passed: bool
    fault_trace: Path
    recovery_trace: Path
    attribution: Hypothesis


def inject_message(kind: ChaosKind, message: dict[str, Any]) -> str | None:
    if kind is ChaosKind.CONNECTION_DROP or kind is ChaosKind.KILL_SERVER:
        return None
    if kind is ChaosKind.MALFORMED_JSON_RPC:
        return "{malformed"
    if kind is ChaosKind.ERROR_CODE:
        return json.dumps({"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": -32000}})
    if kind is ChaosKind.PARTIAL_RESULT:
        return json.dumps({"jsonrpc": "2.0", "id": message.get("id"), "result": {}})
    if kind is ChaosKind.HUGE_RESULT:
        return json.dumps({"jsonrpc": "2.0", "id": message.get("id"), "result": "x" * 1_000_000})
    return json.dumps(message)


def attribute_chaos(evidence: ChaosEvidence) -> Hypothesis:
    """A proxy-confirmed injected fault is laboratory infrastructure, not an MCP bug."""
    if evidence.proxy_confirmed:
        return Hypothesis.INFRA
    return Hypothesis.UNKNOWN


def _server_command(target: TargetContract) -> tuple[list[str], Path | None]:
    server = target.topology[0].server
    if server.transport != "stdio" or server.command is None:
        raise ValueError("L6 live chaos requires a stdio MCP server")
    cwd = server.repo
    if cwd is not None and not cwd.is_absolute():
        cwd = Path.cwd() / cwd
    command = (
        sys.executable
        if server.command.casefold() in {"python", "python.exe"}
        else server.command
    )
    return [command, *server.args], cwd


def _proxy_parameters(
    target: TargetContract,
    trace_path: Path,
    trace_id: str,
    *,
    kind: ChaosKind | None = None,
    injection_id: str = "",
) -> StdioServerParameters:
    command, cwd = _server_command(target)
    args = [
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
    ]
    if kind is not None:
        args.extend(
            [
                "--chaos-kind",
                kind.value,
                "--chaos-id",
                injection_id,
                "--chaos-tool",
                "get_status",
            ]
        )
    args.extend(["--", *command])
    return StdioServerParameters(command=sys.executable, args=args, cwd=cwd)


async def _get_status(
    target: TargetContract,
    trace_path: Path,
    *,
    kind: ChaosKind | None = None,
    injection_id: str = "",
    timeout_seconds: float = 3.0,
) -> Any:
    parameters = _proxy_parameters(
        target,
        trace_path,
        new_trace_id(),
        kind=kind,
        injection_id=injection_id,
    )
    async with (
        stdio_client(parameters) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        async with asyncio.timeout(timeout_seconds):
            return await session.call_tool("get_status", {})


def _trace_has_injection(trace_path: Path, injection_id: str, kind: ChaosKind) -> bool:
    if not trace_path.exists():
        return False
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if (
            record.get("record_type") == "chaos_injection"
            and record.get("injection_id") == injection_id
            and record.get("chaos_kind") == kind.value
            and record.get("phase") == "injected"
        ):
            return True
    return False


def _result_text(result: Any) -> str:
    if hasattr(result, "model_dump_json"):
        return result.model_dump_json()
    return json.dumps(result, default=str)


async def run_live_chaos_control(
    config: LabConfig,
    target: TargetContract,
    kind: ChaosKind,
) -> LiveChaosResult:
    injection_id = f"l6-{kind.value}-{uuid.uuid4()}"
    root = config.paths.state_dir / "artifacts" / injection_id
    fault_trace = root / "fault-trace.jsonl"
    recovery_trace = root / "recovery-trace.jsonl"
    timeout = 0.05 if kind is ChaosKind.LATENCY else 3.0
    started = time.monotonic()
    fault_result: Any = None
    fault_error = ""
    try:
        fault_result = await _get_status(
            target,
            fault_trace,
            kind=kind,
            injection_id=injection_id,
            timeout_seconds=timeout,
        )
        fault_observed = "response"
    except Exception as exc:
        fault_error = f"{type(exc).__name__}: {exc}"
        fault_observed = fault_error
    elapsed = time.monotonic() - started

    text = _result_text(fault_result) if fault_result is not None else ""
    semantic_match = {
        ChaosKind.LATENCY: bool(fault_error) and elapsed >= timeout,
        ChaosKind.CONNECTION_DROP: bool(fault_error),
        ChaosKind.MALFORMED_JSON_RPC: bool(fault_error),
        ChaosKind.ERROR_CODE: bool(fault_error),
        ChaosKind.KILL_SERVER: bool(fault_error),
        ChaosKind.PARTIAL_RESULT: bool(fault_error)
        or (fault_result is not None and '"content":[]' in text),
        ChaosKind.HUGE_RESULT: len(text) >= 262_144,
    }[kind]
    injected = _trace_has_injection(fault_trace, injection_id, kind)

    recovery_passed = False
    try:
        recovery = await _get_status(target, recovery_trace)
        recovery_text = _result_text(recovery)
        recovery_passed = bool(recovery_text) and not bool(getattr(recovery, "isError", False))
    except Exception:
        recovery_passed = False

    evidence = ChaosEvidence(kind, injection_id, fault_observed, injected)
    attribution = attribute_chaos(evidence)
    passed = semantic_match and injected and recovery_passed and attribution is Hypothesis.INFRA
    return LiveChaosResult(
        kind,
        injection_id,
        passed,
        fault_observed,
        recovery_passed,
        fault_trace,
        recovery_trace,
        attribution,
    )


async def run_live_chaos_suite(
    config: LabConfig,
    target: TargetContract,
) -> list[LiveChaosResult]:
    return [
        await run_live_chaos_control(config, target, kind)
        for kind in ChaosKind
    ]
