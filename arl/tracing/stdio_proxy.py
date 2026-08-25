from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import urlsplit

from arl.engines.chaos import ChaosKind
from arl.safety.firewall import SideEffectFirewall
from arl.safety.redaction import SecretRedactor
from arl.safety.risk_class import classify_tool
from arl.targets.contract import SafetyMode
from arl.tracing.otel_model import Span, SpanKind, SpanStatus, utc_now


class TraceSink:
    def __init__(self, path: Path, trace_id: str) -> None:
        self.path = path
        self.trace_id = trace_id
        self.lock = threading.Lock()
        self.pending: dict[str, Span] = {}
        self.redactor = SecretRedactor()
        path.parent.mkdir(parents=True, exist_ok=True)

    def _append(self, record: dict[str, Any]) -> None:
        safe = self.redactor.redact(record)
        with self.lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(safe, sort_keys=True, ensure_ascii=False) + "\n")

    def message(self, direction: str, raw: bytes) -> None:
        text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            self._append(
                {
                    "record_type": "mcp_message",
                    "trace_id": self.trace_id,
                    "timestamp": utc_now(),
                    "direction": direction,
                    "malformed": True,
                    "message": text,
                }
            )
            return

        method = message.get("method") if isinstance(message, dict) else None
        message_id = message.get("id") if isinstance(message, dict) else None
        self._append(
            {
                "record_type": "mcp_message",
                "trace_id": self.trace_id,
                "timestamp": utc_now(),
                "direction": direction,
                "method": method,
                "message": message,
            }
        )
        if direction == "client_to_server" and method and message_id is not None:
            attributes: dict[str, Any] = {"rpc.system": "jsonrpc", "rpc.method": method}
            params = message.get("params", {}) if isinstance(message, dict) else {}
            if method == "tools/call" and isinstance(params, dict):
                attributes["tool.name"] = params.get("name")
                attributes["tool.arguments"] = params.get("arguments", {})
            span = Span(
                trace_id=self.trace_id,
                name=f"mcp.{method}",
                kind=SpanKind.CLIENT,
                attributes=attributes,
            )
            with self.lock:
                self.pending[str(message_id)] = span
        elif direction == "server_to_client" and message_id is not None:
            with self.lock:
                span = self.pending.pop(str(message_id), None)
            if span is not None:
                error = message.get("error") if isinstance(message, dict) else None
                span.end(
                    SpanStatus.ERROR if error else SpanStatus.OK,
                    **({"error": error} if error else {"rpc.response": message.get("result")}),
                )
                self._append(span.as_record())

    def close_pending(self, reason: str) -> None:
        with self.lock:
            pending = list(self.pending.values())
            self.pending.clear()
        for span in pending:
            span.end(SpanStatus.ERROR, error=reason)
            self._append(span.as_record())

    def stderr(self, raw: bytes) -> None:
        self._append(
            {
                "record_type": "server_stderr",
                "trace_id": self.trace_id,
                "timestamp": utc_now(),
                "message": raw.decode("utf-8", errors="replace").rstrip("\r\n"),
            }
        )

    def chaos(self, injection_id: str, kind: ChaosKind, phase: str, **extra: Any) -> None:
        self._append(
            {
                "record_type": "chaos_injection",
                "trace_id": self.trace_id,
                "timestamp": utc_now(),
                "injection_id": injection_id,
                "chaos_kind": kind.value,
                "phase": phase,
                **extra,
            }
        )


class ChaosInjector:
    def __init__(
        self,
        kind: ChaosKind,
        injection_id: str,
        tool_name: str,
        delay_seconds: float,
        huge_bytes: int,
        sink: TraceSink,
    ) -> None:
        self.kind = kind
        self.injection_id = injection_id
        self.tool_name = tool_name
        self.delay_seconds = delay_seconds
        self.huge_bytes = huge_bytes
        self.sink = sink
        self._target_ids: set[str] = set()
        self._lock = threading.Lock()
        self.process: subprocess.Popen[bytes] | None = None

    def observe_request(self, message: Any) -> None:
        if not isinstance(message, dict) or message.get("method") != "tools/call":
            return
        params = message.get("params", {})
        if not isinstance(params, dict) or params.get("name") != self.tool_name:
            return
        message_id = str(message.get("id"))
        self.sink.chaos(
            self.injection_id,
            self.kind,
            "armed",
            message_id=message_id,
            tool_name=self.tool_name,
        )
        if self.kind in {ChaosKind.CONNECTION_DROP, ChaosKind.KILL_SERVER}:
            with self._lock:
                self._target_ids.add(message_id)
            self.sink.chaos(self.injection_id, self.kind, "injected", message_id=message_id)
            if self.process is not None:
                self.process.terminate()
            return
        with self._lock:
            self._target_ids.add(message_id)

    def transform_response(self, raw: bytes) -> bytes | None:
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        if not isinstance(message, dict):
            return raw
        message_id = str(message.get("id"))
        with self._lock:
            if message_id not in self._target_ids:
                return raw
            self._target_ids.remove(message_id)
        if self.kind in {ChaosKind.CONNECTION_DROP, ChaosKind.KILL_SERVER}:
            return None
        self.sink.chaos(self.injection_id, self.kind, "injected", message_id=message_id)
        if self.kind is ChaosKind.LATENCY:
            time.sleep(self.delay_seconds)
            return raw
        if self.kind is ChaosKind.MALFORMED_JSON_RPC:
            return b"{malformed\n"
        if self.kind is ChaosKind.ERROR_CODE:
            replacement = {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {"code": -32000, "message": "ARL injected MCP error"},
            }
        elif self.kind is ChaosKind.PARTIAL_RESULT:
            replacement = {"jsonrpc": "2.0", "id": message.get("id"), "result": {}}
        elif self.kind is ChaosKind.HUGE_RESULT:
            replacement = {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "result": {
                    "content": [{"type": "text", "text": "x" * self.huge_bytes}],
                    "isError": False,
                },
            }
        else:
            return None
        return (json.dumps(replacement, separators=(",", ":")) + "\n").encode()


def browser_url_allowed(url: str, allowed_origins: set[str]) -> bool:
    """Require an exact HTTP(S) origin match for browser navigation tools."""
    if not allowed_origins:
        return True
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    default_port = 443 if parsed.scheme == "https" else 80
    origin = f"{parsed.scheme}://{parsed.hostname.casefold()}:{parsed.port or default_port}"
    return origin in allowed_origins


def _relay(
    source: BinaryIO,
    destination: BinaryIO,
    sink: TraceSink | None,
    direction: str,
    chaos: ChaosInjector | None = None,
) -> None:
    try:
        while line := source.readline():
            if chaos is not None and direction == "server_to_client":
                line = chaos.transform_response(line)
                if line is None:
                    continue
            if sink is not None:
                sink.message(direction, line)
            destination.write(line)
            destination.flush()
    except (BrokenPipeError, OSError):
        return


def _relay_stderr(source: BinaryIO, destination: BinaryIO, sink: TraceSink) -> None:
    try:
        while line := source.readline():
            sink.stderr(line)
            destination.write(line)
            destination.flush()
    except (BrokenPipeError, OSError):
        return


def _relay_stdin(
    source: BinaryIO,
    destination: BinaryIO,
    client_output: BinaryIO,
    sink: TraceSink,
    firewall: SideEffectFirewall,
    chaos: ChaosInjector | None = None,
    browser_allowed_origins: set[str] | None = None,
) -> None:
    try:
        while line := source.readline():
            sink.message("client_to_server", line)
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                message = None
            if chaos is not None:
                chaos.observe_request(message)
            params = message.get("params", {}) if isinstance(message, dict) else {}
            is_tool_call = isinstance(message, dict) and message.get("method") == "tools/call"
            tool_name = params.get("name", "") if isinstance(params, dict) else ""
            decision = (
                firewall.decide(tool_name, classify_tool(tool_name)) if is_tool_call else None
            )
            arguments = params.get("arguments", {}) if isinstance(params, dict) else {}
            url = arguments.get("url", "") if isinstance(arguments, dict) else ""
            browser_block_reason = None
            if (
                is_tool_call
                and tool_name in {"browser_open", "browser_login"}
                and not browser_url_allowed(str(url), browser_allowed_origins or set())
            ):
                browser_block_reason = "ARL browser origin firewall blocked navigation"
            if decision is not None and not decision.allowed:
                browser_block_reason = decision.reason
            if browser_block_reason is not None:
                response = {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "result": {
                        "content": [{"type": "text", "text": browser_block_reason}],
                        "isError": True,
                    },
                }
                encoded = (json.dumps(response, separators=(",", ":")) + "\n").encode()
                sink.message("server_to_client", encoded)
                client_output.write(encoded)
                client_output.flush()
                continue
            destination.write(line)
            destination.flush()
    finally:
        with contextlib.suppress(OSError):
            destination.close()


def proxy(
    command: list[str],
    trace_file: Path,
    trace_id: str,
    safety_mode: SafetyMode,
    irreversible_tools: set[str],
    chaos_kind: ChaosKind | None = None,
    chaos_id: str = "",
    chaos_tool: str = "get_status",
    chaos_delay_seconds: float = 1.0,
    chaos_huge_bytes: int = 262_144,
    browser_allowed_origins: set[str] | None = None,
) -> int:
    if not command:
        raise ValueError("server command is required after --")
    sink = TraceSink(trace_file, trace_id)
    firewall = SideEffectFirewall(safety_mode, irreversible_tools=irreversible_tools)
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    chaos = (
        ChaosInjector(
            chaos_kind,
            chaos_id,
            chaos_tool,
            chaos_delay_seconds,
            chaos_huge_bytes,
            sink,
        )
        if chaos_kind is not None
        else None
    )
    if chaos is not None:
        chaos.process = process

    stdout_thread = threading.Thread(
        target=_relay,
        args=(process.stdout, sys.stdout.buffer, sink, "server_to_client", chaos),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_relay_stderr,
        args=(process.stderr, sys.stderr.buffer, sink),
        daemon=True,
    )
    stdin_thread = threading.Thread(
        target=_relay_stdin,
        args=(
            sys.stdin.buffer,
            process.stdin,
            sys.stdout.buffer,
            sink,
            firewall,
            chaos,
            browser_allowed_origins,
        ),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    stdin_thread.start()
    return_code = process.wait()
    stdout_thread.join(timeout=2)
    stderr_thread.join(timeout=2)
    if stdin_thread.is_alive():
        with contextlib.suppress(OSError):
            sys.stdout.buffer.close()
        stdin_thread.join(timeout=2)
    sink.close_pending(f"server exited with code {return_code}")
    return return_code


def main() -> None:
    parser = argparse.ArgumentParser(description="Transparent stdio MCP trace proxy")
    parser.add_argument("--trace-file", type=Path, required=True)
    parser.add_argument("--trace-id", required=True)
    parser.add_argument(
        "--safety-mode",
        choices=[item.value for item in SafetyMode],
        default=SafetyMode.SAFE_LIVE.value,
    )
    parser.add_argument("--irreversible-tool", action="append", default=[])
    parser.add_argument("--chaos-kind", choices=[item.value for item in ChaosKind])
    parser.add_argument("--chaos-id", default="")
    parser.add_argument("--chaos-tool", default="get_status")
    parser.add_argument("--chaos-delay-seconds", type=float, default=1.0)
    parser.add_argument("--chaos-huge-bytes", type=int, default=262_144)
    parser.add_argument("--browser-allow-origin", action="append", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    raise SystemExit(
        proxy(
            command,
            args.trace_file,
            args.trace_id,
            SafetyMode(args.safety_mode),
            set(args.irreversible_tool),
            ChaosKind(args.chaos_kind) if args.chaos_kind else None,
            args.chaos_id,
            args.chaos_tool,
            args.chaos_delay_seconds,
            args.chaos_huge_bytes,
            set(args.browser_allow_origin),
        )
    )


if __name__ == "__main__":
    main()
