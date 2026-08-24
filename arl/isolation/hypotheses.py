from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Hypothesis(StrEnum):
    MCP_PROTOCOL = "MCP_PROTOCOL"
    MCP_LOGIC = "MCP_LOGIC"
    MCP_SCHEMA = "MCP_SCHEMA"
    TOOL_METADATA = "TOOL_METADATA"
    HARNESS = "HARNESS"
    MODEL_CAPABILITY = "MODEL_CAPABILITY"
    MODEL_REASONING = "MODEL_REASONING"
    SCENARIO_ERROR = "SCENARIO_ERROR"
    ORACLE_ERROR = "ORACLE_ERROR"
    ENV_EXTERNAL = "ENV_EXTERNAL"
    ENV_AUTH = "ENV_AUTH"
    ENV_RATE_LIMIT = "ENV_RATE_LIMIT"
    NETWORK = "NETWORK"
    PROVIDER = "PROVIDER"
    INFRA = "INFRA"
    FLAKY = "FLAKY"
    EXPECTED_LIMITATION = "EXPECTED_LIMITATION"
    UNKNOWN = "UNKNOWN"


REPAIR_DOMAINS: dict[Hypothesis, str] = {
    Hypothesis.MCP_PROTOCOL: "MCP_CODE",
    Hypothesis.MCP_LOGIC: "MCP_CODE",
    Hypothesis.MCP_SCHEMA: "MCP_SCHEMA",
    Hypothesis.TOOL_METADATA: "TOOL_METADATA",
    Hypothesis.HARNESS: "HARNESS_CONFIG",
    Hypothesis.MODEL_CAPABILITY: "AGENT_PROMPT",
    Hypothesis.MODEL_REASONING: "AGENT_PROMPT",
    Hypothesis.SCENARIO_ERROR: "SCENARIO",
    Hypothesis.ORACLE_ERROR: "ORACLE",
}


@dataclass(frozen=True)
class ScoredHypothesis:
    hypothesis: Hypothesis
    score: float
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class Attribution:
    ranking: tuple[ScoredHypothesis, ...]
    confirmed: bool
    repair_domain: str

    @property
    def top(self) -> Hypothesis:
        return self.ranking[0].hypothesis


class HypothesisEngine:
    def __init__(self, *, threshold: float = 0.75, margin: float = 0.20) -> None:
        self.threshold = threshold
        self.margin = margin

    def attribute(self, evidence: dict[str, Any]) -> Attribution:
        scores = {item: 0.01 for item in Hypothesis}
        refs: dict[Hypothesis, list[str]] = {item: [] for item in Hypothesis}

        def support(hypothesis: Hypothesis, score: float, evidence_ref: str) -> None:
            scores[hypothesis] = max(scores[hypothesis], score)
            refs[hypothesis].append(evidence_ref)

        signal = evidence.get("failure_signal")
        if signal == "protocol_error":
            support(Hypothesis.MCP_PROTOCOL, 0.98, "T1:initialize_protocol_error")
        elif signal == "schema_accepts_invalid":
            support(Hypothesis.MCP_SCHEMA, 0.96, "T1:invalid_input_silent_success")
        elif signal == "semantic_mismatch":
            support(Hypothesis.MCP_LOGIC, 0.94, "T1:valid_direct_semantic_mismatch")

        if evidence.get("original_direct") == "fail" and evidence.get("valid_direct") == "pass":
            support(Hypothesis.MODEL_REASONING, 0.70, "T1b:valid_arguments_recover")
        if evidence.get("live") == "fail" and evidence.get("mock") == "pass":
            support(Hypothesis.ENV_EXTERNAL, 0.92, "T2:mock_recovers")
        if evidence.get("description_swap") == "pass" and evidence.get("agent_original") == "fail":
            support(Hypothesis.TOOL_METADATA, 0.97, "T5:description_swap_recovers")
        if evidence.get("reference_models") == "pass" and evidence.get("executor_model") == "fail":
            support(Hypothesis.MODEL_REASONING, 0.64, "T3:executor_specific")
        if evidence.get("interaction") == "executor_harness_only":
            support(Hypothesis.HARNESS, 0.62, "T4:model_harness_interaction")
        if (
            evidence.get("primary_oracle") == "fail"
            and evidence.get("independent_oracle") == "pass"
        ):
            support(Hypothesis.ORACLE_ERROR, 0.99, "T8:independent_oracle_contradiction")
        repeats = evidence.get("repeats", [])
        if repeats and len(set(repeats)) > 1:
            support(Hypothesis.FLAKY, 0.95, "T9:mixed_repeat_outcomes")

        if not evidence.get("failure", True):
            ranking = (ScoredHypothesis(Hypothesis.UNKNOWN, 0.0, ("baseline:no_failure",)),)
            return Attribution(ranking, False, "NO_REPAIR")

        ranking = tuple(
            ScoredHypothesis(item, scores[item], tuple(refs[item]))
            for item in sorted(Hypothesis, key=lambda item: (-scores[item], item.value))
        )
        top = ranking[0]
        second = ranking[1]
        confirmed = top.score >= self.threshold and top.score - second.score >= self.margin
        domain = REPAIR_DOMAINS.get(top.hypothesis, "NO_REPAIR") if confirmed else "NO_REPAIR"
        return Attribution(ranking, confirmed, domain)
