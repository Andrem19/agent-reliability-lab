from __future__ import annotations

from enum import StrEnum
from typing import Any


class RiskClass(StrEnum):
    READ = "READ"
    WRITE = "WRITE"
    NETWORK = "NETWORK"
    EXECUTE = "EXECUTE"
    FINANCIAL = "FINANCIAL"
    EXTERNAL_SUBMIT = "EXTERNAL_SUBMIT"
    DELETE = "DELETE"
    AUTH = "AUTH"
    SENSITIVE_DATA = "SENSITIVE_DATA"


HIGH_RISK = {RiskClass.EXTERNAL_SUBMIT, RiskClass.FINANCIAL, RiskClass.DELETE}


def classify_tool(
    name: str,
    schema: dict[str, Any] | None = None,
    *,
    annotation_hints: set[RiskClass] | None = None,
    source_hints: set[RiskClass] | None = None,
    observed_hints: set[RiskClass] | None = None,
    override: RiskClass | None = None,
) -> set[RiskClass]:
    """Combine five evidence sources; annotations alone can never lower risk."""
    if override is not None:
        return {override}
    risks = set(annotation_hints or ()) | set(source_hints or ()) | set(observed_hints or ())
    lowered = name.casefold()
    if any(
        token in lowered for token in ("submit", "apply", "send", "publish", "record_application")
    ):
        risks.add(RiskClass.EXTERNAL_SUBMIT)
    if any(token in lowered for token in ("delete", "remove", "purge")):
        risks.add(RiskClass.DELETE)
    if any(token in lowered for token in ("pay", "purchase", "trade", "transfer")):
        risks.add(RiskClass.FINANCIAL)
    if any(token in lowered for token in ("login", "auth", "credential")):
        risks.add(RiskClass.AUTH)
    if schema and any(key in str(schema).casefold() for key in ("password", "token", "secret")):
        risks.add(RiskClass.SENSITIVE_DATA)
    return risks or {RiskClass.READ}
