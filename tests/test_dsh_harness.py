from pathlib import Path

from arl.config import load_config
from arl.harnesses.dsh import DSHHarness
from arl.targets.registry import TargetRegistry


def test_dsh_patch_routes_mcp_through_trace_proxy(tmp_path, monkeypatch) -> None:
    config = load_config()
    target = TargetRegistry(config.paths.targets_dir).get("job-search")
    fake_uv = Path("C:/tools/uv.exe")
    monkeypatch.setattr("arl.harnesses.dsh.shutil.which", lambda _: str(fake_uv))

    patch = DSHHarness(executable="dsh.cmd")._patch_config(
        target, tmp_path / "trace.jsonl", "trace-id"
    )
    row = patch[0]["insert"][0]
    args = row["config"]["args"]
    separator = args.index("--")

    assert row["id"] == "mcp-work-researcher"
    assert args[:2] == ["-m", "arl.tracing.stdio_proxy"]
    assert args[separator + 1] == str(fake_uv)
    assert "record_application" in args
