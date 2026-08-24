import subprocess
import sys
from pathlib import Path

from arl.isolation.hypotheses import HypothesisEngine
from arl.repair.pipeline import RepairPipeline
from arl.repair.router import route_repair
from arl.targets.contract import load_target


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", str(repo), *args),
        capture_output=True,
        text=True,
        check=True,
    )


def _seed_bug_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "arl-test@example.invalid")
    _git(repo, "config", "user.name", "ARL Test")
    (repo / "calc.py").write_text(
        "def add(left: int, right: int) -> int:\n    return left + right + 1\n",
        encoding="utf-8",
    )
    _git(repo, "add", "calc.py")
    _git(repo, "commit", "-m", "inject logic bug")
    return repo


def _replay(repo: Path) -> bool:
    completed = subprocess.run(
        (sys.executable, "-c", "import calc; raise SystemExit(calc.add(2, 3) != 5)"),
        cwd=repo,
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


LOGIC_FIX = """diff --git a/calc.py b/calc.py
index b6e6cab..16d7268 100644
--- a/calc.py
+++ b/calc.py
@@ -1,2 +1,2 @@
 def add(left: int, right: int) -> int:
-    return left + right + 1
+    return left + right
"""


def test_logic_bug_full_fix_replay_staging_cycle(tmp_path) -> None:
    repo = _seed_bug_repo(tmp_path)
    pipeline = RepairPipeline(repo, tmp_path / "worktrees")
    result = pipeline.run(
        diff=LOGIC_FIX,
        allowed_paths=("calc.py",),
        regression_suites=(
            (
                "fast",
                (sys.executable, "-c", "import calc; assert calc.add(10, 4) == 14"),
            ),
            (
                "relevant",
                (sys.executable, "-c", "import calc; assert calc.add(-1, 1) == 0"),
            ),
        ),
        replay_check=_replay,
        replay_attempts=1,
        commit_message="autofix(cycle-test): fix add semantics",
    )
    assert result.accepted, result.reason
    assert result.replay is not None
    assert result.replay.baseline.success_rate == 0
    assert result.replay.after.success_rate == 1
    staging = _git(repo, "rev-parse", "autotune/staging").stdout.strip()
    assert staging == result.commit
    assert _git(repo, "show", "autotune/staging:calc.py").stdout.endswith("left + right\n")
    assert _git(repo, "show", "main:calc.py").stdout.endswith("left + right + 1\n")


def test_malicious_patch_is_rejected_before_worktree_creation(tmp_path) -> None:
    repo = _seed_bug_repo(tmp_path)
    malicious = LOGIC_FIX.replace("return left + right", "import os; os.system('whoami'); return 5")
    worktrees = tmp_path / "worktrees"
    result = RepairPipeline(repo, worktrees).run(
        diff=malicious,
        allowed_paths=("calc.py",),
        regression_suites=(("fast", (sys.executable, "-c", "pass")),),
        replay_check=_replay,
    )
    assert not result.accepted
    assert result.status == "rejected_policy"
    assert not worktrees.exists()


def test_router_blocks_oracle_and_environment_repairs() -> None:
    target = load_target(Path("targets/demo/target.yaml"))
    engine = HypothesisEngine()
    oracle = engine.attribute(
        {"failure": True, "primary_oracle": "fail", "independent_oracle": "pass"}
    )
    environment = engine.attribute({"failure": True, "live": "fail", "mock": "pass"})
    assert not route_repair(target, oracle, oracle_type="DETERMINISTIC").allowed
    assert not route_repair(target, environment, oracle_type="DETERMINISTIC").allowed
