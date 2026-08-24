from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from arl.storage.database import Database


@dataclass(frozen=True)
class FailurePattern:
    pattern_id: str
    failure_signature: dict[str, Any]
    root_cause: str
    successful_patch_type: str
    affected_models: tuple[str, ...] = ()
    affected_harnesses: tuple[str, ...] = ()
    occurrences: int = 1
    hits: int = 0

    @property
    def hit_rate(self) -> float:
        return self.hits / self.occurrences if self.occurrences else 0.0


class PatternLibrary:
    def __init__(self, database: Database) -> None:
        self.database = database
        database.initialize()

    def record(self, pattern: FailurePattern) -> None:
        now = datetime.now(UTC).isoformat()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO failure_patterns VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pattern_id) DO UPDATE SET
                    occurrences = failure_patterns.occurrences + 1,
                    hits = failure_patterns.hits + excluded.hits,
                    updated_at = excluded.updated_at
                """,
                (
                    pattern.pattern_id,
                    json.dumps(pattern.failure_signature, sort_keys=True),
                    pattern.root_cause,
                    pattern.successful_patch_type,
                    json.dumps(pattern.affected_models),
                    json.dumps(pattern.affected_harnesses),
                    pattern.occurrences,
                    pattern.hits,
                    now,
                    now,
                ),
            )

    def retrieve(
        self,
        signature: dict[str, Any],
        *,
        independent_diagnosis: str | None,
        limit: int = 5,
    ) -> tuple[FailurePattern, ...]:
        if not independent_diagnosis:
            raise RuntimeError("pattern retrieval is pass 2; independent diagnosis must run first")
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM failure_patterns").fetchall()
        query_features = set(signature.get("features", []))

        def score(row) -> tuple[int, int]:
            stored = json.loads(row["signature_json"])
            exact = sum(
                stored.get(key) == signature.get(key) for key in ("layer", "attribution", "signal")
            )
            overlap = len(query_features & set(stored.get("features", [])))
            return exact, overlap

        matching = [row for row in rows if score(row) != (0, 0)]
        matching.sort(key=score, reverse=True)
        return tuple(self._from_row(row) for row in matching[:limit])

    def mark_hit(self, pattern_id: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE failure_patterns SET hits = hits + 1, updated_at = ? WHERE pattern_id = ?",
                (datetime.now(UTC).isoformat(), pattern_id),
            )

    def list(self) -> tuple[FailurePattern, ...]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM failure_patterns ORDER BY occurrences DESC, pattern_id"
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    @staticmethod
    def _from_row(row) -> FailurePattern:
        return FailurePattern(
            row["pattern_id"],
            json.loads(row["signature_json"]),
            row["root_cause"],
            row["successful_patch_type"],
            tuple(json.loads(row["affected_models_json"])),
            tuple(json.loads(row["affected_harnesses_json"])),
            row["occurrences"],
            row["hits"],
        )


@dataclass(frozen=True)
class TwoPassResult:
    independent_diagnosis: str
    patterns: tuple[FailurePattern, ...]
    reconciled_diagnosis: str


class TwoPassDiagnosis:
    def __init__(self, library: PatternLibrary) -> None:
        self.library = library

    def diagnose(
        self,
        signature: dict[str, Any],
        independent: Callable[[dict[str, Any]], str],
    ) -> TwoPassResult:
        first = independent(signature)
        patterns = self.library.retrieve(signature, independent_diagnosis=first)
        matching = next((item for item in patterns if item.root_cause == first), None)
        if matching:
            self.library.mark_hit(matching.pattern_id)
        reconciled = matching.root_cause if matching else first
        return TwoPassResult(first, patterns, reconciled)


def new_pattern_id() -> str:
    return f"PT-{uuid.uuid4().hex[:8].upper()}"
