import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from arl.config import LabConfig, PathConfig
from arl.engines import direct
from arl.engines.direct import run_direct_scenario
from arl.storage.database import Database
from arl.targets.registry import TargetRegistry


@pytest.mark.asyncio
async def test_demo_l2_trace_to_oracle_e2e(tmp_path) -> None:
    config = LabConfig(
        paths=PathConfig(
            state_dir=tmp_path / "state",
            targets_dir=(tmp_path.cwd() / "targets").resolve(),
            reports_dir=tmp_path / "reports",
        )
    )
    target = TargetRegistry(config.paths.targets_dir).get("demo")
    result = await run_direct_scenario(config, target)

    assert result.status == "pass", result.reason
    assert result.observed == {"value": "reliability"}
    records = [json.loads(line) for line in result.trace_path.read_text().splitlines()]
    assert any(record.get("direction") == "client_to_server" for record in records)
    assert any(record.get("name") == "mcp.tools/call" for record in records)
    assert any(record.get("name") == "scenario.demo-echo" for record in records)

    database = Database(config.paths.state_dir / "arl.db")
    with database.connect() as connection:
        layer = connection.execute(
            "SELECT status, trace_path FROM layer_results WHERE run_id = ?", (result.run_id,)
        ).fetchone()
        tool_call = connection.execute(
            "SELECT tool_name FROM tool_calls WHERE run_id = ?", (result.run_id,)
        ).fetchone()
    assert tuple(layer) == ("pass", str(result.trace_path))
    assert tool_call[0] == "echo"


@pytest.mark.asyncio
async def test_direct_engine_selects_streamable_http_transport(monkeypatch) -> None:
    target = TargetRegistry((PathConfig().targets_dir).resolve()).get("demo")
    http_server = target.topology[0].server.model_copy(
        update={"transport": "http", "command": None, "url": "http://mcp.test/mcp"}
    )
    target = target.model_copy(
        update={"topology": [target.topology[0].model_copy(update={"server": http_server})]}
    )
    observed: dict[str, object] = {}

    @asynccontextmanager
    async def fake_transport(url: str):
        observed["url"] = url
        yield object(), object()

    class FakeSession:
        def __init__(self, read, write) -> None:
            observed["streams"] = (read, write)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

    async def fake_call(session, scenario):
        observed["scenario"] = scenario
        return {"ok": True}

    monkeypatch.setattr(direct, "streamable_http_client", fake_transport)
    monkeypatch.setattr(direct, "ClientSession", FakeSession)
    monkeypatch.setattr(direct, "_initialize_and_call", fake_call)

    result = await direct._call_configured_server(
        target, {"tool": "echo", "arguments": {}}, Path("unused"), "trace"
    )
    assert result == {"ok": True}
    assert observed["url"] == "http://mcp.test/mcp"
