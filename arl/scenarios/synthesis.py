from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from arl.safety.risk_class import HIGH_RISK, RiskClass

STRONG_ORACLES = {"DETERMINISTIC", "TRACE_ASSERTION", "ENVIRONMENT_STATE", "HUMAN_GOLD"}


@dataclass(frozen=True)
class SynthesizedScenario:
    scenario_id: str
    scenario_type: str
    tool: str
    arguments: dict[str, Any]
    oracle_type: str | None
    risk_classes: frozenset[RiskClass]
    needs_review: bool = False
    autonomous_repair: bool = False


def lint_scenario(
    scenario: SynthesizedScenario,
    *,
    tool_schemas: dict[str, dict[str, Any]],
    existing_fingerprints: set[str] | None = None,
) -> SynthesizedScenario:
    if scenario.tool not in tool_schemas:
        raise ValueError(f"unknown tool: {scenario.tool}")
    schema = tool_schemas[scenario.tool]
    missing = set(schema.get("required", [])) - set(scenario.arguments)
    if missing:
        raise ValueError(f"missing required arguments: {sorted(missing)}")
    fingerprint = json.dumps(
        [scenario.scenario_type, scenario.tool, scenario.arguments], sort_keys=True
    )
    if existing_fingerprints and fingerprint in existing_fingerprints:
        raise ValueError("duplicate synthesized scenario")
    strong = scenario.oracle_type in STRONG_ORACLES
    review = bool(scenario.risk_classes & HIGH_RISK) or not strong
    return SynthesizedScenario(
        scenario.scenario_id,
        scenario.scenario_type,
        scenario.tool,
        scenario.arguments,
        scenario.oracle_type,
        scenario.risk_classes,
        review,
        strong and not review,
    )
