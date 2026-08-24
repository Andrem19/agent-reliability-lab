import json

from arl.reporting import build_report
from arl.storage.database import Database
from arl.storage.events import EventWriter, LabEvent


def test_event_is_redacted_in_sqlite_and_jsonl(tmp_path) -> None:
    database = Database(tmp_path / "state" / "arl.db")
    jsonl = tmp_path / "events.jsonl"
    writer = EventWriter(database, jsonl)
    writer.write(LabEvent("probe", "pass", {"api_key": "super-secret", "value": 42}))

    with database.connect() as connection:
        row = connection.execute("SELECT payload_json FROM events").fetchone()
    assert json.loads(row[0]) == {"api_key": "[REDACTED]", "value": 42}
    assert "super-secret" not in jsonl.read_text(encoding="utf-8")


def test_database_initialization_is_idempotent(tmp_path) -> None:
    database = Database(tmp_path / "arl.db")
    database.initialize()
    database.initialize()
    with database.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {"targets", "runs", "events", "mutation_ground_truth"} <= tables


def test_report_includes_production_and_repair_evidence(tmp_path) -> None:
    report = build_report(Database(tmp_path / "arl.db"))

    assert report["production_checks"] == []
    assert report["repair_attempts"] == []
