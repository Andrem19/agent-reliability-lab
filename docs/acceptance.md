# Acceptance status — 2026-08-24

This file distinguishes executable evidence from pending external or elapsed-time checks.

| Milestone | Status | Evidence |
|---|---|---|
| M0 | PASS | Valid demo/production contracts, doctor, redaction, timeout and worktree tests. |
| M1 | PASS | Real MCP SDK L2 run through the STDIO trace proxy and deterministic oracle. |
| M2 | PASS | Blind five-case mutation suite: top-1 1.0, top-3 1.0, baseline false repair rate 0.0. |
| M3 | PASS | Logic repair/replay/staging test; oracle/environment no-code routes; malicious patch rejection. |
| M4 | PASS | Real ZCode `0.16.3` + LM Studio `qwen3.8-27b` + Job Search MCP run, with proxy trace and submit firewall tests. |
| M5 | PASS | Transport-only fallback/circuit breaker, automatic model×harness interaction detection, Streamable HTTP client path, protocol compatibility matrix, and real native Z.ai Coding Plan / GLM-5.3 execution. |
| M6 | PASS | Boundary fuzz crash detection, high-risk live-fuzz block, injection canary neutralization and proxy-confirmed chaos attribution. |
| M7 | RUNNING | Capability graph, synthesis lint, coverage scheduler and persistent two-pass pattern reuse pass. A real kill/resume test continued from 2/5 to 5/5 cycles without state loss. The literal two-hour soak is currently running with a five-minute interval. |

## Latest verification

- `uv run ruff check .`: PASS.
- `uv run pytest -q`: 42 passed.
- `uv run arl demo --suite`: top-1/top-3 1.0, false repair rate 0.0.
- Qwen/ZCode/Job MCP read-only workflow: `get_status → list_stored_jobs → get_job → check_applied`, PASS with no forbidden calls.
- Native Z.ai Coding Plan / GLM-5.3 escalation called proxied Job MCP `get_status`, PASS.
- Production direct firewall probe blocked `record_application` before the MCP server, PASS.
- Live Adzuna `search_jobs` returned 25 jobs; its versioned repeat-safe L2 oracle passes.
- Google Drive OAuth failure was attributed to `MCP_LOGIC`, repaired in an isolated
  worktree, replayed live 3/3, and merged only into `autotune/staging` at `9dc8fe0`;
  target regression is 6/6 and `main` remains `b96e6d5`.
- `uv run arl regress job-search`: real target pytest suite, PASS.
- `arl patterns --demo-gate`: persistent `PT-DEMO-001` retrieved only after independent diagnosis, PASS.
- Ctrl+C after 2/5 soak cycles followed by `arl resume`: completed 5/5, zero failures.
- Runtime reports: `.arl` metadata to `reports/runtime/report.md` and `report.json`.

## Pending Definition of Done evidence

1. Let the active literal two-hour soak reach at least 7200 elapsed seconds with zero failures; its heartbeat monitor will finalize this document and reports.
2. A full 24-hour run remains available with `uv run arl run demo --hours 24 --layers L2 --interval-seconds 300` when 24-hour evidence rather than the M7 two-hour gate is desired.

These checks are not replaced by mocks or accelerated clocks.
