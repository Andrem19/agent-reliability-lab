from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class AccessMode(StrEnum):
    BLACK_BOX = "black_box"
    GRAY_BOX = "gray_box"
    WHITE_BOX = "white_box"


class SafetyMode(StrEnum):
    DRY_RUN = "dry_run"
    SAFE_LIVE = "safe_live"
    LIVE = "live"


class ServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo: Path | None = None
    transport: Literal["stdio", "http"]
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None

    @model_validator(mode="after")
    def validate_transport_fields(self) -> ServerConfig:
        if self.transport == "stdio" and not self.command:
            raise ValueError("stdio server requires command")
        if self.transport == "http" and not self.url:
            raise ValueError("http server requires url")
        return self


class TopologyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    server: ServerConfig
    trace_method: Literal["auto", "native_otel", "stdio_proxy", "http_proxy"] = "auto"


class ExecutorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    harness: str
    model: str


class EnvironmentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    adapter: str
    default_mode: SafetyMode = SafetyMode.SAFE_LIVE
    record: bool = True


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    irreversible_tools: list[str] = Field(default_factory=list)
    daily_submit_limit: int = Field(default=0, ge=0)


class RepairConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    staging_branch: str = "autotune/staging"


class OracleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_ground_truth_for_repair: Literal[
        "deterministic", "trace_assertion", "environment_state", "human_gold", "curated"
    ] = "curated"


class TargetContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    target_type: Literal["mcp"] = "mcp"
    access_mode: AccessMode
    topology: list[TopologyEntry] = Field(min_length=1)
    executor: ExecutorConfig
    references: list[ExecutorConfig] = Field(default_factory=list)
    environment: EnvironmentConfig
    safety: SafetyConfig = SafetyConfig()
    layers: dict[str, bool] = Field(default_factory=dict)
    repair: RepairConfig = RepairConfig()
    oracle: OracleConfig = OracleConfig()

    @model_validator(mode="after")
    def enforce_v1_and_repair_capabilities(self) -> TargetContract:
        if len(self.topology) != 1:
            raise ValueError("V1 requires exactly one MCP server in topology")
        if self.repair.enabled and self.access_mode is not AccessMode.WHITE_BOX:
            raise ValueError("repair can only be enabled for white_box targets")
        names = [entry.name for entry in self.topology]
        if len(names) != len(set(names)):
            raise ValueError("topology entry names must be unique")
        return self

    @property
    def can_repair(self) -> bool:
        return self.access_mode is AccessMode.WHITE_BOX and self.repair.enabled

    @property
    def enabled_layers(self) -> list[str]:
        return sorted(name for name, enabled in self.layers.items() if enabled)


def load_target(path: Path) -> TargetContract:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"target contract root must be a mapping: {path}")
    target = TargetContract.model_validate(raw)
    if target.name != path.parent.name:
        raise ValueError(f"target name {target.name!r} must match directory {path.parent.name!r}")
    return target
