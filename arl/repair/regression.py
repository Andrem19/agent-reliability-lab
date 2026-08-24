from __future__ import annotations

from dataclasses import dataclass

from arl.repair.sandbox import L0Fixer


@dataclass(frozen=True)
class RegressionResult:
    suite: str
    passed: bool
    returncode: int | None
    output: str


def run_regressions(
    fixer: L0Fixer,
    suites: tuple[tuple[str, tuple[str, ...]], ...],
) -> tuple[RegressionResult, ...]:
    results: list[RegressionResult] = []
    for name, command in suites:
        process = fixer.run(command)
        result = RegressionResult(
            name,
            process.returncode == 0 and not process.timed_out,
            process.returncode,
            (process.stdout + process.stderr)[-4000:],
        )
        results.append(result)
        if not result.passed:
            break
    return tuple(results)
