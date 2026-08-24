from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, BinaryIO


@dataclass(frozen=True)
class SoakState:
    status: str
    completed_cycles: int
    failures: int
    started_monotonic: float
    elapsed_seconds: float
    goal_hours: float | None = None
    goal_cycles: int | None = None
    metadata: dict[str, Any] | None = None


class SoakRunner:
    def __init__(
        self,
        checkpoint: Path,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.checkpoint = checkpoint
        self.clock = clock
        self.sleeper = sleeper

    def run(
        self,
        cycle: Callable[[int], bool],
        *,
        hours: float | None = None,
        max_cycles: int | None = None,
        interval_seconds: float = 0,
        metadata: dict[str, Any] | None = None,
        resume_from: SoakState | None = None,
    ) -> SoakState:
        with self._lease():
            return self._run_locked(
                cycle,
                hours=hours,
                max_cycles=max_cycles,
                interval_seconds=interval_seconds,
                metadata=metadata,
                resume_from=resume_from,
            )

    def _run_locked(
        self,
        cycle: Callable[[int], bool],
        *,
        hours: float | None,
        max_cycles: int | None,
        interval_seconds: float,
        metadata: dict[str, Any] | None,
        resume_from: SoakState | None,
    ) -> SoakState:
        if resume_from is not None:
            hours = hours if hours is not None else resume_from.goal_hours
            max_cycles = max_cycles if max_cycles is not None else resume_from.goal_cycles
            metadata = metadata if metadata is not None else resume_from.metadata
        if hours is None and max_cycles is None:
            raise ValueError("hours or max_cycles is required")
        if interval_seconds < 0:
            raise ValueError("interval_seconds cannot be negative")
        started = self.clock()
        completed = resume_from.completed_cycles if resume_from else 0
        failures = resume_from.failures if resume_from else 0
        elapsed_offset = resume_from.elapsed_seconds if resume_from else 0.0
        self.checkpoint.with_suffix(".stop").unlink(missing_ok=True)
        while True:
            elapsed = elapsed_offset + self.clock() - started
            if hours is not None and elapsed >= hours * 3600:
                break
            if max_cycles is not None and completed >= max_cycles:
                break
            if self.checkpoint.with_suffix(".stop").exists():
                status = "stopped"
                state = SoakState(
                    status, completed, failures, started, elapsed, hours, max_cycles, metadata
                )
                self._save(state)
                return state
            try:
                if not cycle(completed + 1):
                    failures += 1
            except Exception:
                failures += 1
            completed += 1
            current_elapsed = elapsed_offset + self.clock() - started
            self._save(
                SoakState(
                    "running",
                    completed,
                    failures,
                    started,
                    current_elapsed,
                    hours,
                    max_cycles,
                    metadata,
                )
            )
            if interval_seconds:
                self.sleeper(interval_seconds)
        state = SoakState(
            "completed",
            completed,
            failures,
            started,
            elapsed_offset + self.clock() - started,
            hours,
            max_cycles,
            metadata,
        )
        self._save(state)
        return state

    @contextmanager
    def _lease(self) -> Iterator[None]:
        """Hold an OS-backed lease so concurrent processes cannot share a checkpoint."""
        lock_path = self.checkpoint.with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("a+b")
        try:
            self._lock_handle(handle)
        except OSError as exc:
            handle.close()
            raise RuntimeError(f"soak checkpoint already leased: {self.checkpoint}") from exc
        try:
            yield
        finally:
            self._unlock_handle(handle)
            handle.close()

    @staticmethod
    def _lock_handle(handle: BinaryIO) -> None:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _unlock_handle(handle: BinaryIO) -> None:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _save(self, state: SoakState) -> None:
        self.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.checkpoint.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")
        temporary.replace(self.checkpoint)

    def load(self) -> SoakState:
        raw = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        return SoakState(**raw)
