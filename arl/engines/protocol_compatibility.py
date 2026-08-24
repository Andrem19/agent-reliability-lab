from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProtocolCompatibility:
    version: str
    lifecycle: str
    trace_context: str
    expected_deprecations: tuple[str, ...]


KNOWN_COMPATIBILITY: dict[str, ProtocolCompatibility] = {
    "2025-11-25": ProtocolCompatibility(
        "2025-11-25",
        "stateful_initialize",
        "proxy_or_native_otel",
        (),
    ),
    "2026-07-28": ProtocolCompatibility(
        "2026-07-28",
        "stateless_per_request_meta",
        "w3c_trace_context_in_meta",
        ("roots", "sampling", "logging"),
    ),
}


def compatibility_for(version: str) -> ProtocolCompatibility:
    try:
        return KNOWN_COMPATIBILITY[version]
    except KeyError as exc:
        raise ValueError(f"unsupported or undiscovered MCP version: {version}") from exc
