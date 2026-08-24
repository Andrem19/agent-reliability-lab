import subprocess

from arl.repair.worktree import WorktreeManager


def _git(repo, *args):
    return subprocess.run(
        ("git", "-C", str(repo), *args),
        capture_output=True,
        text=True,
        check=True,
    )


def test_worktree_create_and_remove_are_scoped(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "arl-test@example.invalid")
    _git(repo, "config", "user.name", "ARL Test")
    (repo / "seed.txt").write_text("seed", encoding="utf-8")
    _git(repo, "add", "seed.txt")
    _git(repo, "commit", "-m", "seed")

    manager = WorktreeManager(repo, tmp_path / "worktrees")
    worktree = manager.create("autofix/cycle-1")
    assert worktree.parent == (tmp_path / "worktrees").resolve()
    assert (worktree / "seed.txt").exists()
    manager.remove(worktree)
    assert not worktree.exists()
