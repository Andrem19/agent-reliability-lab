from __future__ import annotations

import json
import os
import shutil
import sqlite3
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from arl.config import LabConfig
from arl.providers.zcode_subscription import ZCodeSubscriptionProvider
from arl.runtime.timeouts import run_process
from arl.storage.database import Database
from arl.targets.registry import TargetRegistry


class CheckStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: CheckStatus
    detail: str
    required: bool = False


def _command_check(name: str, args: tuple[str, ...], required: bool = False) -> CheckResult:
    executable = shutil.which(args[0])
    if executable is None:
        return CheckResult(
            name, CheckStatus.FAIL if required else CheckStatus.WARN, "not found", required
        )
    resolved_command: tuple[str, ...]
    if Path(executable).suffix.casefold() == ".ps1":
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if powershell is None:
            return CheckResult(name, CheckStatus.WARN, f"PowerShell shim cannot run: {executable}")
        resolved_command = (powershell, "-NoProfile", "-File", executable, *args[1:])
    else:
        resolved_command = (executable, *args[1:])
    result = run_process(resolved_command, timeout=5)
    first_line = (result.stdout or result.stderr).strip().splitlines()
    detail = first_line[0] if first_line else executable
    status = CheckStatus.PASS if result.returncode == 0 else CheckStatus.WARN
    return CheckResult(name, status, detail, required)


def _zcode_check() -> CheckResult:
    executable = Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "ZCode/ZCode.exe"
    bundled = executable.parent / "resources/glm/zcode.cjs"
    if not executable.exists():
        return CheckResult("Z Code", CheckStatus.WARN, "desktop executable not found")
    if shutil.which("node") and bundled.exists():
        result = run_process(("node", str(bundled), "--version"), timeout=5)
        cli_version = result.stdout.strip() if result.returncode == 0 else "unavailable"
    else:
        cli_version = "unavailable"
    return CheckResult("Z Code", CheckStatus.PASS, f"desktop installed; bundled CLI {cli_version}")


def _qwen_check() -> CheckResult:
    base_url = os.environ.get("ARL_QWEN_BASE_URL", "http://127.0.0.1:1234/v1")
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/models", timeout=2) as response:
            body = json.load(response)
        ids = [item.get("id", "") for item in body.get("data", [])]
        matches = [model for model in ids if "qwen3.8-27b" in model.lower()]
        if matches:
            detail = f"available: {matches[0]}"
            router_url = f"{base_url.removesuffix('/v1').rstrip('/')}/models"
            try:
                with urllib.request.urlopen(router_url, timeout=2) as response:
                    router = json.load(response)
                entry = next(
                    item for item in router.get("data", []) if item.get("id") == matches[0]
                )
                owner = entry.get("owned_by", "unknown")
                modalities = entry.get("architecture", {}).get("input_modalities", [])
                mode = "vision" if "image" in modalities else "text"
                status = entry.get("status", {}).get("value", "unknown")
                detail = f"{owner} {matches[0]} {status}; mode={mode}"
            except (OSError, ValueError, StopIteration, urllib.error.URLError):
                pass
            return CheckResult("Qwen executor", CheckStatus.PASS, detail)
        return CheckResult(
            "Qwen executor",
            CheckStatus.WARN,
            f"local OpenAI-compatible endpoint reachable; model absent ({len(ids)} models)",
        )
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return CheckResult(
            "Qwen executor",
            CheckStatus.WARN,
            "test_infra_unavailable: local Qwen /models unreachable "
            f"({type(exc).__name__})",
        )


def _target_check(config: LabConfig) -> CheckResult:
    targets, errors = TargetRegistry(config.paths.targets_dir).discover()
    if errors:
        return CheckResult("Target contracts", CheckStatus.FAIL, f"{len(errors)} invalid", True)
    if "demo" not in targets:
        return CheckResult("Target contracts", CheckStatus.FAIL, "demo target missing", True)
    return CheckResult(
        "Target contracts", CheckStatus.PASS, f"{len(targets)} valid: {', '.join(targets)}", True
    )


def _zai_subscription_check() -> CheckResult:
    health = ZCodeSubscriptionProvider().health()
    return CheckResult(
        "Z.ai Coding Plan / GLM-5.3",
        CheckStatus.PASS if health.available else CheckStatus.WARN,
        health.detail,
    )


def run_doctor(config: LabConfig) -> list[CheckResult]:
    results = [
        _command_check("Python", ("python", "--version"), required=True),
        _command_check("Git", ("git", "--version"), required=True),
        _command_check("Node", ("node", "--version")),
        _command_check("Docker sandbox L1", ("docker", "--version")),
        CheckResult(
            "Subprocess sandbox L0",
            CheckStatus.PASS,
            "available; sanitized env enforced at fixer boundary",
        ),
        _zcode_check(),
        _zai_subscription_check(),
        _qwen_check(),
        _command_check("DeepSeek Harness", ("dsh", "--version")),
        _target_check(config),
    ]
    reference = config.reference_target_repo
    results.append(
        CheckResult(
            "Reference MCP repository",
            CheckStatus.PASS if (reference / "pyproject.toml").exists() else CheckStatus.WARN,
            str(reference),
        )
    )
    try:
        version = Database(config.paths.state_dir / "arl.db").healthcheck()
        results.append(
            CheckResult("SQLite", CheckStatus.PASS, f"{version}; WAL schema initialized", True)
        )
    except sqlite3.Error as exc:
        results.append(CheckResult("SQLite", CheckStatus.FAIL, str(exc), True))
    return results


def doctor_ok(results: list[CheckResult]) -> bool:
    return all(not item.required or item.status is not CheckStatus.FAIL for item in results)
