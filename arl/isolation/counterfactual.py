from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MatrixCell:
    model: str
    harness: str
    status: str


@dataclass(frozen=True)
class MatrixInsight:
    kind: str
    model: str | None
    harness: str | None
    detail: str


class CounterfactualMatrix:
    def __init__(self, cells: tuple[MatrixCell, ...]) -> None:
        self.cells = cells

    def interaction_insights(self) -> tuple[MatrixInsight, ...]:
        failures = [cell for cell in self.cells if cell.status == "fail"]
        insights: list[MatrixInsight] = []
        for cell in failures:
            same_model_elsewhere = [
                item
                for item in self.cells
                if item.model == cell.model and item.harness != cell.harness
            ]
            same_harness_elsewhere = [
                item
                for item in self.cells
                if item.harness == cell.harness and item.model != cell.model
            ]
            if (
                same_model_elsewhere
                and same_harness_elsewhere
                and all(
                    item.status == "pass" for item in same_model_elsewhere + same_harness_elsewhere
                )
            ):
                insights.append(
                    MatrixInsight(
                        "MODEL_HARNESS_INTERACTION",
                        cell.model,
                        cell.harness,
                        f"failure isolated to {cell.model} x {cell.harness}",
                    )
                )
        return tuple(insights)
