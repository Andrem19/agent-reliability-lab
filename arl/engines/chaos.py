from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from arl.isolation.hypotheses import Hypothesis


class ChaosKind(StrEnum):
    LATENCY = "latency"
    CONNECTION_DROP = "connection_drop"
    MALFORMED_JSON_RPC = "malformed_json_rpc"
    ERROR_CODE = "error_code"
    KILL_SERVER = "kill_server"
    PARTIAL_RESULT = "partial_result"
    HUGE_RESULT = "huge_result"


@dataclass(frozen=True)
class ChaosEvidence:
    kind: ChaosKind
    injection_id: str
    observed_error: str
    proxy_confirmed: bool = True


def inject_message(kind: ChaosKind, message: dict[str, Any]) -> str | None:
    if kind is ChaosKind.CONNECTION_DROP or kind is ChaosKind.KILL_SERVER:
        return None
    if kind is ChaosKind.MALFORMED_JSON_RPC:
        return "{malformed"
    if kind is ChaosKind.ERROR_CODE:
        return json.dumps({"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": -32000}})
    if kind is ChaosKind.PARTIAL_RESULT:
        return json.dumps({"jsonrpc": "2.0", "id": message.get("id"), "result": {}})
    if kind is ChaosKind.HUGE_RESULT:
        return json.dumps({"jsonrpc": "2.0", "id": message.get("id"), "result": "x" * 1_000_000})
    return json.dumps(message)


def attribute_chaos(evidence: ChaosEvidence) -> Hypothesis:
    """A proxy-confirmed injected fault is laboratory infrastructure, not an MCP bug."""
    if evidence.proxy_confirmed:
        return Hypothesis.INFRA
    return Hypothesis.UNKNOWN
