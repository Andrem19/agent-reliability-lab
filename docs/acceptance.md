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
| M7 | PASS | Capability graph, synthesis lint, coverage scheduler, persistent two-pass pattern reuse, kill/resume recovery, and a literal 7243-second Job Search MCP soak: 24/24 PASS with zero failures. |

## Latest verification

- `uv run ruff check .`: PASS.
- `uv run pytest -q`: 44 passed.
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
- Literal Job Search MCP soak: 7243 seconds, 24/24 PASS, zero failures, 11 live
  Adzuna provider cycles and 13 duplicate-cache cycles; live responses contained
  19–24 jobs and every provider report was healthy.
- Literal L3 schema-fuzz soak: 7225.844 seconds, 24/24 cycles and 456/456 schema
  assertions PASS with zero failures; only four read-only Job Search MCP tools were
  reachable and no model or application action was used.
- Literal L4 agent soak: 7323.140 seconds, 19/19 Qwen → ZCode → Job Search MCP
  workflows PASS with zero failures. Traces contain exactly 76 required read-only
  tool calls and no application, submission, browser, sync, push, or write call.
- Advanced L4 soak: 7421.938 seconds, 18/18 PASS (9 long-horizon and 9
  error-recovery), 99 strictly asserted read-only calls, zero forbidden calls and
  zero failures. A pre-soak structural oracle defect was detected and repaired.
- Bounded live L5 matrix: Qwen/ZCode, native Z.ai GLM-5.3/ZCode, and the actual
  DSH-selected `deepseek-official/deepseek-v4-flash` all PASS the same proxied
  read-only `get_status` control. GLM used one call; DeepSeek used one failed
  configuration probe and one passing confirmation after the DSH adapter repair.
- Runtime reports: `.arl` metadata to `reports/runtime/report.md` and `report.json`.

## Optional extended evidence

A full 24-hour run remains available with `uv run arl run job-search --hours 24
--layers L2 --scenario live_search --interval-seconds 300` when evidence beyond
the accepted two-hour M7 gate is desired.

These checks are not replaced by mocks or accelerated clocks.
