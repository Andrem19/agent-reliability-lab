from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from arl.repair.regression import RegressionResult, run_regressions
from arl.repair.replay import ReplayGate, evaluate_replay_gate, sample_replay
from arl.repair.sandbox import L0Fixer, PatchPolicy, PatchValidation
from arl.repair.staging import promote_to_staging
from arl.repair.worktree import WorktreeManager
from arl.runtime.timeouts import run_process


@dataclass(frozen=True)
class RepairPipelineResult:
    accepted: bool
    status: str
    validation: PatchValidation
    regressions: tuple[RegressionResult, ...]
    replay: ReplayGate | None
    commit: str | None
    reason: str


class RepairPipeline:
    def __init__(self, repo: Path, worktrees_root: Path) -> None:
        self.repo = repo.resolve()
        self.manager = WorktreeManager(self.repo, worktrees_root)
        self.policy = PatchPolicy()

    def run(
        self,
        *,
        diff: str,
        allowed_paths: tuple[str, ...],
        regression_suites: tuple[tuple[str, tuple[str, ...]], ...],
        replay_check: Callable[[Path], bool],
        replay_attempts: int = 1,
        commit_message: str = "autofix: localized repair",
    ) -> RepairPipelineResult:
        validation = self.policy.validate(diff, allowed_paths)
        if not validation.accepted:
            return RepairPipelineResult(
                False, "rejected_policy", validation, (), None, None, validation.reason
            )

        baseline = sample_replay(replay_check, self.repo, replay_attempts)
        branch = f"autofix/cycle-{uuid.uuid4().hex[:12]}"
        worktree = self.manager.create(branch)
        fixer = L0Fixer(worktree)
        applied = fixer.apply(diff, self.policy, allowed_paths)
        if not applied.accepted:
            return RepairPipelineResult(
                False, "apply_failed", applied, (), None, None, applied.reason
            )

        regressions = run_regressions(fixer, regression_suites)
        if not regressions or not all(item.passed for item in regressions):
            return RepairPipelineResult(
                False,
                "regression_failed",
                applied,
                regressions,
                None,
                None,
                "regression gate failed",
            )

        recorded = sample_replay(replay_check, worktree, 1)
        if recorded.success_rate != 1.0:
            return RepairPipelineResult(
                False,
                "recorded_replay_failed",
                applied,
                regressions,
                None,
                None,
                "recorded replay failed",
            )
        after = sample_replay(replay_check, worktree, replay_attempts)
        replay = evaluate_replay_gate(baseline, after)
        if not replay.accepted:
            return RepairPipelineResult(
                False,
                "live_replay_failed",
                applied,
                regressions,
                replay,
                None,
                replay.reason,
            )

        add = run_process(("git", "-C", str(worktree), "add", "--", *applied.changed_paths))
        if add.returncode != 0:
            raise RuntimeError(add.stderr.strip())
        commit_result = run_process(
            ("git", "-C", str(worktree), "commit", "-m", commit_message), timeout=60
        )
        if commit_result.returncode != 0:
            raise RuntimeError(commit_result.stderr.strip() or commit_result.stdout.strip())
        rev = run_process(("git", "-C", str(worktree), "rev-parse", "HEAD"))
        commit = rev.stdout.strip()
        promote_to_staging(self.repo, commit)
        self.manager.remove(worktree)
        return RepairPipelineResult(
            True, "accepted", applied, regressions, replay, commit, "all repair gates passed"
        )
