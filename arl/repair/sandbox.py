from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from arl.runtime.timeouts import ProcessResult, run_process

SAFE_ENV_KEYS = {
    "COMSPEC",
    "PATH",
    "PATHEXT",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "WINDIR",
}


def sanitized_environment() -> dict[str, str]:
    clean = {key: value for key, value in os.environ.items() if key.upper() in SAFE_ENV_KEYS}
    clean["PYTHONNOUSERSITE"] = "1"
    clean["PYTHONDONTWRITEBYTECODE"] = "1"
    clean["ARL_FIXER_SANDBOX"] = "L0"
    return clean


@dataclass(frozen=True)
class PatchValidation:
    accepted: bool
    reason: str
    changed_paths: tuple[str, ...]
    diff_hash: str


class PatchPolicy:
    _path_line = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)
    _dangerous = (
        re.compile(r"\bos\.system\s*\("),
        re.compile(r"\bsubprocess\.(?:run|Popen|call)\s*\("),
        re.compile(r"\beval\s*\("),
        re.compile(r"\bexec\s*\("),
        re.compile(r"(?i)(api[-_]?key|password|private[-_]?key)\s*="),
    )

    def validate(self, diff: str, allowed_paths: tuple[str, ...]) -> PatchValidation:
        digest = hashlib.sha256(diff.encode("utf-8")).hexdigest()
        paths = tuple(self._path_line.findall(diff))
        if not paths:
            return PatchValidation(False, "diff has no changed paths", paths, digest)
        for value in paths:
            path = PurePosixPath(value)
            if path.is_absolute() or ".." in path.parts:
                return PatchValidation(False, f"unsafe patch path: {value}", paths, digest)
            if not any(path.match(pattern) for pattern in allowed_paths):
                return PatchValidation(False, f"path outside repair domain: {value}", paths, digest)
        added = "\n".join(
            line[1:]
            for line in diff.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        if any(pattern.search(added) for pattern in self._dangerous):
            return PatchValidation(False, "dangerous code pattern in added lines", paths, digest)
        return PatchValidation(True, "patch policy passed", paths, digest)


class L0Fixer:
    def __init__(self, worktree: Path) -> None:
        self.worktree = worktree.resolve()

    def apply(
        self, diff: str, policy: PatchPolicy, allowed_paths: tuple[str, ...]
    ) -> PatchValidation:
        validation = policy.validate(diff, allowed_paths)
        if not validation.accepted:
            return validation
        completed = subprocess.run(
            ("git", "-C", str(self.worktree), "apply", "--whitespace=error", "-"),
            input=diff,
            capture_output=True,
            text=True,
            env=sanitized_environment(),
            timeout=30,
            check=False,
        )
        if completed.returncode != 0:
            return PatchValidation(
                False,
                f"git apply failed: {completed.stderr.strip()}",
                validation.changed_paths,
                validation.diff_hash,
            )
        return validation

    def run(self, command: tuple[str, ...], timeout: float = 60) -> ProcessResult:
        return run_process(
            command,
            cwd=self.worktree,
            env=sanitized_environment(),
            timeout=timeout,
        )
