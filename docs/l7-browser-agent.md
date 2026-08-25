# L7 Browser Agent

L7 validates the browser-execution part of the Work Researcher agent without
touching a real job board or the user's production browser profile.

## Tested stack

```text
direct SDK or local Qwen -> ZCode -> Work Researcher MCP -> browser_* -> Playwright
                                                          -> local ARL job board
```

The separate Playwright MCP is deliberately not used: it has a different browser
context and would not validate the embedded Work Researcher browser tools.

## Isolation and safety

Every L7 run creates a new artifact directory containing its own Work Researcher
configuration, SQLite database, CV directory, browser profile, upload fixture,
screenshots, MCP JSONL trace, and Playwright trace. Drive, providers, automatic
Google sign-in, and the production data directory are disabled.

The test board binds to `127.0.0.1` on an ephemeral port. The STDIO proxy applies
an exact-origin firewall to `browser_open` and `browser_login`; `browser_eval` is
classified as irreversible and blocked. The model is therefore unable to navigate
from an L7 run to a real site. A final Submit is permitted only because it posts to
the in-memory local test board.

## Deterministic scenarios

| Scenario | Assertions |
|---|---|
| `happy` | Cookie banner, target-blank popup, inputs, select, checkbox, hidden file upload, modal wizard, review, local submit, confirmation, screenshot, tabs, close. |
| `stale` | The site replaces a numbered button after the snapshot. The stale action must fail, a fresh snapshot must recover, and the workflow must then complete. |
| `session` | The wizard reports an expired session. The browser restarts the local application and completes it once. |
| `captcha` | A CAPTCHA/human-assistance screen appears. The run must stop safely with zero submissions. |

The environment oracle compares the submitted JSON exactly with the expected
candidate data and uploaded file metadata. It also asserts submit count, scenario
events, screenshots, allowed tool names, and navigation origin.

## Agent scenario

`scenario=agent` runs local Vision-enabled `qwen3.8-27b` from the tuned llama.cpp
server through the real ZCode harness. The model
must complete the same local happy path using only the supplied browser tools,
fresh modal snapshots, and the isolated upload file. ARL independently evaluates
the MCP trace and the local site's state; the model's final prose is not accepted
as proof by itself.

## Evidence

Each run emits:

- `l7-<scenario>-trace.jsonl`: MCP requests, responses, tool arguments and firewall decisions;
- `playwright-trace.zip`: Playwright DOM snapshots, screenshots, sources and network timeline;
- isolated Work Researcher data/profile directories;
- a final screenshot for successful submit scenarios;
- a production-check row when launched through the CLI.

Open a Playwright trace with `uv run playwright show-trace <trace.zip>` from the
Work Researcher repository.

## Commands

```powershell
# Four deterministic direct controls; no model call.
uv run arl run job-search --layers L7 --scenario suite

# One individual control.
uv run arl run job-search --layers L7 --scenario stale

# Bounded local-Qwen agent acceptance run.
uv run arl run job-search --layers L7 --scenario agent

# Two-hour mixed direct + Qwen/ZCode browser soak.
uv run arl run job-search --layers L7 --scenario soak --hours 2 --interval-seconds 60

# Resume an interrupted timed L7 run.
uv run arl resume-l7
```

The timed soak rotates direct happy-path, stale-DOM, expired-session and CAPTCHA
controls with real Qwen/ZCode agent runs. Agent cycles cover the happy path,
expired-session recovery and CAPTCHA safe-stop. It checkpoints to
`.arl/l7-browser-soak.json`; every cycle has a fresh loopback site, browser profile,
MCP trace, Playwright trace and data directory.

## Current readiness evidence

The bounded direct CLI gate completed on 2026-08-25 with 4/4 PASS: `happy`,
`stale`, `session`, and `captcha`. It also exposed a real Work Researcher browser
defect: modal element numbers collided with numbered fields behind the dialog, so
an agent could change Full name instead of the visible radio button. The modal
tagger now clears the background numbering namespace; the live regression and
target tests pass. The validated target changes are staged on Work Researcher
`autotune/staging` at `0f7d555`, leaving its default branch untouched.

The final clean mixed soak then ran for 7282.141 seconds and completed 47/47
cycles with zero failures. Its 30 direct controls covered 6 happy paths, 12
stale-DOM recoveries, 6 expired-session recoveries and 6 CAPTCHA stops. Its 17
real-agent controls ran Qwen through the tuned llama.cpp Vision endpoint and
ZCode: 6 happy paths, 6 session recoveries and 5 CAPTCHA safe-stops. The evidence
audit found 47 passing independent environment oracles, 47 MCP traces, 47
Playwright traces, exact loopback-only navigation across 47 fresh origins, and
zero forbidden calls.

An earlier run is deliberately excluded from acceptance because it exposed a
real CAPTCHA latency defect: repeated snapshots expanded the agent conversation
until ZCode hit its headers timeout. The prompt now follows Work Researcher's
bounded fresh-snapshot protocol and the minimal ZCode runtime has a suitable
network deadline. A bounded CAPTCHA replay passed before the clean two-hour run,
and the timeout did not recur.

## Real-site progression

Real job boards are a later shadow-mode target. The first real-site gate may open,
authenticate, fill, upload, and reach review, but must stop before the final submit.
A browser-level submit firewall needs semantic action metadata from Work Researcher
before real-site automated submission can be considered safe. CAPTCHA and 2FA must
always return control to the user.
