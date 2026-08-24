from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from arl.harnesses.zcode import ZCodeHarness, ZCodeRunResult
from arl.runtime.timeouts import run_process
from arl.safety.redaction import SecretRedactor
from arl.targets.contract import TargetContract
from arl.tracing.otel_model import new_trace_id


@dataclass(frozen=True)
class SubscriptionHealth:
    available: bool
    provider_id: str
    model_id: str
    detail: str


class ZCodeSubscriptionProvider:
    """Ephemeral bridge from ZCode Desktop's native Coding Plan to its bundled CLI."""

    provider_id = "builtin:zai-coding-plan"
    model_id = "GLM-5.3"

    def __init__(
        self,
        desktop_config: Path | None = None,
        zcode_cli: Path | None = None,
    ) -> None:
        self.desktop_config = desktop_config or Path.home() / ".zcode" / "v2" / "config.json"
        self.harness = ZCodeHarness(zcode_cli)

    def _provider(self) -> dict:
        raw = json.loads(self.desktop_config.read_text(encoding="utf-8"))
        provider = raw.get("provider", {}).get(self.provider_id)
        if not isinstance(provider, dict):
            raise ValueError(f"native provider unavailable: {self.provider_id}")
        return deepcopy(provider)

    def health(self) -> SubscriptionHealth:
        try:
            provider = self._provider()
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return SubscriptionHealth(
                False, self.provider_id, self.model_id, f"{type(exc).__name__}: {exc}"
            )
        models = provider.get("models", {})
        endpoint = provider.get("options", {}).get("baseURL")
        credential_present = bool(provider.get("options", {}).get("apiKey"))
        available = self.model_id in models and bool(endpoint) and credential_present
        detail = (
            "native Z.ai Coding Plan credential and GLM-5.3 catalog entry present"
            if available
            else "provider exists but model, endpoint, or credential is unavailable"
        )
        return SubscriptionHealth(available, self.provider_id, self.model_id, detail)

    def has_desktop_provider(self, base_url: str) -> bool:
        """Check catalog/credential presence without returning credential material."""
        try:
            raw = json.loads(self.desktop_config.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return False
        expected = base_url.rstrip("/").casefold()
        for provider in raw.get("provider", {}).values():
            if not isinstance(provider, dict):
                continue
            options = provider.get("options", {})
            actual = str(options.get("baseURL", "")).rstrip("/").casefold()
            if actual == expected and options.get("apiKey"):
                return True
        return False

    def run_job_mcp_smoke(
        self,
        target: TargetContract,
        artifacts_dir: Path,
    ) -> ZCodeRunResult:
        health = self.health()
        trace_id = new_trace_id()
        trace_path = artifacts_dir / "glm53-job-search-mcp-trace.jsonl"
        if not health.available:
            return ZCodeRunResult(
                False, None, trace_id, "", trace_path, self.model_id, health.detail
            )
        if self.harness.node is None or not self.harness.zcode_cli.exists():
            return ZCodeRunResult(
                False,
                None,
                trace_id,
                "",
                trace_path,
                self.model_id,
                "ZCode bundled CLI unavailable",
            )

        artifacts_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="zai-runtime-", dir=artifacts_dir) as temporary:
            workspace = Path(temporary)
            config_dir = workspace / ".zcode"
            config_dir.mkdir()
            config = self.harness._workspace_config(target, workspace, trace_path, trace_id)
            config["provider"] = {self.provider_id: self._provider()}
            config["model"] = {"main": f"{self.provider_id}/{self.model_id}"}
            (config_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
            isolated_home = workspace / "home"
            isolated_home.mkdir()
            environment = self._isolated_environment(isolated_home)
            prompt = (
                "Use the work-researcher get_status MCP tool exactly once. "
                "Do not call application, browser, write, or submission tools. "
                "Then reply with ARL_GLM53_JOB_MCP_OK and a short status summary."
            )
            command = (
                self.harness.node,
                str(self.harness.zcode_cli),
                "--cwd",
                str(workspace),
                "--mode",
                "plan",
                "--json",
                "--prompt",
                prompt,
            )
            process = run_process(command, env=environment, timeout=300)

        redactor = SecretRedactor()
        if process.timed_out or process.returncode != 0:
            reason = redactor.redact_text(
                "ZCode subscription process failed or timed out: " + process.stderr[-1500:]
            )
            return ZCodeRunResult(False, None, trace_id, "", trace_path, self.model_id, reason)
        try:
            payload = json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            return ZCodeRunResult(
                False,
                None,
                trace_id,
                redactor.redact_text(process.stdout),
                trace_path,
                self.model_id,
                str(exc),
            )
        tool_seen = _trace_has_tool(trace_path, "get_status")
        response = redactor.redact_text(str(payload.get("response", "")))
        token_seen = "ARL_GLM53_JOB_MCP_OK" in response
        passed = tool_seen and token_seen
        return ZCodeRunResult(
            passed,
            payload.get("sessionId"),
            trace_id,
            response,
            trace_path,
            self.model_id,
            "native GLM-5.3 get_status traced"
            if passed
            else "missing tool trace or response token",
        )

    @staticmethod
    def _isolated_environment(home: Path) -> dict[str, str]:
        allowed = {
            "APPDATA",
            "COMSPEC",
            "LOCALAPPDATA",
            "PATH",
            "PATHEXT",
            "SYSTEMDRIVE",
            "SYSTEMROOT",
            "TEMP",
            "TMP",
            "WINDIR",
        }
        environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
        environment["USERPROFILE"] = str(home)
        environment["HOME"] = str(home)
        environment["PYTHONNOUSERSITE"] = "1"
        return environment


def _trace_has_tool(trace_path: Path, tool_name: str) -> bool:
    if not trace_path.exists():
        return False
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = record.get("message", {})
        params = message.get("params", {}) if isinstance(message, dict) else {}
        if message.get("method") == "tools/call" and params.get("name") == tool_name:
            return True
    return False
