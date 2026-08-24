from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class FailureKind(StrEnum):
    TRANSPORT = "transport"
    REASONING = "reasoning"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"


@dataclass(frozen=True)
class ProviderAttempt:
    provider: str
    model: str
    ok: bool
    value: Any = None
    failure_kind: FailureKind | None = None
    error: str | None = None


@dataclass(frozen=True)
class RouteResult:
    value: Any
    provider: str
    model: str
    attempts: tuple[ProviderAttempt, ...]


class CircuitBreaker:
    def __init__(self, threshold: int = 3, cooldown_seconds: float = 60) -> None:
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self.failures: dict[str, int] = {}
        self.opened_at: dict[str, float] = {}

    def available(self, provider: str, *, now: float | None = None) -> bool:
        if provider not in self.opened_at:
            return True
        current = time.monotonic() if now is None else now
        return current - self.opened_at[provider] >= self.cooldown_seconds

    def record_success(self, provider: str) -> None:
        self.failures.pop(provider, None)
        self.opened_at.pop(provider, None)

    def record_failure(self, provider: str, kind: FailureKind, *, now: float | None = None) -> None:
        if kind is FailureKind.REASONING:
            return
        count = self.failures.get(provider, 0) + 1
        self.failures[provider] = count
        if count >= self.threshold:
            self.opened_at[provider] = time.monotonic() if now is None else now


class ModelRouter:
    """Transport failures fall back; reasoning failures escalate without provider substitution."""

    def __init__(self, breaker: CircuitBreaker | None = None) -> None:
        self.breaker = breaker or CircuitBreaker()

    def route(
        self,
        candidates: tuple[tuple[str, str], ...],
        invoke: Callable[[str, str], ProviderAttempt],
    ) -> RouteResult:
        attempts: list[ProviderAttempt] = []
        for provider, model in candidates:
            if not self.breaker.available(provider):
                attempts.append(
                    ProviderAttempt(
                        provider,
                        model,
                        False,
                        failure_kind=FailureKind.TRANSPORT,
                        error="circuit_open",
                    )
                )
                continue
            attempt = invoke(provider, model)
            attempts.append(attempt)
            if attempt.ok:
                self.breaker.record_success(provider)
                return RouteResult(attempt.value, provider, model, tuple(attempts))
            assert attempt.failure_kind is not None
            self.breaker.record_failure(provider, attempt.failure_kind)
            if attempt.failure_kind is FailureKind.REASONING:
                raise RuntimeError(f"reasoning escalation required for {provider}/{model}")
            if attempt.failure_kind in {FailureKind.AUTH, FailureKind.RATE_LIMIT}:
                continue
        raise RuntimeError(f"all providers unavailable: {attempts}")
