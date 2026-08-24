# Discovery report — 2026-08-24

This report records installed behavior, not assumed interfaces. Commands were
checked with local `--help`, configuration, health probes, and read-only MCP
handshakes. Secrets and credential values were not read into this report.

## Installed components

| Component | Finding | Status |
|---|---|---|
| MCP repositories | Sibling `WORK_RESEARCHER_MCP`, Python package `work-researcher-mcp 0.1.0`, `mcp>=2,<3`; stdio launch via `uv run --directory ... work-researcher serve --transport stdio`; 29 tools discovered. Another local MCP was excluded from the V1 reference scope. | Reference target handshake passed through ZCode, OpenCode, and DSH configurations. |
| Reference tests | The dev extra installs cleanly in isolated worktrees. The original suite passes 5/5; the staged Google Drive regression expands it to 6/6. | PASS in repair and staging worktrees. |
| ZCode desktop | `C:/Program Files/ZCode/ZCode.exe`, product version `3.8.1.5310`. | Installed. |
| ZCode programmatic interface | Bundled `resources/glm/zcode.cjs`, CLI version `0.16.3`. It supports `app-server` (ZCode Protocol over stdio), one-shot `--prompt`, `--json`, `--cwd`, model/tool controls, session resume, and TUI. Desktop internally exposes typed RPC channels including task, agent, session, model-provider, hooks, and MCP sync. | Use bundled CLI/app-server; no UI automation. |
| Qwen executor | Installed configuration identifies `qwen3.8-27b` through LM Studio at `http://127.0.0.1:1234/v1`. It completed traced Job MCP smoke and four-tool read-only workflows. | Live production acceptance passed. |
| OpenCode | Desktop installed under the current user's local application directory; target MCP is configured and handshake passed. Config exposes local Qwen plus Command Code models. | Desktop present; a separate `opencode` CLI was not in `PATH`. |
| DeepSeek Harness | `@deepseek-ai/dsh 0.1.0-rc.6`; headless one-shot syntax is `dsh --profile headless "task"`. MCP plugin handshake passed. | Available. |
| Command Code | OpenAI-compatible provider configured at `https://api.commandcode.ai/provider/v1`; discovered catalog contains DeepSeek v4 Flash/Pro and GLM/Qwen entries. | Configuration exists; authenticated model health calls are deferred to M5 to avoid subscription use during M0. |
| GLM-5.3 via Z.ai | ZCode Desktop's native `builtin:zai-coding-plan` provider exposes `GLM-5.3`. The authenticated Coding Plan completed an exact-token UI probe and a programmatic proxied Job MCP `get_status` call. | Live native-provider acceptance passed. |
| MCP Inspector | npm package `@modelcontextprotocol/inspector 2.3.0`, requires Node `>=22.19`; local Node is `24.19.0`. CLI is selected with `--cli` and emits machine-readable one-shot results. | Available via `npx`; integrate as L1 backend rather than reimplementing it. |
| MCP conformance | npm package `@modelcontextprotocol/conformance 0.1.16`; commands: `client`, `server`, `tier-check`, `list`. It supports dated spec filtering including `2025-11-25` and `2026-07-28` where scenarios apply. | Available via `npx`; stdio targets will need an adapter because server mode takes an HTTP URL. |
| mcp-eval | No local command/package was found. Search results did not establish an official MCP project with a stable, installed CLI contract. | Do not depend on it; revisit as an optional backend only after repository/version discovery. |
| Raindrop Workshop | No installed component or authoritative local interface was found. | Treat trace/replay concepts as inspiration only; no dependency. |
| Sandbox | Docker/Podman command not found. Windows subprocess isolation is available. | M0 supports mandatory L0 only; L1/L2 unavailable. |
| Trace methods | Demo and job-search are stdio: STDIO proxy is the V1 primary method. ZCode JSONL logs and app-server events can supplement harness spans. Native MCP `_meta` trace context is conditional on negotiated protocol support. | STDIO proxy + harness events available; native OTel not yet proven. |
| Git | ARL began as an empty non-repository and was initialized on `main`. A real Drive OAuth defect was fixed at `bca9bda` in an isolated worktree and merged at `9dc8fe0` only to `autotune/staging`; reference `main` remains `b96e6d5`. | Worktree/staging isolation verified. |

## Main integration risks

1. The production executor depends on LM Studio being up with the exact Qwen model;
   doctor verifies this before L4 execution.
2. ZCode desktop and its bundled CLI have different product versions; the adapter
   must fingerprint both and treat the CLI's observed protocol as authoritative.
3. The reference MCP has externally visible browser/application actions. SAFE_LIVE
   must block the final irreversible record/submit boundary in both proxy and adapter.
4. No container runtime is installed, so arbitrary fixer/test code has only L0
   isolation until Docker or Podman is installed.
5. Command Code and Z.ai are subscription-backed; health checks distinguish local
   configuration from live authenticated acceptance and redact all credentials.
6. MCP 2026-07-28 behavior is draft/release-candidate era in installed tools. Results
   must persist a protocol compatibility matrix and must not label expected stateless
   behavior as regression.

## Authoritative interface references

- [MCP Inspector CLI](https://github.com/modelcontextprotocol/inspector/blob/main/clients/cli/README.md)
- [MCP Conformance](https://github.com/modelcontextprotocol/conformance)
