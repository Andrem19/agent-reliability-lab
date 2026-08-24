from __future__ import annotations

import shutil
import sys
from pathlib import Path

import yaml

from arl.harnesses.zcode import ZCodeRunResult, _trace_tool_calls
from arl.runtime.timeouts import run_process
from arl.targets.contract import TargetContract
from arl.tracing.otel_model import new_trace_id


class DSHHarness:
    def __init__(self, executable: str | None = None, settings_path: Path | None = None) -> None:
        self.executable = executable or shutil.which("dsh.cmd") or shutil.which("dsh")
        self.settings_path = settings_path or Path.home() / ".dsh" / "settings.yaml"

    def selected_model(self) -> tuple[str, str]:
        settings = yaml.safe_load(self.settings_path.read_text(encoding="utf-8")) or {}
        selection = settings.get("agent-default-model", {})
        return str(selection.get("provider", "unknown")), str(selection.get("model", "unknown"))

    def _patch_config(
        self,
        target: TargetContract,
        trace_path: Path,
        trace_id: str,
    ) -> list[dict]:
        server = target.topology[0].server
        if server.transport != "stdio" or server.command is None:
            raise ValueError("L5 DSH adapter requires a stdio target")
        server_command = shutil.which(server.command) or server.command
        server_args = list(server.args)
        if "--directory" in server_args:
            index = server_args.index("--directory") + 1
            directory = Path(server_args[index])
            if not directory.is_absolute():
                directory = (Path.cwd() / directory).resolve()
            server_args[index] = str(directory)
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
            server_command,
            *server_args,
        ]
        return [
            {
                "insert": [
                    {
                        "id": "mcp-work-researcher",
                        "name": "@deepseek-ai/dsh-mcp-client",
                        "config": {
                            "serverName": target.topology[0].name,
                            "transport": "stdio",
                            "command": sys.executable,
                            "args": proxy_args,
                            "toolCallTimeoutMs": 180000,
                        },
                    }
                ]
            }
        ]

    def run_job_mcp_smoke(
        self,
        target: TargetContract,
        artifacts_dir: Path,
    ) -> ZCodeRunResult:
        trace_id = new_trace_id()
        trace_path = artifacts_dir / "dsh-job-search-mcp-trace.jsonl"
        provider, model = self.selected_model()
        model_id = f"{provider}/{model}"
        if not self.executable:
            return ZCodeRunResult(
                False, None, trace_id, "", trace_path, model_id, "DSH executable unavailable"
            )
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        patch_path = artifacts_dir / "dsh-trace-proxy.patch.yml"
        patch_path.write_text(
            yaml.safe_dump(
                self._patch_config(target, trace_path, trace_id),
                sort_keys=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        prompt = (
            "Use the work-researcher get_status MCP tool exactly once and use no other tool. "
            "Do not call application, browser, write, sync, push, or submission tools. "
            "Reply with the exact token ARL_DSH_JOB_MCP_OK and a short status summary."
        )
        process = run_process(
            (self.executable, "--profile", "headless", "--patch", str(patch_path), prompt),
            timeout=300,
        )
        calls, _ = _trace_tool_calls(trace_path)
        token_seen = "ARL_DSH_JOB_MCP_OK" in process.stdout
        passed = (
            not process.timed_out
            and process.returncode == 0
            and calls == ["get_status"]
            and token_seen
        )
        reasons = []
        if process.timed_out or process.returncode != 0:
            reasons.append("DSH process failed or timed out")
        if calls != ["get_status"]:
            reasons.append(f"MCP tool sequence mismatch: {calls}")
        if not token_seen:
            reasons.append("response token missing")
        return ZCodeRunResult(
            passed,
            None,
            trace_id,
            process.stdout,
            trace_path,
            model_id,
            "DSH get_status traced" if passed else "; ".join(reasons),
        )
