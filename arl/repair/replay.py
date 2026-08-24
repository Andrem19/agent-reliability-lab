from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReplayStats:
    attempts: int
    successes: int
    success_rate: float


@dataclass(frozen=True)
class ReplayGate:
    accepted: bool
    baseline: ReplayStats
    after: ReplayStats
    threshold: float
    reason: str


def sample_replay(check: Callable[[Path], bool], repo: Path, attempts: int) -> ReplayStats:
    if attempts < 1:
        raise ValueError("replay attempts must be positive")
    outcomes = [bool(check(repo)) for _ in range(attempts)]
    successes = sum(outcomes)
    return ReplayStats(attempts, successes, successes / attempts)


def evaluate_replay_gate(
    baseline: ReplayStats,
    after: ReplayStats,
    *,
    threshold: float = 0.8,
) -> ReplayGate:
    accepted = after.success_rate >= threshold and after.success_rate > baseline.success_rate
    reason = "statistical replay improved" if accepted else "replay improvement gate failed"
    return ReplayGate(accepted, baseline, after, threshold, reason)
