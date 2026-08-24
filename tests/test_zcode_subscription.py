import json

from arl.harnesses.zcode import _trace_tool_calls
from arl.providers.zcode_subscription import ZCodeSubscriptionProvider


def test_native_subscription_health_uses_desktop_provider_without_exposing_key(tmp_path) -> None:
    config = {
        "provider": {
            "builtin:zai-coding-plan": {
                "kind": "anthropic",
                "options": {"baseURL": "https://example.test/anthropic", "apiKey": "secret"},
                "models": {"GLM-5.3": {}},
            }
        }
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    health = ZCodeSubscriptionProvider(desktop_config=path).health()
    assert health.available
    assert "secret" not in health.detail


def test_trace_assertions_detect_firewall_synthetic_error(tmp_path) -> None:
    trace = tmp_path / "trace.jsonl"
    records = [
        {
            "record_type": "mcp_message",
            "direction": "client_to_server",
            "message": {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {"name": "record_application", "arguments": {}},
            },
        },
        {
            "record_type": "mcp_message",
            "direction": "server_to_client",
            "message": {
                "jsonrpc": "2.0",
                "id": 7,
                "result": {
                    "isError": True,
                    "content": [{"type": "text", "text": "blocked by SAFE_LIVE"}],
                },
            },
        },
    ]
    trace.write_text("\n".join(json.dumps(item) for item in records), encoding="utf-8")
    calls, blocked = _trace_tool_calls(trace)
    assert calls == ["record_application"]
    assert blocked == {"record_application"}
