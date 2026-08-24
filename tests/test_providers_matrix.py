import pytest

from arl.engines.protocol_compatibility import compatibility_for
from arl.isolation.counterfactual import CounterfactualMatrix, MatrixCell
from arl.providers.router import (
    CircuitBreaker,
    FailureKind,
    ModelRouter,
    ProviderAttempt,
)


def test_transport_outage_falls_back_and_is_logged_in_attempts() -> None:
    def invoke(provider: str, model: str) -> ProviderAttempt:
        if provider == "primary":
            return ProviderAttempt(
                provider,
                model,
                False,
                failure_kind=FailureKind.TRANSPORT,
                error="timeout",
            )
        return ProviderAttempt(provider, model, True, value="ok")

    result = ModelRouter().route(
        (("primary", "deepseek-v4-flash"), ("fallback", "deepseek-v4-flash")),
        invoke,
    )
    assert result.value == "ok"
    assert result.provider == "fallback"
    assert [item.failure_kind for item in result.attempts] == [FailureKind.TRANSPORT, None]


def test_reasoning_failure_escalates_without_transport_fallback() -> None:
    called: list[str] = []

    def invoke(provider: str, model: str) -> ProviderAttempt:
        called.append(provider)
        return ProviderAttempt(
            provider,
            model,
            False,
            failure_kind=FailureKind.REASONING,
            error="invalid structured diagnosis",
        )

    with pytest.raises(RuntimeError, match="reasoning escalation"):
        ModelRouter().route((("primary", "small"), ("fallback", "same")), invoke)
    assert called == ["primary"]


def test_circuit_breaker_opens_after_three_transport_failures_and_recovers() -> None:
    breaker = CircuitBreaker(threshold=3, cooldown_seconds=10)
    for _ in range(3):
        breaker.record_failure("primary", FailureKind.TRANSPORT, now=100)
    assert not breaker.available("primary", now=109)
    assert breaker.available("primary", now=111)
    breaker.record_success("primary")
    assert breaker.available("primary", now=101)


def test_qwen_zcode_interaction_is_detected() -> None:
    matrix = CounterfactualMatrix(
        (
            MatrixCell("qwen3.8-27b", "zcode", "fail"),
            MatrixCell("qwen3.8-27b", "dsh", "pass"),
            MatrixCell("deepseek-v4-pro", "zcode", "pass"),
            MatrixCell("deepseek-v4-pro", "dsh", "pass"),
        )
    )
    insights = matrix.interaction_insights()
    assert len(insights) == 1
    assert insights[0].kind == "MODEL_HARNESS_INTERACTION"
    assert insights[0].model == "qwen3.8-27b"
    assert insights[0].harness == "zcode"


def test_protocol_compatibility_distinguishes_lifecycle_and_deprecations() -> None:
    legacy = compatibility_for("2025-11-25")
    modern = compatibility_for("2026-07-28")
    assert legacy.lifecycle == "stateful_initialize"
    assert modern.lifecycle == "stateless_per_request_meta"
    assert "roots" in modern.expected_deprecations
    with pytest.raises(ValueError, match="undiscovered"):
        compatibility_for("future")
