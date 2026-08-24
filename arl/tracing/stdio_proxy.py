from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, BinaryIO

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


def _relay(
    source: BinaryIO,
    destination: BinaryIO,
    sink: TraceSink | None,
    direction: str,
) -> None:
    try:
        while line := source.readline():
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
) -> None:
    try:
        while line := source.readline():
            sink.message("client_to_server", line)
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                message = None
            params = message.get("params", {}) if isinstance(message, dict) else {}
            is_tool_call = isinstance(message, dict) and message.get("method") == "tools/call"
            tool_name = params.get("name", "") if isinstance(params, dict) else ""
            decision = (
                firewall.decide(tool_name, classify_tool(tool_name)) if is_tool_call else None
            )
            if decision is not None and not decision.allowed:
                response = {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "result": {
                        "content": [{"type": "text", "text": decision.reason}],
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

    stdout_thread = threading.Thread(
        target=_relay,
        args=(process.stdout, sys.stdout.buffer, sink, "server_to_client"),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_relay_stderr,
        args=(process.stderr, sys.stderr.buffer, sink),
        daemon=True,
    )
    stdin_thread = threading.Thread(
        target=_relay_stdin,
        args=(sys.stdin.buffer, process.stdin, sys.stdout.buffer, sink, firewall),
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
        )
    )


if __name__ == "__main__":
    main()
