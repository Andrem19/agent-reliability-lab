from pathlib import Path

import pytest

from arl.config import LabConfig, PathConfig
from arl.engines.direct import run_direct_scenario
from arl.safety.firewall import SideEffectFirewall
from arl.safety.risk_class import RiskClass, classify_tool
from arl.targets.registry import TargetRegistry
from arl.tracing.stdio_proxy import browser_url_allowed


def test_safe_live_blocks_irreversible_for_demo_and_job_search() -> None:
    targets, errors = TargetRegistry(Path("targets")).discover()
    assert not errors
    for name, tool in (("demo", "submit_demo"), ("job-search", "record_application")):
        target = targets[name]
        firewall = SideEffectFirewall(
            target.environment.default_mode,
            irreversible_tools=set(target.safety.irreversible_tools),
        )
        decision = firewall.decide(tool, classify_tool(tool))
        assert not decision.allowed
        assert RiskClass.EXTERNAL_SUBMIT in decision.risks


def test_browser_origin_firewall_uses_exact_origin() -> None:
    allowed = {"http://127.0.0.1:8765"}

    assert browser_url_allowed("http://127.0.0.1:8765/apply?run=1", allowed)
    assert not browser_url_allowed("http://127.0.0.1:8766/apply", allowed)
    assert not browser_url_allowed("https://example.com/apply", allowed)
    assert not browser_url_allowed("file:///etc/passwd", allowed)


@pytest.mark.asyncio
async def test_stdio_proxy_blocks_demo_submit_end_to_end(tmp_path) -> None:
    config = LabConfig(
        paths=PathConfig(
            state_dir=tmp_path / "state",
            targets_dir=(Path.cwd() / "targets").resolve(),
            reports_dir=tmp_path / "reports",
        )
    )
    target = TargetRegistry(config.paths.targets_dir).get("demo")
    result = await run_direct_scenario(config, target, scenario_name="blocked_submit")
    assert result.status == "pass", result.reason
    trace = result.trace_path.read_text(encoding="utf-8")
    assert "SAFE_LIVE blocks irreversible action" in trace
    assert "must-not-submit" in trace
