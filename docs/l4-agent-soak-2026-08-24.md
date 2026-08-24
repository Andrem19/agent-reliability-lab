# L4 agent two-hour soak report

Date: 2026-08-24

## Result

- Status: PASS
- Elapsed time: 7323.140 seconds (2 h 2 min 3 s)
- Cycles: 19
- Passed: 19
- Failed: 0
- Pass rate: 100%
- Interval: 300 seconds
- Model: `qwen3.8-27b` in LM Studio
- Harness: ZCode `0.16.3`
- Target: Job Search MCP
- stderr: empty

## Agent and MCP coverage

Every cycle ran the real model-to-tool chain `Qwen → ZCode → MCP`. Proxy traces
recorded exactly 76 tool calls:

- `get_status`: 19
- `list_stored_jobs`: 19
- `get_job`: 19
- `check_applied`: 19

No `start_application`, `record_application`, submission, browser, sync, push, or
write tool was called.

## Trace boundaries

- First production check: `2026-08-24T17:43:43.238691+00:00`
- First session: `sess_9fe0dc9c-8ab3-4b6b-a56d-d326adbb64ec`
- First trace: `.arl/artifacts/a6588b35-8787-4e9c-8c98-923ef45d98eb/qwen-job-workflow-trace.jsonl`
- Last production check: `2026-08-24T19:38:46.520096+00:00`
- Last session: `sess_7b1f953f-4a8c-4ff9-ad71-277d10846e82`
- Last trace: `.arl/artifacts/a924ed7d-d56a-4e85-a9bd-b5b7b96d3e9d/qwen-job-workflow-trace.jsonl`

SQLite contains 19 matching `workflow/lmstudio/qwen3.8-27b` production checks,
all with `scenario trace assertions passed`.

## Defect found before the clean soak

The first control run exposed a harness defect: ZCode started in an isolated
workspace while the MCP target still used a relative `uv --directory` path. The
MCP process therefore failed before initialization with Windows `os error 2`.

The harness now resolves the executable and target directory to absolute paths.
A regression test was added, the next real Qwen control passed in 145 seconds,
and the fix was published in commit `e61e82f`. No defect or intermittent failure
occurred during the subsequent clean two-hour soak.

## Final gates

- Ruff: PASS
- Pytest: 44 passed
- Mutation attribution: top-1 1.0, top-3 1.0, false repair rate 0.0
- Doctor: ZCode, Qwen, native Z.ai Coding Plan / GLM-5.3, DeepSeek Harness,
  target contracts, reference MCP, and SQLite available
- Docker L1: optional warning; unavailable
- Runtime Markdown and JSON reports regenerated

