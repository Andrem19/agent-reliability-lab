from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import typer

from arl import __version__
from arl.benchmark.mutations import run_mutation_suite
from arl.config import load_config
from arl.diagnosis.patterns import FailurePattern, PatternLibrary, TwoPassDiagnosis
from arl.doctor import doctor_ok, run_doctor
from arl.engines.direct import run_direct_scenario
from arl.engines.live_fuzz import run_live_schema_fuzz
from arl.engines.security import run_live_firewall_probe
from arl.harnesses.zcode import ZCodeHarness
from arl.isolation.hypotheses import HypothesisEngine
from arl.isolation.planner import ExperimentPlanner
from arl.orchestrator import SoakRunner
from arl.providers.zcode_subscription import ZCodeSubscriptionProvider
from arl.repair.regression import run_regressions
from arl.repair.sandbox import L0Fixer
from arl.reporting import build_report, write_report
from arl.storage.database import Database
from arl.targets.registry import TargetRegistry

app = typer.Typer(help="Agent Reliability Lab", no_args_is_help=True)
targets_app = typer.Typer(help="Inspect target packs", no_args_is_help=True)
experiment_app = typer.Typer(help="Run isolation experiments", no_args_is_help=True)
app.add_typer(targets_app, name="targets")
app.add_typer(experiment_app, name="experiment")


def _registry() -> TargetRegistry:
    return TargetRegistry(load_config().paths.targets_dir)


def _scenario_name_for_id(config, target_name: str, scenario_id: str) -> str:
    directory = config.paths.targets_dir / target_name / "scenarios"
    for path in directory.glob("*.yaml"):
        raw = path.read_text(encoding="utf-8")
        if f"id: {scenario_id}" in raw:
            return path.stem
    raise ValueError(f"scenario file not found for id: {scenario_id}")


def _record_production_check(
    config,
    *,
    scenario: str,
    provider: str,
    model: str,
    passed: bool,
    session_id: str | None,
    trace_id: str,
    trace_path,
    reason: str,
) -> None:
    database = Database(config.paths.state_dir / "arl.db")
    database.initialize()
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO production_checks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                scenario,
                provider,
                model,
                "pass" if passed else "fail",
                session_id,
                trace_id,
                str(trace_path),
                reason,
                datetime.now(UTC).isoformat(),
            ),
        )


def _execute_l2_soak(
    config,
    target_contract,
    *,
    scenario: str,
    cycles: int | None,
    hours: float | None,
    interval_seconds: float,
    resume_state=None,
):
    last_result = None

    def run_cycle(_: int) -> bool:
        nonlocal last_result
        last_result = asyncio.run(
            run_direct_scenario(config, target_contract, scenario_name=scenario)
        )
        typer.echo(
            f"{last_result.status.upper()} run={last_result.run_id} "
            f"scenario={last_result.scenario_id} trace={last_result.trace_path}"
        )
        return last_result.status == "pass"

    runner = SoakRunner(config.paths.state_dir / "soak.json")
    metadata = {
        "target": target_contract.name,
        "scenario": scenario,
        "layers": "L2",
        "interval_seconds": interval_seconds,
    }
    state = runner.run(
        run_cycle,
        hours=hours,
        max_cycles=cycles,
        interval_seconds=interval_seconds,
        metadata=metadata,
        resume_from=resume_state,
    )
    typer.echo(
        f"SOAK {state.status.upper()} cycles={state.completed_cycles} "
        f"failures={state.failures} elapsed={state.elapsed_seconds:.2f}s"
    )
    return state


def _execute_l3_soak(
    config,
    target_contract,
    *,
    cycles: int | None,
    hours: float | None,
    interval_seconds: float,
    resume_state=None,
):
    def run_cycle(_: int) -> bool:
        artifacts = config.paths.state_dir / "artifacts" / str(uuid.uuid4())
        result = asyncio.run(
            run_live_schema_fuzz(target_contract, artifacts / "l3-schema-fuzz-trace.jsonl")
        )
        typer.echo(
            f"{'PASS' if result.passed else 'FAIL'} L3 cases={result.successes}/{result.total} "
            f"trace={result.trace_path}"
        )
        _record_production_check(
            config,
            scenario="l3-schema-fuzz",
            provider="direct-mcp-sdk",
            model="none",
            passed=result.passed,
            session_id=None,
            trace_id=result.trace_id,
            trace_path=result.trace_path,
            reason=result.reason,
        )
        return result.passed

    runner = SoakRunner(config.paths.state_dir / "soak.json")
    metadata = {
        "target": target_contract.name,
        "scenario": "schema-fuzz",
        "layers": "L3",
        "interval_seconds": interval_seconds,
    }
    state = runner.run(
        run_cycle,
        hours=hours,
        max_cycles=cycles,
        interval_seconds=interval_seconds,
        metadata=metadata,
        resume_from=resume_state,
    )
    typer.echo(
        f"L3 SOAK {state.status.upper()} cycles={state.completed_cycles} "
        f"failures={state.failures} elapsed={state.elapsed_seconds:.2f}s"
    )
    return state


def _execute_l4_soak(
    config,
    target_contract,
    *,
    cycles: int | None,
    hours: float | None,
    interval_seconds: float,
    resume_state=None,
):
    def run_cycle(_: int) -> bool:
        artifacts = config.paths.state_dir / "artifacts" / str(uuid.uuid4())
        result = ZCodeHarness().run_read_only_workflow(target_contract, artifacts)
        typer.echo(
            f"{'PASS' if result.passed else 'FAIL'} L4 model={result.model} "
            f"session={result.session_id} trace={result.trace_path} reason={result.reason}"
        )
        _record_production_check(
            config,
            scenario="workflow",
            provider="lmstudio",
            model=result.model,
            passed=result.passed,
            session_id=result.session_id,
            trace_id=result.trace_id,
            trace_path=result.trace_path,
            reason=result.reason,
        )
        return result.passed

    runner = SoakRunner(config.paths.state_dir / "soak.json")
    metadata = {
        "target": target_contract.name,
        "scenario": "workflow",
        "layers": "L4",
        "interval_seconds": interval_seconds,
    }
    state = runner.run(
        run_cycle,
        hours=hours,
        max_cycles=cycles,
        interval_seconds=interval_seconds,
        metadata=metadata,
        resume_from=resume_state,
    )
    typer.echo(
        f"L4 SOAK {state.status.upper()} cycles={state.completed_cycles} "
        f"failures={state.failures} elapsed={state.elapsed_seconds:.2f}s"
    )
    return state


@app.command()
def version() -> None:
    """Print the ARL version."""
    typer.echo(__version__)


@app.command()
def doctor(json_output: bool = typer.Option(False, "--json")) -> None:
    """Inspect required and optional local integrations."""
    results = run_doctor(load_config())
    if json_output:
        typer.echo(json.dumps([item.__dict__ for item in results], indent=2, default=str))
    else:
        for item in results:
            typer.echo(f"[{item.status}] {item.name}: {item.detail}")
    if not doctor_ok(results):
        raise typer.Exit(1)


@targets_app.command("list")
def targets_list() -> None:
    targets, errors = _registry().discover()
    for name, target in targets.items():
        typer.echo(
            f"{name}\t{target.access_mode}\tservers={len(target.topology)}\t"
            f"repair={'yes' if target.can_repair else 'no'}"
        )
    for error in errors:
        typer.echo(f"INVALID\t{error.path}\t{error.message}", err=True)
    if errors:
        raise typer.Exit(1)


@targets_app.command("inspect")
def targets_inspect(name: str, json_output: bool = typer.Option(False, "--json")) -> None:
    target = _registry().get(name)
    data = target.model_dump(mode="json")
    if json_output:
        typer.echo(json.dumps(data, indent=2))
    else:
        typer.echo(f"name: {target.name}")
        typer.echo(f"access_mode: {target.access_mode}")
        typer.echo(f"executor: {target.executor.harness}/{target.executor.model}")
        typer.echo(f"repair: {'enabled' if target.can_repair else 'disabled'}")
        typer.echo(f"layers: {', '.join(target.enabled_layers)}")


@app.command()
def demo(
    inject: str | None = typer.Option(None, "--inject"),
    suite: bool = typer.Option(False, "--suite"),
    baseline: bool = typer.Option(False, "--baseline"),
) -> None:
    """Validate the clean demo pack or select a mutation fixture."""
    target = _registry().get("demo")
    if inject:
        known = {"MUT-001", "MUT-002", "MUT-003", "MUT-004", "MUT-005"}
        if inject not in known:
            raise typer.BadParameter(f"unknown M0 mutation id: {inject}")
        typer.echo(f"demo mutation selected: {inject}; ground truth remains isolated")
    elif suite:
        pack_dir = load_config().paths.targets_dir / "demo" / "mutations"
        report = run_mutation_suite(pack_dir)
        typer.echo(report.to_json())
        if report.top1_accuracy < 0.80 or report.false_repair_rate != 0:
            raise typer.Exit(1)
    else:
        label = "baseline" if baseline else "clean"
        typer.echo(f"demo target registered ({label}); repairs=0")
    if not target.can_repair:
        raise typer.Exit(1)


@app.command()
def run(
    target: str,
    cycles: int | None = typer.Option(None, "--cycles", min=1),
    hours: float | None = typer.Option(None, "--hours", min=0.001),
    interval_seconds: float | None = typer.Option(None, "--interval-seconds", min=0),
    layers: str = typer.Option("L2", "--layers"),
    scenario: str = typer.Option("echo", "--scenario"),
) -> None:
    """Run an accepted direct or production-agent vertical slice."""
    selected_layers = {item.strip().upper() for item in layers.split(",")}
    if cycles is not None and hours is not None:
        raise typer.BadParameter("choose either --cycles or --hours")
    if selected_layers not in ({"L2"}, {"L3"}, {"L4"}):
        raise typer.BadParameter("accepted vertical slices are L2, L3, or L4")
    config = load_config()
    target_contract = TargetRegistry(config.paths.targets_dir).get(target)
    if selected_layers == {"L4"}:
        if target != "job-search":
            raise typer.BadParameter("L4 production slice is defined for job-search")
        if scenario == "workflow" and (hours is not None or cycles is not None):
            effective_interval = (
                interval_seconds if interval_seconds is not None else (60.0 if hours else 0.0)
            )
            state = _execute_l4_soak(
                config,
                target_contract,
                cycles=None if hours is not None else (cycles or 1),
                hours=hours,
                interval_seconds=effective_interval,
            )
            if state.failures:
                raise typer.Exit(1)
            return
        if hours is not None or (cycles is not None and cycles != 1):
            raise typer.BadParameter(
                "only the read-only L4 workflow supports repeated or timed runs"
            )
        artifacts = config.paths.state_dir / "artifacts" / str(uuid.uuid4())
        if scenario in {"echo", "smoke"}:
            result = ZCodeHarness().run_smoke(target_contract, artifacts)
        elif scenario == "workflow":
            result = ZCodeHarness().run_read_only_workflow(target_contract, artifacts)
        elif scenario == "firewall":
            firewall_result = asyncio.run(
                run_live_firewall_probe(target_contract, artifacts / "direct-firewall-trace.jsonl")
            )
            typer.echo(
                f"{'PASS' if firewall_result.passed else 'FAIL'} "
                f"trace={firewall_result.trace_path} reason={firewall_result.reason}"
            )
            _record_production_check(
                config,
                scenario=scenario,
                provider="direct-mcp-sdk",
                model="none",
                passed=firewall_result.passed,
                session_id=None,
                trace_id=firewall_result.trace_id,
                trace_path=firewall_result.trace_path,
                reason=firewall_result.reason,
            )
            if not firewall_result.passed:
                raise typer.Exit(1)
            return
        elif scenario == "glm-escalation":
            result = ZCodeSubscriptionProvider().run_job_mcp_smoke(target_contract, artifacts)
        else:
            raise typer.BadParameter(
                "L4 scenario must be smoke, workflow, firewall, or glm-escalation"
            )
        typer.echo(
            f"{'PASS' if result.passed else 'FAIL'} model={result.model} "
            f"session={result.session_id} trace={result.trace_path} reason={result.reason}"
        )
        _record_production_check(
            config,
            scenario=scenario,
            provider="zai-coding-plan" if scenario == "glm-escalation" else "lmstudio",
            model=result.model,
            passed=result.passed,
            session_id=result.session_id,
            trace_id=result.trace_id,
            trace_path=result.trace_path,
            reason=result.reason,
        )
        if not result.passed:
            raise typer.Exit(1)
        return
    effective_interval = (
        interval_seconds if interval_seconds is not None else (60.0 if hours else 0.0)
    )
    if selected_layers == {"L3"}:
        if target != "job-search":
            raise typer.BadParameter("live L3 schema fuzz is defined for job-search")
        if scenario not in {"echo", "schema-fuzz"}:
            raise typer.BadParameter("L3 scenario must be schema-fuzz")
        state = _execute_l3_soak(
            config,
            target_contract,
            cycles=None if hours is not None else (cycles or 1),
            hours=hours,
            interval_seconds=effective_interval,
        )
        if state.failures:
            raise typer.Exit(1)
        return
    state = _execute_l2_soak(
        config,
        target_contract,
        scenario=scenario,
        cycles=None if hours is not None else (cycles or 1),
        hours=hours,
        interval_seconds=effective_interval,
    )
    if state.failures:
        raise typer.Exit(1)


@app.command()
def resume() -> None:
    config = load_config()
    checkpoint = config.paths.state_dir / "soak.json"
    if not checkpoint.exists():
        typer.echo("no persisted soak checkpoint", err=True)
        raise typer.Exit(1)
    runner = SoakRunner(checkpoint)
    saved = runner.load()
    if saved.status == "completed":
        typer.echo("checkpoint already completed")
        return
    metadata = saved.metadata or {}
    if metadata.get("layers") not in {"L2", "L3", "L4"} or not metadata.get("target"):
        typer.echo("checkpoint lacks a resumable L2/L3/L4 run specification", err=True)
        raise typer.Exit(1)
    target_contract = TargetRegistry(config.paths.targets_dir).get(metadata["target"])
    if metadata["layers"] == "L4":
        if metadata.get("scenario") != "workflow":
            typer.echo("only the read-only L4 workflow is resumable", err=True)
            raise typer.Exit(1)
        state = _execute_l4_soak(
            config,
            target_contract,
            cycles=None,
            hours=None,
            interval_seconds=float(metadata.get("interval_seconds", 0)),
            resume_state=saved,
        )
    elif metadata["layers"] == "L3":
        state = _execute_l3_soak(
            config,
            target_contract,
            cycles=None,
            hours=None,
            interval_seconds=float(metadata.get("interval_seconds", 0)),
            resume_state=saved,
        )
    else:
        state = _execute_l2_soak(
            config,
            target_contract,
            scenario=metadata.get("scenario", "echo"),
            cycles=None,
            hours=None,
            interval_seconds=float(metadata.get("interval_seconds", 0)),
            resume_state=saved,
        )
    if state.failures:
        raise typer.Exit(1)


@app.command()
def stop() -> None:
    config = load_config()
    stop_file = (config.paths.state_dir / "soak.json").with_suffix(".stop")
    stop_file.parent.mkdir(parents=True, exist_ok=True)
    stop_file.write_text("stop requested\n", encoding="utf-8")
    typer.echo(f"stop requested: {stop_file}")


@app.command()
def status() -> None:
    config = load_config()
    checkpoint = config.paths.state_dir / "soak.json"
    if checkpoint.exists():
        typer.echo(checkpoint.read_text(encoding="utf-8"))
    else:
        typer.echo(json.dumps(build_report(Database(config.paths.state_dir / "arl.db")), indent=2))


@app.command()
def report() -> None:
    config = load_config()
    paths = write_report(
        build_report(Database(config.paths.state_dir / "arl.db")), config.paths.reports_dir
    )
    typer.echo(f"markdown={paths[0]} json={paths[1]}")


@app.command()
def replay(cycle_id: str) -> None:
    config = load_config()
    database = Database(config.paths.state_dir / "arl.db")
    database.initialize()
    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT runs.target_name, layer_results.scenario_id
            FROM cycles JOIN runs ON runs.id = cycles.run_id
            JOIN layer_results ON layer_results.cycle_id = cycles.id
            WHERE cycles.id = ? ORDER BY layer_results.created_at DESC LIMIT 1
            """,
            (cycle_id,),
        ).fetchone()
    if row is None:
        typer.echo(f"cycle not found: {cycle_id}", err=True)
        raise typer.Exit(1)
    scenario_name = _scenario_name_for_id(config, row["target_name"], row["scenario_id"])
    target = TargetRegistry(config.paths.targets_dir).get(row["target_name"])
    result = asyncio.run(run_direct_scenario(config, target, scenario_name=scenario_name))
    typer.echo(json.dumps(result.__dict__, indent=2, default=str))
    if result.status != "pass":
        raise typer.Exit(1)


@app.command()
def isolate(failure_id: str) -> None:
    config = load_config()
    database = Database(config.paths.state_dir / "arl.db")
    database.initialize()
    with database.connect() as connection:
        row = connection.execute(
            "SELECT signature_json FROM failures WHERE id = ?", (failure_id,)
        ).fetchone()
    if row is None:
        typer.echo(f"failure not found: {failure_id}", err=True)
        raise typer.Exit(1)
    attribution = HypothesisEngine().attribute(json.loads(row["signature_json"]))
    typer.echo(json.dumps(attribution, default=lambda item: item.__dict__, indent=2))


@experiment_app.command("run")
def experiment_run(template_id: str, failure_id: str) -> None:
    selected = ExperimentPlanner().plan({template_id})
    if not selected:
        raise typer.BadParameter(f"unknown experiment template: {template_id}")
    config = load_config()
    database = Database(config.paths.state_dir / "arl.db")
    database.initialize()
    with database.connect() as connection:
        failure = connection.execute(
            "SELECT id FROM failures WHERE id = ?", (failure_id,)
        ).fetchone()
        if failure is None:
            typer.echo(f"failure not found: {failure_id}", err=True)
            raise typer.Exit(1)
        experiment_id = str(uuid.uuid4())
        template = selected[0]
        connection.execute(
            "INSERT INTO experiments VALUES (?, ?, ?, ?, ?, ?)",
            (
                experiment_id,
                failure_id,
                template.id,
                "planned",
                json.dumps(template.__dict__),
                datetime.now(UTC).isoformat(),
            ),
        )
    typer.echo(f"planned experiment={experiment_id} template={template.id}")


@app.command()
def regress(target: str) -> None:
    """Run the target's non-mutating regression suite in its source tree."""
    config = load_config()
    contract = TargetRegistry(config.paths.targets_dir).get(target)
    repo = contract.topology[0].server.repo
    if repo is None:
        raise typer.BadParameter(f"target {target} has no white-box repository")
    repo_path = Path(repo)
    if not repo_path.is_absolute():
        repo_path = config.paths.targets_dir.parent / repo_path
    if not repo_path.is_dir():
        raise typer.BadParameter(f"target repository does not exist: {repo_path}")
    results = run_regressions(
        L0Fixer(repo_path),
        (("pytest", ("uv", "run", "--extra", "dev", "pytest", "-q")),),
    )
    for result in results:
        typer.echo(
            f"{'PASS' if result.passed else 'FAIL'} {result.suite} "
            f"returncode={result.returncode}\n{result.output.strip()}"
        )
    if not results or not all(result.passed for result in results):
        raise typer.Exit(1)


@app.command()
def patterns(demo_gate: bool = typer.Option(False, "--demo-gate")) -> None:
    config = load_config()
    library = PatternLibrary(Database(config.paths.state_dir / "arl.db"))
    if demo_gate:
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
        result = TwoPassDiagnosis(library).diagnose(
            signature, lambda _: "ambiguous tool description"
        )
        if not result.patterns or result.patterns[0].pattern_id != "PT-DEMO-001":
            typer.echo("pattern reuse gate failed", err=True)
            raise typer.Exit(1)
        typer.echo("PASS pattern PT-DEMO-001 retrieved after independent diagnosis")
    items = library.list()
    typer.echo(json.dumps([item.__dict__ for item in items], indent=2, default=list))


@app.command()
def providers() -> None:
    config = load_config()
    desktop_bridge = ZCodeSubscriptionProvider()
    result = []
    for name, provider in config.providers.items():
        env_name = provider.get("auth_env")
        kind = provider.get("kind", "unknown")
        if env_name:
            if os.environ.get(str(env_name)):
                status = "configured_env"
            elif desktop_bridge.has_desktop_provider(str(provider.get("base_url", ""))):
                status = "configured_zcode_desktop"
            else:
                status = "credential_missing"
        elif kind == "zcode_subscription":
            health = ZCodeSubscriptionProvider().health()
            status = "configured" if health.available else "unavailable"
        else:
            status = "configured"
        result.append(
            {
                "name": name,
                "type": kind,
                "status": status,
            }
        )
    typer.echo(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
