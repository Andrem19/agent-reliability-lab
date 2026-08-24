from __future__ import annotations

from dataclasses import dataclass

from arl.isolation.hypotheses import Attribution
from arl.targets.contract import AccessMode, TargetContract


@dataclass(frozen=True)
class RepairDecision:
    allowed: bool
    domain: str
    reason: str


STRONG_ORACLES = {"DETERMINISTIC", "TRACE_ASSERTION", "ENVIRONMENT_STATE", "HUMAN_GOLD"}
NON_REPAIR_DOMAINS = {"ORACLE", "SCENARIO", "NO_REPAIR"}


def route_repair(
    target: TargetContract,
    attribution: Attribution,
    *,
    oracle_type: str,
    generated: bool = False,
) -> RepairDecision:
    if target.access_mode is not AccessMode.WHITE_BOX or not target.repair.enabled:
        return RepairDecision(False, "NO_REPAIR", "target access mode forbids repair")
    if not attribution.confirmed:
        return RepairDecision(False, "NO_REPAIR", "attribution is not confirmed")
    if attribution.repair_domain in NON_REPAIR_DOMAINS:
        return RepairDecision(False, "NO_REPAIR", f"{attribution.top.value} is report-only")
    if generated and oracle_type.upper() not in STRONG_ORACLES:
        return RepairDecision(False, "NO_REPAIR", "generated scenario has weak ground truth")
    return RepairDecision(True, attribution.repair_domain, "localized repair permitted")
