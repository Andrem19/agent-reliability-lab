from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from arl.targets.contract import SafetyMode


@dataclass(frozen=True)
class WebResponse:
    status: int
    headers: dict[str, str]
    body: str


class WebProxy:
    """Deterministic record/replay boundary; the caller supplies the live transport."""

    def __init__(self, fixtures_dir: Path, mode: SafetyMode) -> None:
        self.fixtures_dir = fixtures_dir
        self.mode = mode

    def _path(self, method: str, url: str) -> Path:
        key = hashlib.sha256(f"{method.upper()} {url}".encode()).hexdigest()
        return self.fixtures_dir / f"{key}.json"

    def request(
        self,
        method: str,
        url: str,
        *,
        live_fetch: Callable[[str, str], WebResponse] | None = None,
        replay: bool = False,
    ) -> WebResponse:
        normalized_method = method.upper()
        if self.mode is not SafetyMode.LIVE and normalized_method not in {"GET", "HEAD"}:
            raise PermissionError(f"{self.mode.value} blocks live {normalized_method}")
        path = self._path(normalized_method, url)
        if replay:
            data = json.loads(path.read_text(encoding="utf-8"))
            return WebResponse(**data)
        if live_fetch is None:
            raise ValueError("live_fetch is required in record mode")
        response = live_fetch(normalized_method, url)
        self.fixtures_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(response), sort_keys=True), encoding="utf-8")
        return response
