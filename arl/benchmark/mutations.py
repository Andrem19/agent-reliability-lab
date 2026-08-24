from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from arl.isolation.hypotheses import HypothesisEngine


@dataclass(frozen=True)
class MutationCaseResult:
    mutation_id: str
    predicted: str
    expected: str
    top3: tuple[str, ...]
    repair_domain: str
    correct_top1: bool
    correct_top3: bool


@dataclass(frozen=True)
class MutationSuiteReport:
    cases: tuple[MutationCaseResult, ...]
    top1_accuracy: float
    top3_accuracy: float
    false_repair_rate: float

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected mapping: {path}")
    return value


def run_mutation_suite(pack_dir: Path) -> MutationSuiteReport:
    catalog = _load_yaml(pack_dir / "catalog.yaml")["mutations"]
    truth = _load_yaml(pack_dir / "ground_truth.yaml")["mutations"]
    engine = HypothesisEngine()
    cases: list[MutationCaseResult] = []
    for entry in catalog:
        mutation_id = entry["id"]
        evidence = _load_yaml(pack_dir / "fixtures" / entry["fixture"])["evidence"]
        attribution = engine.attribute(evidence)
        expected = truth[mutation_id]["attribution"]
        top3 = tuple(item.hypothesis.value for item in attribution.ranking[:3])
        cases.append(
            MutationCaseResult(
                mutation_id,
                attribution.top.value,
                expected,
                top3,
                attribution.repair_domain,
                attribution.top.value == expected,
                expected in top3,
            )
        )
    top1 = sum(item.correct_top1 for item in cases) / len(cases)
    top3 = sum(item.correct_top3 for item in cases) / len(cases)
    baseline = engine.attribute({"failure": False})
    false_repair_rate = 0.0 if baseline.repair_domain == "NO_REPAIR" else 1.0
    return MutationSuiteReport(tuple(cases), top1, top3, false_repair_rate)
