# L7 Browser Agent soak — 2026-08-25

## Result

The clean L7 acceptance soak completed in 7282.141 seconds with 47/47 PASS,
zero failures and a 100% PASS rate. It used the tuned local
`qwen3.8-27b` llama.cpp Vision runtime for agent cycles; LM Studio, GLM and
DeepSeek were not used.

| Kind | Scenario | PASS |
|---|---|---:|
| Direct | Happy path | 6 |
| Direct | Stale-DOM recovery | 12 |
| Direct | Expired-session recovery | 6 |
| Direct | CAPTCHA safe-stop | 6 |
| Qwen → ZCode agent | Happy path | 6 |
| Qwen → ZCode agent | Expired-session recovery | 6 |
| Qwen → ZCode agent | CAPTCHA safe-stop | 5 |
| **Total** |  | **47** |

## Evidence audit

- 47/47 local job-site environment oracles passed.
- 47/47 artifact directories contain a non-empty Playwright trace and an MCP
  JSONL trace; screenshot artifacts are present for every run.
- Each cycle used a fresh exact `http://127.0.0.1:<port>` origin. All 47
  navigation origins were loopback-only and unique.
- Actual MCP calls were limited to the approved browser tool set. There were no
  `browser_eval`, external navigation, real-site, login, sync, CV push or
  production application calls.
- CAPTCHA scenarios produced zero submissions. Happy and session scenarios were
  accepted only when the independent site oracle matched the complete candidate
  payload and uploaded-file metadata.

The clean-run files are `.arl/l7-browser-soak.json`,
`.arl/l7-browser-soak.stdout.log` and `.arl/l7-browser-soak.stderr.log`.
The rejected pre-fix run remains preserved with the
`.failed-20260825-1648` suffix and is not counted above.

## Defects found and repaired

1. The first agent integration invoked ZCode in planning mode, so the model could
   describe browser actions but could not execute them. L7 now uses the real
   execution path with an isolated project-level tool allowlist.
2. ZCode 0.16.5 advertised CLI flags that its bundled runtime rejected. ARL moved
   those controls into the isolated project configuration and retained a bounded
   outer deadline.
3. The Work Researcher modal tagger reused element numbers from controls behind
   the active dialog. The target now clears the background numbering namespace;
   its regression is staged on `autotune/staging` at `0f7d555`.
4. The first timed CAPTCHA run accumulated redundant snapshots and eventually hit
   ZCode's headers timeout. ARL now tells the agent to chain fresh snapshots
   returned by browser actions, use `browser_form` once, and request
   `modal_only=true` only after entering the wizard. The minimal runtime network
   deadline was raised to 600 seconds. The bounded replay and clean soak passed.

## Final verification

- Ruff: PASS.
- Pytest: 54 passed.
- Five-case mutation suite: top-1 1.0, top-3 1.0, false repair rate 0.0.
- Doctor: all required integrations PASS; the optional Docker L1 sandbox is not
  installed, while the enforced subprocess L0 sandbox is available.
- Runtime report regenerated successfully.

L7 therefore proves the isolated browser-execution loop, including model-driven
action selection, DOM changes, session recovery and safe human-challenge stop.
It does not authorize or claim real-job-board submission; real-site shadow mode
remains a separate safety gate.
