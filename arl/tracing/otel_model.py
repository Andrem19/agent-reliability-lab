from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class SpanKind(StrEnum):
    INTERNAL = "internal"
    CLIENT = "client"
    SERVER = "server"


class SpanStatus(StrEnum):
    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def new_trace_id() -> str:
    return secrets.token_hex(16)


def new_span_id() -> str:
    return secrets.token_hex(8)


@dataclass
class Span:
    trace_id: str
    name: str
    kind: SpanKind
    parent_span_id: str | None = None
    span_id: str = field(default_factory=new_span_id)
    start_time: str = field(default_factory=utc_now)
    end_time: str | None = None
    status: SpanStatus = SpanStatus.UNSET
    attributes: dict[str, Any] = field(default_factory=dict)

    def end(self, status: SpanStatus, **attributes: Any) -> None:
        if self.end_time is not None:
            raise RuntimeError(f"span already ended: {self.span_id}")
        self.end_time = utc_now()
        self.status = status
        self.attributes.update(attributes)

    def as_record(self) -> dict[str, Any]:
        return {"record_type": "span", **asdict(self)}
