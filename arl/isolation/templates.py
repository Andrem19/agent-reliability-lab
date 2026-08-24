from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExperimentTemplate:
    id: str
    description: str
    cost: float
    llm_calls: int
    risk: int
    discriminates: tuple[str, ...]

    @property
    def rank_score(self) -> float:
        return len(self.discriminates) / self.cost


CATALOG: tuple[ExperimentTemplate, ...] = (
    ExperimentTemplate("T1", "Direct replay", 1.0, 0, 0, ("below_agent", "above_agent")),
    ExperimentTemplate("T1b", "Valid-argument direct replay", 1.0, 0, 0, ("MCP", "caller")),
    ExperimentTemplate("T2", "Mock-environment direct call", 1.5, 0, 0, ("MCP", "environment")),
    ExperimentTemplate("T9", "Repeat N times", 2.0, 0, 0, ("FLAKY", "stable")),
    ExperimentTemplate("T3", "Reference-model matrix", 5.0, 2, 0, ("executor", "common")),
    ExperimentTemplate("T4", "Harness swap matrix", 6.0, 2, 0, ("MODEL", "HARNESS", "interaction")),
    ExperimentTemplate("T8", "Independent oracle", 3.0, 1, 0, ("ORACLE_ERROR", "system")),
)
