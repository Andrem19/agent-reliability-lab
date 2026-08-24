import json
from pathlib import Path

from arl.config import load_config
from arl.harnesses.zcode import (
    ZCodeHarness,
    _contains_subset,
    _response_payload,
    _trace_tool_events,
)
from arl.targets.registry import TargetRegistry


def test_zcode_workspace_uses_absolute_server_paths(tmp_path, monkeypatch) -> None:
    config = load_config()
    target = TargetRegistry(config.paths.targets_dir).get("job-search")
    fake_uv = Path("C:/tools/uv.exe")
    monkeypatch.setattr("arl.harnesses.zcode.shutil.which", lambda _: str(fake_uv))

    workspace_config = ZCodeHarness()._workspace_config(
        target, tmp_path, tmp_path / "trace.jsonl", "trace-id"
    )
    args = workspace_config["mcp"]["servers"]["work-researcher"]["args"]
    separator = args.index("--")
    server_args = args[separator + 1 :]

    assert server_args[0] == str(fake_uv)
    directory = Path(server_args[server_args.index("--directory") + 1])
    assert directory.is_absolute()
    assert directory.name == "WORK_RESEARCHER_MCP"


def test_trace_events_pair_arguments_and_responses(tmp_path) -> None:
    trace = tmp_path / "trace.jsonl"
    records = [
        {
            "record_type": "mcp_message",
            "direction": "client_to_server",
            "message": {
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "get_job",
                    "arguments": {"job_ids": ["missing"], "include_description": False},
                },
            },
        },
        {
            "record_type": "mcp_message",
            "direction": "server_to_client",
            "message": {
                "id": 7,
                "result": {"content": [{"type": "text", "text": '{"error":"unknown"}'}]},
            },
        },
    ]
    trace.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

    events = _trace_tool_events(trace)

    assert [event["name"] for event in events] == ["get_job"]
    assert _contains_subset(
        events[0]["arguments"],
        {"job_ids": ["missing"], "include_description": False},
    )
    assert "unknown" in json.dumps(events[0]["response"])
    assert _contains_subset(_response_payload(events[0]["response"]), {"error": "unknown"})
