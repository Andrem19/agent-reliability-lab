from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS targets (
    name TEXT PRIMARY KEY,
    access_mode TEXT NOT NULL,
    contract_json TEXT NOT NULL,
    registered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    target_name TEXT NOT NULL REFERENCES targets(name),
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cycles (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    ordinal INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, ordinal)
);

CREATE TABLE IF NOT EXISTS scenarios (
    id TEXT PRIMARY KEY,
    target_name TEXT NOT NULL REFERENCES targets(name),
    oracle_id TEXT NOT NULL,
    oracle_version TEXT NOT NULL,
    oracle_type TEXT NOT NULL,
    oracle_confidence REAL NOT NULL,
    source TEXT NOT NULL,
    needs_review INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    run_id TEXT,
    cycle_id TEXT,
    scenario_id TEXT,
    ts TEXT NOT NULL,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS layer_results (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    cycle_id TEXT NOT NULL REFERENCES cycles(id),
    scenario_id TEXT NOT NULL REFERENCES scenarios(id),
    layer TEXT NOT NULL,
    status TEXT NOT NULL,
    result_json TEXT NOT NULL,
    trace_path TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS spans (
    span_id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    parent_span_id TEXT,
    run_id TEXT,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT,
    status TEXT NOT NULL,
    attributes_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    span_id TEXT NOT NULL,
    run_id TEXT,
    tool_name TEXT NOT NULL,
    args_json TEXT NOT NULL,
    result_json TEXT,
    duration_ms REAL,
    error TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS failures (
    id TEXT PRIMARY KEY,
    run_id TEXT,
    scenario_id TEXT,
    signature_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hypotheses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    failure_id TEXT NOT NULL REFERENCES failures(id),
    hypothesis TEXT NOT NULL,
    score REAL NOT NULL,
    evidence_refs_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY,
    failure_id TEXT NOT NULL REFERENCES failures(id),
    template_id TEXT NOT NULL,
    status TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS isolation_probes (
    id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES experiments(id),
    probe_type TEXT NOT NULL,
    outcome TEXT NOT NULL,
    evidence_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS repair_attempts (
    id TEXT PRIMARY KEY,
    failure_id TEXT,
    repair_domain TEXT NOT NULL,
    worktree_path TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS patches (
    id TEXT PRIMARY KEY,
    repair_attempt_id TEXT NOT NULL REFERENCES repair_attempts(id),
    commit_sha TEXT,
    diff_hash TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS replays (
    id TEXT PRIMARY KEY,
    repair_attempt_id TEXT NOT NULL REFERENCES repair_attempts(id),
    mode TEXT NOT NULL,
    phase TEXT NOT NULL,
    attempts INTEGER NOT NULL,
    successes INTEGER NOT NULL,
    success_rate REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS regressions (
    id TEXT PRIMARY KEY,
    repair_attempt_id TEXT NOT NULL REFERENCES repair_attempts(id),
    suite TEXT NOT NULL,
    status TEXT NOT NULL,
    output_summary TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provider_calls (
    id TEXT PRIMARY KEY,
    run_id TEXT,
    role TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    failure_kind TEXT,
    duration_ms REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS production_checks (
    id TEXT PRIMARY KEY,
    scenario TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    session_id TEXT,
    trace_id TEXT NOT NULL,
    trace_path TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS coverage_matrix (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_name TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    model TEXT NOT NULL,
    harness TEXT NOT NULL,
    layer TEXT NOT NULL,
    status TEXT NOT NULL,
    UNIQUE(target_name, scenario_id, model, harness, layer)
);

CREATE TABLE IF NOT EXISTS failure_patterns (
    pattern_id TEXT PRIMARY KEY,
    signature_json TEXT NOT NULL,
    root_cause TEXT NOT NULL,
    successful_patch_type TEXT NOT NULL,
    affected_models_json TEXT NOT NULL,
    affected_harnesses_json TEXT NOT NULL,
    occurrences INTEGER NOT NULL,
    hits INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS safety_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    ts TEXT NOT NULL,
    action TEXT NOT NULL,
    decision TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

-- Ground truth is deliberately isolated from evidence-facing query APIs.
CREATE TABLE IF NOT EXISTS mutation_ground_truth (
    mutation_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    attribution TEXT NOT NULL,
    repair_domain TEXT NOT NULL,
    fixture_json TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def healthcheck(self) -> str:
        self.initialize()
        with self.connect() as connection:
            return str(connection.execute("SELECT sqlite_version()").fetchone()[0])
