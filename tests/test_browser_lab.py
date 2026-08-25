import json
import urllib.request

from arl.browser_lab import BrowserLabServer
from arl.engines.browser_agent import _find, write_isolated_work_researcher_config


def test_local_job_board_records_submission_and_stale_state() -> None:
    with BrowserLabServer() as site:
        run_id, start_url = site.new_run("stale")
        assert urlopen_text(start_url).find("Apply now") >= 0
        site.arm_stale_refresh(run_id)
        request = urllib.request.Request(
            f"{site.origin}/api/submit?run_id={run_id}",
            data=json.dumps({"full_name": "Test"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            assert json.load(response)["ok"]
        state = site.state(run_id)

    assert state["stale_generation"] == 1
    assert state["submit_count"] == 1
    assert state["submission"] == {"full_name": "Test"}


def test_isolated_browser_config_never_uses_production_data(tmp_path) -> None:
    path = write_isolated_work_researcher_config(tmp_path)
    text = path.read_text(encoding="utf-8")

    assert tmp_path.resolve().as_posix() in text
    assert "auto_google_signin = false" in text
    assert "enabled = false" in text


def test_browser_element_lookup_supports_snapshots_and_forms() -> None:
    assert _find({"elements": [{"n": 4, "name": "Apply now"}]}, "apply") == 4
    assert _find({"fields": [{"n": 2, "label": "Email address"}]}, "email", fields=True) == 2


def urlopen_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=3) as response:
        return response.read().decode()
