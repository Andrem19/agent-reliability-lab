# Job Search MCP two-hour soak report

Date: 2026-08-24

## Result

- Status: PASS
- Elapsed time: 7243.047 seconds
- Cycles: 24
- Passed: 24
- Failed: 0
- Pass rate: 100%
- Interval: 300 seconds
- Scenario: `job-search/live_search`
- Safety mode: read-only L2; no application or submit actions

## MCP and provider coverage

- Live Adzuna provider cycles: 11/11 healthy
- Duplicate-cache cycles: 13
- Unique search IDs: 12
- Jobs returned per cycle: 19–24
- Cycle duration: min 0.959 s, average 1.758 s, max 2.825 s
- stderr: empty

## Trace boundaries

- First run: `fb620441-8bbe-4718-9038-110a107ff368`
- Last run: `fe1256af-2d9b-472e-9b61-4cc73b990819`
- Traces: `.arl/artifacts/<run-id>/mcp-trace.jsonl`

## Findings

Before the clean soak, the original `Data Analyst` scenario allowed location and
requirements post-filters to remove every result, producing a false oracle failure.
The scenario was corrected to use a broader `Analyst` provider probe with those two
post-filters disabled. A real control call passed, the fix was published as `3942102`,
and the clean two-hour run then completed without a failure.

This L2 soak validates MCP startup, initialization, tool discovery, `search_jobs`,
Adzuna integration, duplicate caching, response-policy assertions, tracing, SQLite
persistence, and orderly shutdown. It intentionally does not invoke Qwen, DeepSeek,
GLM, browser automation, or application submission.

## Final gates

- Ruff: PASS
- Pytest: 42 passed
- Mutation attribution: top-1 1.0, top-3 1.0, false repair rate 0.0
- Doctor: core integrations PASS; Docker L1 remains optional and unavailable
