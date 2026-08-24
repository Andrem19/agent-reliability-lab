import sys

from arl.runtime.timeouts import run_process


def test_process_timeout_is_classified() -> None:
    result = run_process((sys.executable, "-c", "import time; time.sleep(2)"), timeout=0.05)
    assert result.timed_out
    assert result.returncode is None


def test_process_success_is_captured() -> None:
    result = run_process((sys.executable, "-c", "print('ok')"), timeout=2)
    assert not result.timed_out
    assert result.returncode == 0
    assert result.stdout.strip() == "ok"
