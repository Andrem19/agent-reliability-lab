from __future__ import annotations

from arl.isolation.templates import CATALOG, ExperimentTemplate


class ExperimentPlanner:
    """Deterministic discrimination-per-cost ranking with non-LLM probes first."""

    def plan(self, available: set[str] | None = None) -> tuple[ExperimentTemplate, ...]:
        candidates = [item for item in CATALOG if available is None or item.id in available]
        return tuple(
            sorted(
                candidates,
                key=lambda item: (item.llm_calls > 0, -item.rank_score, item.cost, item.id),
            )
        )
