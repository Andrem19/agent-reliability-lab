from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from arl.safety.redaction import SecretRedactor
from arl.storage.database import Database


@dataclass(frozen=True)
class LabEvent:
    event_type: str
    status: str
    payload: dict[str, Any] = field(default_factory=dict)
    run_id: str | None = None
    cycle_id: str | None = None
    scenario_id: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ts: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class EventWriter:
    def __init__(self, database: Database, jsonl_path: Path) -> None:
        self.database = database
        self.jsonl_path = jsonl_path
        self.redactor = SecretRedactor()

    def write(self, event: LabEvent) -> dict[str, Any]:
        self.database.initialize()
        record = self.redactor.redact(asdict(event))
        payload_json = json.dumps(record["payload"], sort_keys=True, ensure_ascii=False)
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO events (
                    event_id, run_id, cycle_id, scenario_id, ts, event_type, status, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["event_id"],
                    record["run_id"],
                    record["cycle_id"],
                    record["scenario_id"],
                    record["ts"],
                    record["event_type"],
                    record["status"],
                    payload_json,
                ),
            )
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with self.jsonl_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
        return record
