import pytest

from arl.environment.web_proxy import WebProxy, WebResponse
from arl.targets.contract import SafetyMode


def test_web_proxy_records_and_replays_get(tmp_path) -> None:
    proxy = WebProxy(tmp_path, SafetyMode.SAFE_LIVE)
    response = proxy.request(
        "GET",
        "https://example.invalid/jobs",
        live_fetch=lambda method, url: WebResponse(200, {"content-type": "text/plain"}, "jobs"),
    )
    replayed = proxy.request("GET", "https://example.invalid/jobs", replay=True)
    assert response == replayed


def test_web_proxy_blocks_post_in_safe_live(tmp_path) -> None:
    proxy = WebProxy(tmp_path, SafetyMode.SAFE_LIVE)
    with pytest.raises(PermissionError, match="blocks live POST"):
        proxy.request(
            "POST",
            "https://example.invalid/apply",
            live_fetch=lambda method, url: WebResponse(201, {}, "submitted"),
        )
