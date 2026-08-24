from pathlib import Path

from arl.benchmark.mutations import run_mutation_suite
from arl.isolation.hypotheses import Hypothesis, HypothesisEngine
from arl.isolation.planner import ExperimentPlanner


def test_planner_ranks_deterministic_probes_before_llm_probes() -> None:
    plan = ExperimentPlanner().plan()
    first_llm = next(index for index, item in enumerate(plan) if item.llm_calls)
    assert {item.id for item in plan} == {"T1", "T1b", "T2", "T3", "T4", "T8", "T9"}
    assert all(item.llm_calls == 0 for item in plan[:first_llm])


def test_mutation_suite_meets_m2_gate() -> None:
    report = run_mutation_suite(Path("targets/demo/mutations"))
    assert report.top1_accuracy >= 0.80
    assert report.top3_accuracy == 1.0
    assert report.false_repair_rate == 0.0
    descriptions = next(item for item in report.cases if item.mutation_id == "MUT-004")
    assert descriptions.predicted == "TOOL_METADATA"
    assert descriptions.repair_domain == "TOOL_METADATA"


def test_oracle_and_environment_attribution_never_routes_to_mcp_code() -> None:
    engine = HypothesisEngine()
    oracle = engine.attribute(
        {"failure": True, "primary_oracle": "fail", "independent_oracle": "pass"}
    )
    environment = engine.attribute({"failure": True, "live": "fail", "mock": "pass"})
    assert oracle.top is Hypothesis.ORACLE_ERROR
    assert oracle.repair_domain != "MCP_CODE"
    assert environment.top is Hypothesis.ENV_EXTERNAL
    assert environment.repair_domain == "NO_REPAIR"
