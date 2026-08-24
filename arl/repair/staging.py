from __future__ import annotations

from pathlib import Path

from arl.runtime.timeouts import run_process


def promote_to_staging(repo: Path, commit: str, branch: str = "autotune/staging") -> None:
    repo = repo.resolve()
    verify = run_process(("git", "-C", str(repo), "cat-file", "-e", f"{commit}^{{commit}}"))
    if verify.returncode != 0:
        raise ValueError(f"unknown patch commit: {commit}")
    existing = run_process(("git", "-C", str(repo), "rev-parse", "--verify", branch))
    if existing.returncode == 0:
        ancestor = run_process(
            ("git", "-C", str(repo), "merge-base", "--is-ancestor", existing.stdout.strip(), commit)
        )
        if ancestor.returncode != 0:
            raise RuntimeError("staging promotion is not a fast-forward")
    update = run_process(("git", "-C", str(repo), "update-ref", f"refs/heads/{branch}", commit))
    if update.returncode != 0:
        raise RuntimeError(update.stderr.strip() or update.stdout.strip())
