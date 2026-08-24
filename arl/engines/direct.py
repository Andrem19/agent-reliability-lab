from __future__ import annotations

import asyncio
import json
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from arl.config import LabConfig
from arl.oracles.deterministic import evaluate_expected_subset
from arl.safety.redaction import SecretRedactor
from arl.storage.database import Database
from arl.storage.events import EventWriter, LabEvent
from arl.targets.contract import TargetContract
from arl.tracing.otel_model import Span, SpanKind, SpanStatus, new_trace_id


@dataclass(frozen=True)
class DirectRunResult:
    run_id: str
    cycle_id: str
    scenario_id: str
    status: str
    trace_id: str
    trace_path: Path
    observed: Any
    expected: Any
    reason: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _load_scenario(config: LabConfig, target_name: str, scenario_name: str) -> dict[str, Any]:
    path = config.paths.targets_dir / target_name / "scenarios" / f"{scenario_name}.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"scenario root must be a mapping: {path}")
    return raw


def _normalize_tool_result(result: Any) -> Any:
    if hasattr(result, "model_dump"):
        data = result.model_dump(mode="json", by_alias=True)
    elif isinstance(result, dict):
        data = result
    else:
        return result
    structured = data.get("structuredContent")
    if structured is not None:
        return structured
    for item in data.get("content", []):
        if item.get("type") == "text":
            text = item.get("text", "")
            try:
                return json.loads(text)
            except (TypeError, json.JSONDecodeError):
                return {"text": text}
    return data


def _resolve_server_command(target: TargetContract) -> tuple[list[str], Path | None]:
    server = target.topology[0].server
    if server.transport != "stdio" or server.command is None:
        raise ValueError("server is not configured for stdio")
    cwd = server.repo
    if cwd is not None and not cwd.is_absolute():
        cwd = Path.cwd() / cwd
    is_python_command = server.command.casefold() in {"python", "python.exe"}
    command = sys.executable if is_python_command else server.command
    return [command, *server.args], cwd


async def _call_configured_server(
    target: TargetContract,
    scenario: dict[str, Any],
    trace_path: Path,
    trace_id: str,
) -> Any:
    server = target.topology[0].server
    if server.transport == "http":
        if server.url is None:  # guarded by TargetContract validation
            raise ValueError("http server requires url")
        async with (
            streamable_http_client(server.url) as (read, write),
            ClientSession(read, write) as session,
        ):
            return await _initialize_and_call(session, scenario)

    server_command, cwd = _resolve_server_command(target)
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
        *server_command,
    ]
    params = StdioServerParameters(command=sys.executable, args=proxy_args, cwd=cwd)
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as session,
    ):
        return await _initialize_and_call(session, scenario)


async def _initialize_and_call(session: ClientSession, scenario: dict[str, Any]) -> Any:
    await session.initialize()
    tools = await session.list_tools()
    names = {tool.name for tool in tools.tools}
    if scenario["tool"] not in names:
        raise ValueError(f"tool not found: {scenario['tool']}")
    return await session.call_tool(scenario["tool"], scenario["arguments"])


def _persist_start(
    database: Database,
    target: TargetContract,
    scenario: dict[str, Any],
    run_id: str,
    cycle_id: str,
) -> None:
    now = _now()
    oracle = scenario["oracle"]
    with database.connect() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO targets VALUES (?, ?, ?, ?)",
            (
                target.name,
                target.access_mode,
                json.dumps(target.model_dump(mode="json"), sort_keys=True),
                now,
            ),
        )
        connection.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?)",
            (run_id, target.name, "running", now, now),
        )
        connection.execute(
            "INSERT INTO cycles VALUES (?, ?, ?, ?, ?)",
            (cycle_id, run_id, 1, "running", now),
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO scenarios
            (id, target_name, oracle_id, oracle_version, oracle_type, oracle_confidence,
             source, needs_review) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scenario["id"],
                target.name,
                oracle["id"],
                str(oracle["version"]),
                str(oracle["type"]).upper(),
                float(oracle["confidence"]),
                "curated",
                0,
            ),
        )


def _ingest_spans(database: Database, trace_path: Path, run_id: str) -> None:
    if not trace_path.exists():
        return
    with database.connect() as connection:
        for line in trace_path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record.get("record_type") != "span":
                continue
            attributes = record.get("attributes", {})
            connection.execute(
                """
                INSERT OR REPLACE INTO spans
                (span_id, trace_id, parent_span_id, run_id, name, kind, start_time,
                 end_time, status, attributes_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["span_id"],
                    record["trace_id"],
                    record.get("parent_span_id"),
                    run_id,
                    record["name"],
                    record["kind"],
                    record["start_time"],
                    record.get("end_time"),
                    record["status"],
                    json.dumps(attributes, sort_keys=True),
                ),
            )
            if attributes.get("rpc.method") == "tools/call":
                connection.execute(
                    """
                    INSERT OR REPLACE INTO tool_calls
                    (id, trace_id, span_id, run_id, tool_name, args_json, result_json,
                     duration_ms, error, retry_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        str(uuid.uuid4()),
                        record["trace_id"],
                        record["span_id"],
                        run_id,
                        attributes.get("tool.name", ""),
                        json.dumps(attributes.get("tool.arguments", {}), sort_keys=True),
                        json.dumps(attributes.get("rpc.response"), sort_keys=True),
                        None,
                        json.dumps(attributes.get("error")) if attributes.get("error") else None,
                    ),
                )


def _persist_finish(database: Database, result: DirectRunResult) -> None:
    now = _now()
    safe_result = SecretRedactor().redact(asdict(result))
    safe_result["trace_path"] = str(safe_result["trace_path"])
    with database.connect() as connection:
        connection.execute(
            "UPDATE runs SET status = ?, updated_at = ? WHERE id = ?",
            (result.status, now, result.run_id),
        )
        connection.execute(
            "UPDATE cycles SET status = ? WHERE id = ?",
            (result.status, result.cycle_id),
        )
        connection.execute(
            """
            INSERT INTO layer_results
            (id, run_id, cycle_id, scenario_id, layer, status, result_json,
             trace_path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                result.run_id,
                result.cycle_id,
                result.scenario_id,
                "L2",
                result.status,
                json.dumps(safe_result, sort_keys=True),
                str(result.trace_path),
                now,
            ),
        )


async def run_direct_scenario(
    config: LabConfig,
    target: TargetContract,
    *,
    scenario_name: str = "echo",
) -> DirectRunResult:
    database = Database(config.paths.state_dir / "arl.db")
    database.initialize()
    scenario = _load_scenario(config, target.name, scenario_name)
    run_id = str(uuid.uuid4())
    cycle_id = str(uuid.uuid4())
    trace_id = new_trace_id()
    trace_path = config.paths.state_dir / "artifacts" / run_id / "mcp-trace.jsonl"
    _persist_start(database, target, scenario, run_id, cycle_id)
    event_writer = EventWriter(database, config.paths.state_dir / "events.jsonl")
    event_writer.write(
        LabEvent("layer.started", "running", {"layer": "L2"}, run_id, cycle_id, scenario["id"])
    )

    root_span = Span(trace_id, f"scenario.{scenario['id']}", SpanKind.INTERNAL)
    try:
        async with asyncio.timeout(config.timeouts.process_seconds):
            call_result = await _call_configured_server(target, scenario, trace_path, trace_id)
        observed = _normalize_tool_result(call_result)
        oracle = evaluate_expected_subset(scenario["expected"], observed)
        status = "pass" if oracle.passed else "fail"
        root_span.end(SpanStatus.OK if oracle.passed else SpanStatus.ERROR)
        result = DirectRunResult(
            run_id,
            cycle_id,
            scenario["id"],
            status,
            trace_id,
            trace_path,
            observed,
            scenario["expected"],
            oracle.reason,
        )
    except Exception as exc:
        root_span.end(SpanStatus.ERROR, error=f"{type(exc).__name__}: {exc}")
        result = DirectRunResult(
            run_id,
            cycle_id,
            scenario["id"],
            "error",
            trace_id,
            trace_path,
            None,
            scenario["expected"],
            f"{type(exc).__name__}: {exc}",
        )

    trace_path.parent.mkdir(parents=True, exist_ok=True)
    safe_span = SecretRedactor().redact(root_span.as_record())
    with trace_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(safe_span, sort_keys=True) + "\n")
    _ingest_spans(database, trace_path, run_id)
    _persist_finish(database, result)
    event_writer.write(
        LabEvent(
            "layer.completed",
            result.status,
            {"layer": "L2", "reason": result.reason, "trace_id": trace_id},
            run_id,
            cycle_id,
            scenario["id"],
        )
    )
    return result
