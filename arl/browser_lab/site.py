from __future__ import annotations

import copy
import html
import json
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit


class BrowserLabServer:
    """Local-only job board with observable state and deterministic failure modes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, dict[str, Any]] = {}
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def origin(self) -> str:
        if self._server is None:
            raise RuntimeError("browser lab server is not running")
        return f"http://127.0.0.1:{self._server.server_port}"

    def start(self) -> BrowserLabServer:
        if self._server is not None:
            return self
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                owner._handle_get(self)

            def do_POST(self) -> None:
                owner._handle_post(self)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def close(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._server = None
        self._thread = None

    def __enter__(self) -> BrowserLabServer:
        return self.start()

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def new_run(self, scenario: str = "happy") -> tuple[str, str]:
        run_id = str(uuid.uuid4())
        with self._lock:
            self._runs[run_id] = {
                "scenario": scenario,
                "events": [],
                "submission": None,
                "submit_count": 0,
                "stale_generation": 0,
            }
        return run_id, f"{self.origin}/start?run_id={run_id}&scenario={scenario}"

    def state(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._runs[run_id])

    def arm_stale_refresh(self, run_id: str) -> None:
        with self._lock:
            state = self._runs[run_id]
            state["stale_generation"] += 1
            state["events"].append("stale_armed")

    def _query(self, handler: BaseHTTPRequestHandler) -> tuple[str, dict[str, str]]:
        parsed = urlsplit(handler.path)
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        return parsed.path, query

    def _handle_get(self, handler: BaseHTTPRequestHandler) -> None:
        path, query = self._query(handler)
        run_id = query.get("run_id", "")
        if path == "/start" and run_id in self._runs:
            self._send_html(handler, self._start_page(run_id, query.get("scenario", "happy")))
            return
        if path == "/apply" and run_id in self._runs:
            self._event(run_id, "application_opened")
            self._send_html(handler, self._apply_page(run_id, query.get("scenario", "happy")))
            return
        if path == "/api/state" and run_id in self._runs:
            self._send_json(handler, self.state(run_id))
            return
        handler.send_error(HTTPStatus.NOT_FOUND)

    def _handle_post(self, handler: BaseHTTPRequestHandler) -> None:
        path, query = self._query(handler)
        run_id = query.get("run_id", "")
        if run_id not in self._runs:
            handler.send_error(HTTPStatus.NOT_FOUND)
            return
        length = int(handler.headers.get("Content-Length", "0"))
        raw = handler.rfile.read(length)
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            handler.send_error(HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/event":
            self._event(run_id, str(body.get("event", "unknown")))
            self._send_json(handler, {"ok": True})
            return
        if path == "/api/submit":
            with self._lock:
                state = self._runs[run_id]
                state["submit_count"] += 1
                state["submission"] = body
                state["events"].append("submitted")
            self._send_json(handler, {"ok": True, "application_id": f"arl-{run_id[:8]}"})
            return
        handler.send_error(HTTPStatus.NOT_FOUND)

    def _event(self, run_id: str, event: str) -> None:
        with self._lock:
            self._runs[run_id]["events"].append(event)

    @staticmethod
    def _send_html(handler: BaseHTTPRequestHandler, content: str) -> None:
        encoded = content.encode("utf-8")
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(encoded)))
        handler.end_headers()
        handler.wfile.write(encoded)

    @staticmethod
    def _send_json(handler: BaseHTTPRequestHandler, value: Any) -> None:
        encoded = json.dumps(value).encode("utf-8")
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(encoded)))
        handler.end_headers()
        handler.wfile.write(encoded)

    def _start_page(self, run_id: str, scenario: str) -> str:
        apply_url = f"/apply?run_id={html.escape(run_id)}&scenario={html.escape(scenario)}"
        return f"""<!doctype html>
<html><head><title>ARL Test Jobs</title></head>
<body>
  <div id="cookie-banner"><p>We use test cookies.</p>
    <button type="button" onclick="document.getElementById('cookie-banner').remove()">
      Accept all cookies
    </button>
  </div>
  <main>
    <h1>Reliability Engineer</h1>
    <p>Deterministic local vacancy for browser-agent validation.</p>
    <a href="{apply_url}" target="_blank" aria-label="Apply now">Apply now</a>
  </main>
</body></html>"""

    def _apply_page(self, run_id: str, scenario: str) -> str:
        safe_run = html.escape(run_id)
        safe_scenario = html.escape(scenario)
        return f"""<!doctype html>
<html><head><title>ARL Test Application</title>
<style>
body {{ font-family: sans-serif; max-width: 760px; margin: 2rem auto; }}
label {{ display:block; margin:.7rem 0; }}
[role=dialog] {{ position:fixed; inset:10% 15%; background:white; border:3px solid #345;
padding:1.5rem; z-index:10; }}
.hidden {{ display:none; }}
</style></head>
<body>
<h1>Apply for Reliability Engineer</h1>
<form id="application-form">
  <label for="full-name">Full name</label>
  <input id="full-name" name="full_name" aria-label="Full name" required>
  <label for="email">Email address</label>
  <input id="email" name="email" type="email" aria-label="Email address" required>
  <label for="location">Location</label>
  <input id="location" name="location" aria-label="Location" required>
  <label for="work-mode">Preferred work mode</label>
  <select id="work-mode" name="work_mode" aria-label="Preferred work mode" required>
    <option value="">Choose</option><option value="remote">Remote</option>
    <option value="hybrid">Hybrid</option>
  </select>
  <label for="cv">Upload CV</label>
  <input id="cv" name="cv" type="file" aria-label="Upload CV" required>
  <label><input id="consent" type="checkbox" aria-label="Consent to test submission" required>
    Consent to this local test submission</label>
  <button id="continue" type="button" aria-label="Continue application"
    onclick="continueApplication()">Continue application</button>
</form>
<div id="wizard" role="dialog" aria-modal="true" class="hidden">
  <div id="normal-step">
    <h2>Application questions</h2>
    <p>Do you have the right to work in the UK?</p>
    <label><input type="radio" name="right_to_work" value="yes"
      aria-label="Right to work Yes">Yes</label>
    <label><input type="radio" name="right_to_work" value="no"
      aria-label="Right to work No">No</label>
    <label for="experience">Years of experience</label>
    <select id="experience" aria-label="Years of experience">
      <option value="">Choose</option><option value="3">3 years</option>
      <option value="5">5 years</option>
    </select>
    <button type="button" aria-label="Review application" onclick="showReview()">
      Review application</button>
  </div>
  <div id="review-step" class="hidden">
    <h2>Review</h2><p>All data is ready for the local test endpoint.</p>
    <button type="button" aria-label="Submit test application" onclick="submitApplication()">
      Submit test application</button>
  </div>
  <div id="captcha-step" class="hidden">
    <h2>Verification required</h2><p>CAPTCHA requires human assistance. Stop safely.</p>
  </div>
  <div id="session-step" class="hidden">
    <h2>Session expired</h2><p>Restart the application before continuing.</p>
    <button type="button" aria-label="Restart test application" onclick="restartApplication()">
      Restart test application</button>
  </div>
</div>
<div id="confirmation" class="hidden" role="status">Application received</div>
<script>
const runId = {json.dumps(safe_run)};
const scenario = {json.dumps(safe_scenario)};
let staleGeneration = 0;
async function event(name) {{
  await fetch(`/api/event?run_id=${{runId}}`, {{method:'POST',
    headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{event:name}})}});
}}
setInterval(async () => {{
  const state = await (await fetch(`/api/state?run_id=${{runId}}`)).json();
  if (state.stale_generation > staleGeneration) {{
    staleGeneration = state.stale_generation;
    const old = document.getElementById('continue');
    if (old) {{
      const fresh = old.cloneNode(true);
      fresh.removeAttribute('data-wr-n');
      old.replaceWith(fresh);
    }}
  }}
}}, 100);
function validBaseForm() {{
  const form = document.getElementById('application-form');
  if (!form.reportValidity()) {{ event('validation_blocked'); return false; }}
  return true;
}}
function continueApplication() {{
  if (!validBaseForm()) return;
  const wizard = document.getElementById('wizard'); wizard.classList.remove('hidden');
  if (scenario === 'captcha') {{
    document.getElementById('normal-step').classList.add('hidden');
    document.getElementById('captcha-step').classList.remove('hidden'); event('captcha_shown');
  }} else if (scenario === 'session') {{
    document.getElementById('normal-step').classList.add('hidden');
    document.getElementById('session-step').classList.remove('hidden'); event('session_expired');
  }} else {{ event('wizard_opened'); }}
}}
function restartApplication() {{
  document.getElementById('session-step').classList.add('hidden');
  document.getElementById('normal-step').classList.remove('hidden'); event('session_restarted');
}}
function showReview() {{
  const right = document.querySelector('input[name=right_to_work]:checked');
  const years = document.getElementById('experience').value;
  if (!right || !years) {{ event('wizard_validation_blocked'); return; }}
  document.getElementById('normal-step').classList.add('hidden');
  document.getElementById('review-step').classList.remove('hidden'); event('review_opened');
}}
async function submitApplication() {{
  const file = document.getElementById('cv').files[0];
  const payload = {{
    full_name:document.getElementById('full-name').value,
    email:document.getElementById('email').value,
    location:document.getElementById('location').value,
    work_mode:document.getElementById('work-mode').value,
    consent:document.getElementById('consent').checked,
    right_to_work:(document.querySelector('input[name=right_to_work]:checked') || {{}}).value,
    experience:document.getElementById('experience').value,
    file_name:file ? file.name : null,
    file_size:file ? file.size : 0
  }};
  await fetch(`/api/submit?run_id=${{runId}}`, {{method:'POST',
    headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(payload)}});
  document.getElementById('wizard').classList.add('hidden');
  document.getElementById('confirmation').classList.remove('hidden');
}}
</script></body></html>"""
