from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from arl.providers.router import FailureKind, ProviderAttempt


@dataclass(frozen=True)
class OpenAICompatibleProvider:
    name: str
    base_url: str
    api_key: str | None

    def list_models(self, timeout: float = 5) -> ProviderAttempt:
        request = urllib.request.Request(f"{self.base_url.rstrip('/')}/models")
        if self.api_key:
            request.add_header("Authorization", f"Bearer {self.api_key}")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload: dict[str, Any] = json.load(response)
            return ProviderAttempt(self.name, "models", True, payload)
        except urllib.error.HTTPError as exc:
            kind = (
                FailureKind.AUTH
                if exc.code in {401, 403}
                else FailureKind.RATE_LIMIT
                if exc.code == 429
                else FailureKind.TRANSPORT
            )
            return ProviderAttempt(
                self.name, "models", False, failure_kind=kind, error=f"HTTP {exc.code}"
            )
        except (OSError, ValueError) as exc:
            return ProviderAttempt(
                self.name,
                "models",
                False,
                failure_kind=FailureKind.TRANSPORT,
                error=type(exc).__name__,
            )
