from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class TimeoutConfig(BaseModel):
    process_seconds: float = Field(default=60.0, gt=0)
    doctor_seconds: float = Field(default=5.0, gt=0)


class PathConfig(BaseModel):
    state_dir: Path = Path(".arl")
    targets_dir: Path = Path("targets")
    reports_dir: Path = Path("reports/runtime")


class LabConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paths: PathConfig = PathConfig()
    timeouts: TimeoutConfig = TimeoutConfig()
    default_safety_mode: str = "safe_live"
    reference_target_repo: Path = Path("../WORK_RESEARCHER_MCP")
    providers: dict[str, dict[str, Any]] = Field(default_factory=dict)
    roles: dict[str, dict[str, Any]] = Field(default_factory=dict)

    def resolve(self, root: Path) -> LabConfig:
        data = self.model_dump()
        for key in ("state_dir", "targets_dir", "reports_dir"):
            value = Path(data["paths"][key])
            if not value.is_absolute():
                data["paths"][key] = root / value
        return LabConfig.model_validate(data)


def load_config(path: Path | None = None, *, root: Path | None = None) -> LabConfig:
    root = (root or Path.cwd()).resolve()
    config_path = path or root / "arl.yaml"
    raw: dict[str, Any] = {}
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if loaded is not None and not isinstance(loaded, dict):
            raise ValueError(f"configuration root must be a mapping: {config_path}")
        raw = loaded or {}
    return LabConfig.model_validate(raw).resolve(root)
