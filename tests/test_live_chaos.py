import json

from arl.engines.chaos import ChaosKind
from arl.tracing.stdio_proxy import ChaosInjector, TraceSink


def _armed_injector(tmp_path, kind: ChaosKind) -> tuple[ChaosInjector, TraceSink]:
    sink = TraceSink(tmp_path / f"{kind.value}.jsonl", "trace-1")
    injector = ChaosInjector(kind, "inject-1", "get_status", 0, 1024, sink)
    injector.observe_request(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "get_status", "arguments": {}},
        }
    )
    return injector, sink


def test_partial_result_is_injected_and_traced(tmp_path) -> None:
    injector, sink = _armed_injector(tmp_path, ChaosKind.PARTIAL_RESULT)
    raw = injector.transform_response(b'{"jsonrpc":"2.0","id":7,"result":{"ok":true}}\n')

    assert json.loads(raw or b"null")["result"] == {}
    records = [json.loads(line) for line in sink.path.read_text().splitlines()]
    assert [record["phase"] for record in records] == ["armed", "injected"]


def test_huge_result_is_bounded(tmp_path) -> None:
    injector, _ = _armed_injector(tmp_path, ChaosKind.HUGE_RESULT)
    raw = injector.transform_response(b'{"jsonrpc":"2.0","id":7,"result":{}}\n')

    text = json.loads(raw or b"null")["result"]["content"][0]["text"]
    assert len(text) == 1024
