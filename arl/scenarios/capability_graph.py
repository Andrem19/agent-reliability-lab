from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CapabilityNode:
    name: str
    schema: dict[str, Any]


@dataclass(frozen=True)
class CapabilityEdge:
    source: str
    target: str
    reason: str


@dataclass(frozen=True)
class CapabilityGraph:
    nodes: tuple[CapabilityNode, ...]
    edges: tuple[CapabilityEdge, ...]


def build_capability_graph(tools: list[dict[str, Any]]) -> CapabilityGraph:
    nodes = tuple(CapabilityNode(tool["name"], tool.get("inputSchema", {})) for tool in tools)
    edges: list[CapabilityEdge] = []
    for index, left in enumerate(nodes):
        for right in nodes[index + 1 :]:
            left_fields = set(left.schema.get("properties", {}))
            right_fields = set(right.schema.get("properties", {}))
            shared = left_fields & right_fields
            if shared:
                edges.append(
                    CapabilityEdge(left.name, right.name, f"shared:{','.join(sorted(shared))}")
                )
    return CapabilityGraph(nodes, tuple(edges))
