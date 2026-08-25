# L6 chaos/recovery soak — 2026-08-25

## Result

The clean two-hour L6 run completed after 7504.703 seconds with 24/24 cycles
PASS and zero failures. It exercised 21 proxy-injected faults and three local
Qwen/ZCode error-recovery controls against the real Work Researcher MCP.

| Control | PASS |
|---|---:|
| Latency/timeout | 3/3 |
| Connection drop/EOF | 3/3 |
| Malformed JSON-RPC | 3/3 |
| MCP error code | 3/3 |
| Server kill/restart | 3/3 |
| Partial result | 3/3 |
| Bounded huge result | 3/3 |
| Local Qwen error recovery | 3/3 |

All 21 direct fault cycles had a unique injection ID and proxy evidence. After
the injected failure was removed, every cycle started a clean MCP process and
successfully repeated `get_status` (`recovery=True`). The three Qwen traces made
12 allowed read-only calls: six `get_job`, three `list_stored_jobs`, and three
`check_applied`. No application, submit, browser, sync, push, or write tool was
called.

The malformed JSON-RPC controls intentionally produce SDK validation messages on
stderr. Those messages are expected evidence of client rejection, not soak
failures.

## Findings and repairs

L6 found three ARL defects and no confirmed Work Researcher MCP defect:

1. The partial-result oracle expected only an empty successful object, while the
   MCP SDK correctly rejected the invalid result schema. The oracle now accepts
   that rejection as the expected fault observation.
2. The original latency deadline could expire before the proxy actually injected
   its delay. The delay/deadline window now requires proxy-confirmed injection;
   three consecutive controls and the clean soak passed.
3. A response/process race could write two `injected` records for one
   connection-drop or server-kill ID. The fault and recovery were valid and every
   run had a unique ID, but the duplicate trace record was noisy. The proxy now
   records the event once; unit tests and fresh live connection-drop/server-kill
   controls pass with clean recovery.

## Final gates

- Ruff: PASS.
- pytest: 49/49 PASS.
- Mutation suite: top-1 1.0, top-3 1.0, false repair rate 0.0.
- Doctor core checks: PASS. Docker L1 remains an optional warning; the enforced
  subprocess L0 sandbox is available.
- Runtime report regenerated at `reports/runtime/report.md` and `report.json`.

The evidence supports reliable read-only operation and recovery for the tested
fault classes. It does not authorize or claim testing of application submission
or other irreversible tools.
