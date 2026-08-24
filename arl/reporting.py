from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from arl.storage.database import Database


def build_report(database: Database) -> dict[str, Any]:
    database.initialize()
    with database.connect() as connection:
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "runs",
                "cycles",
                "failures",
                "repair_attempts",
                "failure_patterns",
                "safety_events",
                "production_checks",
            )
        }
        statuses = {
            row["status"]: row["count"]
            for row in connection.execute(
                "SELECT status, COUNT(*) AS count FROM runs GROUP BY status"
            ).fetchall()
        }
        production_checks = [
            dict(row)
            for row in connection.execute(
                """
                SELECT scenario, provider, model, status, session_id, trace_id,
                       trace_path, reason, created_at
                FROM production_checks ORDER BY created_at DESC LIMIT 20
                """
            ).fetchall()
        ]
        repair_attempts = [
            dict(row)
            for row in connection.execute(
                """
                SELECT repair_attempts.id, repair_attempts.repair_domain,
                       repair_attempts.status, repair_attempts.worktree_path,
                       repair_attempts.created_at, patches.commit_sha,
                       patches.status AS patch_status,
                       (SELECT success_rate FROM replays
                        WHERE replays.repair_attempt_id = repair_attempts.id
                          AND replays.phase = 'live'
                        ORDER BY replays.rowid DESC LIMIT 1) AS live_success_rate,
                       (SELECT status FROM regressions
                        WHERE regressions.repair_attempt_id = repair_attempts.id
                        ORDER BY regressions.rowid DESC LIMIT 1) AS regression_status
                FROM repair_attempts
                LEFT JOIN patches ON patches.repair_attempt_id = repair_attempts.id
                ORDER BY repair_attempts.created_at DESC LIMIT 20
                """
            ).fetchall()
        ]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "counts": counts,
        "run_statuses": statuses,
        "production_checks": production_checks,
        "repair_attempts": repair_attempts,
    }


def write_report(report: dict[str, Any], directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "report.json"
    markdown_path = directory / "report.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    lines = ["# Agent Reliability Lab report", "", f"Generated: {report['generated_at']}", ""]
    lines.extend(f"- {name}: {value}" for name, value in report["counts"].items())
    lines.extend(("", "## Run statuses", ""))
    lines.extend(f"- {name}: {value}" for name, value in report["run_statuses"].items())
    lines.extend(("", "## Production checks", ""))
    for check in report["production_checks"]:
        lines.append(
            f"- {check['status'].upper()} {check['scenario']}: "
            f"{check['provider']}/{check['model']} — {check['reason']} "
            f"(`{check['trace_path']}`)"
        )
    lines.extend(("", "## Repair attempts", ""))
    for repair in report["repair_attempts"]:
        lines.append(
            f"- {repair['status'].upper()} {repair['repair_domain']}: "
            f"commit `{repair['commit_sha']}`; replay={repair['live_success_rate']}; "
            f"regression={repair['regression_status']}"
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return markdown_path, json_path
