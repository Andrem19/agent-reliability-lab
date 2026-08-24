from __future__ import annotations

import re
import shutil
from pathlib import Path

from arl.runtime.timeouts import ProcessResult, run_process

_SAFE_BRANCH = re.compile(r"^[A-Za-z0-9._/-]+$")


class WorktreeManager:
    def __init__(self, repo: Path, worktrees_root: Path) -> None:
        self.repo = repo.resolve()
        self.worktrees_root = worktrees_root.resolve()

    def _git(self, *args: str, timeout: float = 60.0) -> ProcessResult:
        return run_process(("git", "-C", str(self.repo), *args), timeout=timeout)

    def verify_repo(self) -> None:
        result = self._git("rev-parse", "--show-toplevel")
        if result.returncode != 0:
            raise ValueError(f"not a Git repository: {self.repo}")
        discovered = Path(result.stdout.strip()).resolve()
        if discovered != self.repo:
            raise ValueError(f"repository root mismatch: expected {self.repo}, found {discovered}")

    def create(self, branch: str, *, start_point: str = "HEAD") -> Path:
        self.verify_repo()
        if not _SAFE_BRANCH.fullmatch(branch) or ".." in branch:
            raise ValueError(f"unsafe branch name: {branch!r}")
        leaf = branch.replace("/", "-")
        target = (self.worktrees_root / leaf).resolve()
        if target.parent != self.worktrees_root:
            raise ValueError("worktree target escaped configured root")
        if target.exists():
            raise FileExistsError(target)
        self.worktrees_root.mkdir(parents=True, exist_ok=True)
        result = self._git("worktree", "add", "-b", branch, str(target), start_point)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return target

    def remove(self, target: Path) -> None:
        self.verify_repo()
        resolved = target.resolve()
        if resolved.parent != self.worktrees_root or not resolved.exists():
            raise ValueError(f"refusing to remove unverified worktree: {resolved}")
        status = run_process(("git", "-C", str(resolved), "status", "--porcelain"))
        dirty_paths = [line[3:].strip().replace("\\", "/") for line in status.stdout.splitlines()]
        allowed_runtime_parts = {"__pycache__", ".pytest_cache"}
        if dirty_paths and not all(
            any(part in allowed_runtime_parts for part in Path(value).parts)
            for value in dirty_paths
        ):
            raise RuntimeError(f"worktree contains non-runtime changes: {dirty_paths}")
        for directory_name in allowed_runtime_parts:
            for artifact_dir in resolved.rglob(directory_name):
                artifact = artifact_dir.resolve()
                if resolved not in artifact.parents:
                    raise RuntimeError(f"runtime artifact escaped worktree: {artifact}")
                shutil.rmtree(artifact)
        result = self._git("worktree", "remove", str(resolved))
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
