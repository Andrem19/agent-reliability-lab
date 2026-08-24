from pathlib import Path

from arl.config import load_config
from arl.harnesses.zcode import ZCodeHarness
from arl.targets.registry import TargetRegistry


def test_zcode_workspace_uses_absolute_server_paths(tmp_path, monkeypatch) -> None:
    config = load_config()
    target = TargetRegistry(config.paths.targets_dir).get("job-search")
    fake_uv = Path("C:/tools/uv.exe")
    monkeypatch.setattr("arl.harnesses.zcode.shutil.which", lambda _: str(fake_uv))

    workspace_config = ZCodeHarness()._workspace_config(
        target, tmp_path, tmp_path / "trace.jsonl", "trace-id"
    )
    args = workspace_config["mcp"]["servers"]["work-researcher"]["args"]
    separator = args.index("--")
    server_args = args[separator + 1 :]

    assert server_args[0] == str(fake_uv)
    directory = Path(server_args[server_args.index("--directory") + 1])
    assert directory.is_absolute()
    assert directory.name == "WORK_RESEARCHER_MCP"
