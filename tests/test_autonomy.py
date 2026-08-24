import pytest

from arl.diagnosis.patterns import FailurePattern, PatternLibrary, TwoPassDiagnosis
from arl.orchestrator import SoakRunner
from arl.safety.risk_class import RiskClass
from arl.scenarios.capability_graph import build_capability_graph
from arl.scenarios.coverage import CoverageCell, select_next
from arl.scenarios.synthesis import SynthesizedScenario, lint_scenario
from arl.storage.database import Database


def test_demo_pattern_is_retrieved_only_after_independent_diagnosis(tmp_path) -> None:
    library = PatternLibrary(Database(tmp_path / "arl.db"))
    signature = {
        "layer": 4,
        "attribution": "TOOL_METADATA",
        "features": ["similar_tool_names"],
        "signal": "wrong_tool_selected_by_one_model",
    }
    library.record(
        FailurePattern(
            "PT-DEMO-001",
            signature,
            "ambiguous tool description",
            "metadata_only",
            ("qwen3.8-27b",),
            ("zcode",),
        )
    )
    with pytest.raises(RuntimeError, match="independent diagnosis"):
        library.retrieve(signature, independent_diagnosis=None)

    result = TwoPassDiagnosis(library).diagnose(signature, lambda _: "ambiguous tool description")
    assert result.patterns[0].pattern_id == "PT-DEMO-001"
    assert result.reconciled_diagnosis == "ambiguous tool description"
    assert library.list()[0].hits == 1


def test_capability_graph_synthesis_lint_and_coverage_scheduler() -> None:
    schemas = {
        "search": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        "details": {"type": "object", "properties": {"query": {"type": "string"}}},
    }
    graph = build_capability_graph(
        [{"name": name, "inputSchema": schema} for name, schema in schemas.items()]
    )
    assert graph.edges[0].reason == "shared:query"
    candidate = SynthesizedScenario(
        "generated-1",
        "happy_path",
        "search",
        {"query": "reliability"},
        "DETERMINISTIC",
        frozenset({RiskClass.READ}),
    )
    accepted = lint_scenario(candidate, tool_schemas=schemas)
    assert accepted.autonomous_repair
    selected = select_next(
        [
            CoverageCell("covered", True, 1.0),
            CoverageCell("uncovered", False, 0.0),
        ]
    )
    assert selected.scenario_id == "uncovered"


def test_soak_runner_checkpoints_and_continues_after_cycle_failure(tmp_path) -> None:
    runner = SoakRunner(tmp_path / "soak.json")

    def cycle(number: int) -> bool:
        if number == 2:
            raise RuntimeError("injected crash")
        return True

    result = runner.run(cycle, max_cycles=3)
    assert result.status == "completed"
    assert result.completed_cycles == 3
    assert result.failures == 1
    assert (tmp_path / "soak.json").exists()


def test_soak_runner_resumes_after_orchestrator_crash(tmp_path) -> None:
    checkpoint = tmp_path / "soak.json"
    runner = SoakRunner(checkpoint)

    def crashing_cycle(number: int) -> bool:
        if number == 2:
            raise KeyboardInterrupt("orchestrator killed")
        return True

    with pytest.raises(KeyboardInterrupt):
        runner.run(
            crashing_cycle,
            max_cycles=3,
            metadata={"target": "demo", "scenario": "echo", "layers": "L2"},
        )
    saved = runner.load()
    assert saved.completed_cycles == 1
    resumed = runner.run(lambda _: True, resume_from=saved)
    assert resumed.completed_cycles == 3
    assert resumed.metadata == saved.metadata


def test_soak_runner_rejects_concurrent_checkpoint_owner(tmp_path) -> None:
    checkpoint = tmp_path / "soak.json"
    owner = SoakRunner(checkpoint)
    contender = SoakRunner(checkpoint)

    with owner._lease(), pytest.raises(RuntimeError, match="already leased"):
        contender.run(lambda _: True, max_cycles=1)
