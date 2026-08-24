from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoverageCell:
    scenario_id: str
    covered: bool
    success_rate: float
    recently_changed: bool = False
    previously_failed: bool = False
    regression_prone: bool = False

    @property
    def priority(self) -> float:
        return (
            (4.0 if not self.covered else 0.0)
            + (1.0 - self.success_rate) * 3.0
            + (2.0 if self.recently_changed else 0.0)
            + (2.0 if self.previously_failed else 0.0)
            + (1.0 if self.regression_prone else 0.0)
        )


def select_next(cells: list[CoverageCell]) -> CoverageCell:
    if not cells:
        raise ValueError("coverage matrix is empty")
    return max(cells, key=lambda item: (item.priority, item.scenario_id))
