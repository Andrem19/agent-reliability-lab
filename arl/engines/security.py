from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from arl.harnesses.zcode import _trace_tool_calls
from arl.targets.contract import TargetContract
from arl.tracing.otel_model import new_trace_id


@dataclass(frozen=True)
class FirewallProbeResult:
    passed: bool
    tool_name: str
    trace_id: str
    trace_path: Path
    reason: str


async def run_live_firewall_probe(
    target: TargetContract,
    trace_path: Path,
    *,
    timeout_seconds: float = 60,
) -> FirewallProbeResult:
    server = target.topology[0].server
    if server.transport != "stdio" or server.command is None:
        raise ValueError("firewall probe requires a stdio target")
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
    async with asyncio.timeout(timeout_seconds):
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            result = await session.call_tool(
                "record_application",
                {"application_id": "arl-firewall-canary", "status": "submitted"},
            )
    calls, blocked = _trace_tool_calls(trace_path)
    is_error = result.is_error is True
    passed = is_error and "record_application" in blocked
    reason = (
        "record_application blocked before MCP server"
        if passed
        else (f"unexpected result: calls={calls}, blocked={sorted(blocked)}, isError={is_error}")
    )
    return FirewallProbeResult(passed, "record_application", trace_id, trace_path, reason)
