from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[REDACTED]"


class SecretRedactor:
    """Redact secret-bearing keys and common credential shapes before persistence."""

    _secret_key = re.compile(
        r"(?i)(api[-_]?key|access[-_]?token|refresh[-_]?token|authorization|cookie|"
        r"password|passwd|client[-_]?secret|private[-_]?key|ssh[-_]?key|session[-_]?token)"
    )
    _patterns = (
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
        re.compile(r"(?i)\bBasic\s+[A-Za-z0-9+/=]{8,}"),
        re.compile(r"\b(?:sk|pk)-[A-Za-z0-9_-]{16,}\b"),
        re.compile(r"(?i)((?:api[-_]?key|token|secret|password)=)[^&\s]+"),
    )

    def redact_text(self, value: str) -> str:
        redacted = value
        for pattern in self._patterns:
            if pattern.groups:
                redacted = pattern.sub(lambda match: match.group(1) + REDACTED, redacted)
            else:
                redacted = pattern.sub(REDACTED, redacted)
        return redacted

    def redact(self, value: Any, *, key: str | None = None) -> Any:
        if key is not None and self._secret_key.search(key):
            return REDACTED
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, Mapping):
            return {str(k): self.redact(v, key=str(k)) for k, v in value.items()}
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [self.redact(item) for item in value]
        return value
