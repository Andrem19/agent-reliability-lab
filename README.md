# Agent Reliability Lab

[![CI](https://github.com/Andrem19/agent-reliability-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/Andrem19/agent-reliability-lab/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Agent Reliability Lab (ARL) is a causal fault-isolation system for agent + MCP
stacks. The implementation follows vertical milestones: each later slice remains
gated until the preceding acceptance test passes.

## Implemented vertical slices

ARL currently provides:

- a validated MCP target contract with black/gray/white-box repair capabilities;
- SQLite metadata plus redacted JSONL event persistence;
- a recursive secret redactor and subprocess timeouts;
- verified Git worktree creation/removal helpers;
- clean demo and job-search target packs;
- blind mutation fixtures with isolated ground truth and attribution metrics;
- real MCP SDK execution over STDIO and Streamable HTTP, canonical traces, deterministic oracles;
- hypothesis ranking, counterfactual model×harness matrices, provider fallback/circuit breakers;
- scoped worktree repair, regression, recorded/live replay, and staging integration;
- ZCode/Qwen production harness with a trace-path side-effect firewall;
- schema fuzzing, chaos classification, evidence provenance/anti-injection, metamorphic and differential checks;
- capability graphs, synthesized-scenario lint, coverage scheduling, two-pass failure patterns, and checkpointed soak execution.

Native Z.ai Coding Plan / GLM-5.3 escalation, Qwen's production read-only Job MCP
workflow, the production firewall, live Adzuna search, and crash/resume have real
trace-backed acceptance evidence. The literal M7 Job Search MCP soak completed for
7243 seconds with 24/24 passing cycles and zero failures; elapsed time was never
simulated or accelerated.

The production MCP validation also found and repaired a real expired-token Google Drive
OAuth defect. Its unit regression and three live read-only replays pass; the commit is
promoted only to the target repository's `autotune/staging` branch, leaving `main`
untouched.

## Setup

```powershell
uv sync --extra dev --extra mcp
uv run arl doctor
uv run arl targets list
uv run arl targets inspect demo
uv run arl demo --baseline
uv run arl run demo --cycles 10 --layers L2
uv run arl run demo --hours 24 --layers L2
uv run arl status
uv run arl regress job-search
uv run arl report
uv run pytest
```

Copy `.zcode/config.example.json` to `.zcode/config.json` and adjust the local
model/MCP command when using the ZCode production harness. Local credentials,
runtime databases, traces, logs, and generated reports are intentionally ignored.

## Adding an MCP target

Create `targets/<name>/target.yaml`, `safety.yaml`, and one or more scenario YAML
files. Start with a direct L2 scenario, add deterministic oracle assertions, and
only then enable model-driven L4 workflows or repairs. See
[target pack authoring](docs/target-pack-authoring.md).

## Development

Changes should keep the deterministic core green:

```powershell
uv sync --extra dev --extra mcp
uv run ruff check .
uv run pytest -q
uv run arl demo --suite
```

Repairs to white-box targets are developed in isolated worktrees and promoted to
`autotune/staging`; ARL never writes directly to a target's default branch.

The production executor is never substituted: `job-search` requires ZCode and
the locally served `qwen3.8-27b`. If LM Studio is unavailable, doctor reports
`test_infra_unavailable`.

See [discovery](docs/discovery.md) and [architecture](docs/architecture.md).
The accepted two-hour production-target evidence is recorded in the
[Job Search MCP soak report](docs/job-mcp-soak-2026-08-24.md).
