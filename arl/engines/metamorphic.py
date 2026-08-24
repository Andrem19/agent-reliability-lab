from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MetamorphicResult:
    invariant_holds: bool
    normalized_outputs: tuple[Any, ...]


def compare_paraphrases(outputs: list[Any]) -> MetamorphicResult:
    normalized = tuple(_normalize(item) for item in outputs)
    return MetamorphicResult(len(set(map(repr, normalized))) <= 1, normalized)


def differential(left: Any, right: Any) -> bool:
    return _normalize(left) == _normalize(right)


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple(sorted((key, _normalize(item)) for key, item in value.items()))
    if isinstance(value, list):
        return tuple(_normalize(item) for item in value)
    if isinstance(value, str):
        return value.strip()
    return value
