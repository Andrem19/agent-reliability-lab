from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from arl.targets.contract import TargetContract, load_target


@dataclass(frozen=True)
class TargetLoadError:
    path: Path
    message: str


class TargetRegistry:
    def __init__(self, targets_dir: Path) -> None:
        self.targets_dir = targets_dir

    def discover(self) -> tuple[dict[str, TargetContract], list[TargetLoadError]]:
        targets: dict[str, TargetContract] = {}
        errors: list[TargetLoadError] = []
        if not self.targets_dir.exists():
            return targets, errors
        for path in sorted(self.targets_dir.glob("*/target.yaml")):
            try:
                target = load_target(path)
                if target.name in targets:
                    raise ValueError(f"duplicate target name: {target.name}")
                targets[target.name] = target
            except (OSError, ValueError, ValidationError) as exc:
                errors.append(TargetLoadError(path=path, message=str(exc)))
        return targets, errors

    def get(self, name: str) -> TargetContract:
        targets, errors = self.discover()
        if errors:
            detail = "; ".join(f"{e.path}: {e.message}" for e in errors)
            raise ValueError(f"invalid target pack(s): {detail}")
        try:
            return targets[name]
        except KeyError as exc:
            raise KeyError(f"unknown target {name!r}") from exc
