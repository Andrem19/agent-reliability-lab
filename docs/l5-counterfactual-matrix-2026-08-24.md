# L5 counterfactual matrix — 2026-08-24

## Result

The bounded live L5 comparison passed all three available model/harness cells on
the same read-only `get_status` scenario. No timed provider soak was used.

| Model | Harness/provider | Result | Model calls in L5 |
|---|---|---:|---:|
| `qwen3.8-27b` | ZCode + LM Studio | PASS | 0 (advanced-L4 evidence reused) |
| `GLM-5.3` | native Z.ai Coding Plan in ZCode | PASS | 1 |
| `deepseek-official/deepseek-v4-flash` | DSH | PASS | 2 |

Each passing cell produced proxy evidence that the model requested the real Work
Researcher MCP `get_status` tool and returned the required response token. The
actual DSH-selected DeepSeek model was V4 Flash; this report does not claim that
V4 Pro was tested.

## Finding and repair

The first DeepSeek control returned the required token but produced no MCP trace.
`dsh --dump-config` proved that ARL's temporary patch tried to modify a plugin row
that did not yet exist, so the MCP client was never mounted. ARL now inserts the
plugin row explicitly. The single permitted confirmation call then passed with a
real proxy trace. This was an ARL DSH-adapter defect, not a Work Researcher MCP
failure.

## Evidence

- Qwen trace: `.arl/artifacts/3e3ab1c0-65e0-4b01-b600-40fb7afbb1e5/qwen-long-horizon-trace.jsonl`
- GLM trace: `.arl/artifacts/79d6ffe7-df30-408d-bb3c-f078d29071b5/glm53-job-search-mcp-trace.jsonl`
- DeepSeek passing trace: `.arl/artifacts/6358159c-50b9-44ec-acff-718b9f6eb2ff/dsh-job-search-mcp-trace.jsonl`

The L5 runner also reuses a previous passing provider cell, which prevents an
accidental rerun from spending another GLM call.
