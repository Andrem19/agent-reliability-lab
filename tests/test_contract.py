from pathlib import Path

import pytest
from pydantic import ValidationError

from arl.targets.contract import TargetContract, load_target
from arl.targets.registry import TargetRegistry


def test_demo_target_registers() -> None:
    target = load_target(Path("targets/demo/target.yaml"))
    assert target.name == "demo"
    assert target.can_repair
    assert len(target.topology) == 1


def test_registry_finds_clean_demo() -> None:
    targets, errors = TargetRegistry(Path("targets")).discover()
    assert not errors
    assert {"demo", "job-search"} <= targets.keys()


def test_non_white_box_cannot_enable_repair() -> None:
    raw = load_target(Path("targets/demo/target.yaml")).model_dump()
    raw["access_mode"] = "black_box"
    with pytest.raises(ValidationError, match="white_box"):
        TargetContract.model_validate(raw)


def test_v1_rejects_multi_server_topology() -> None:
    raw = load_target(Path("targets/demo/target.yaml")).model_dump()
    raw["topology"] = raw["topology"] * 2
    with pytest.raises(ValidationError, match="exactly one"):
        TargetContract.model_validate(raw)
