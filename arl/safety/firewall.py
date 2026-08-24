from __future__ import annotations

from dataclasses import dataclass

from arl.safety.risk_class import HIGH_RISK, RiskClass
from arl.targets.contract import SafetyMode


@dataclass(frozen=True)
class FirewallDecision:
    allowed: bool
    reason: str
    risks: frozenset[RiskClass]


class SideEffectFirewall:
    def __init__(
        self,
        mode: SafetyMode,
        *,
        irreversible_tools: set[str] | None = None,
    ) -> None:
        self.mode = mode
        self.irreversible_tools = {item.casefold() for item in irreversible_tools or set()}

    def decide(self, tool_name: str, risks: set[RiskClass]) -> FirewallDecision:
        effective = set(risks)
        if tool_name.casefold() in self.irreversible_tools:
            effective.add(RiskClass.EXTERNAL_SUBMIT)
        if self.mode is SafetyMode.DRY_RUN and effective != {RiskClass.READ}:
            return FirewallDecision(False, "DRY_RUN blocks side effects", frozenset(effective))
        if self.mode is SafetyMode.SAFE_LIVE and effective & HIGH_RISK:
            return FirewallDecision(
                False,
                "SAFE_LIVE blocks irreversible action",
                frozenset(effective),
            )
        return FirewallDecision(True, "policy permits action", frozenset(effective))
