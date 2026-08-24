# L3 schema-fuzz two-hour soak report

Date: 2026-08-24

## Result

- Status: PASS
- Elapsed time: 7225.844 seconds
- Cycles: 24
- Assertions per cycle: 19
- Assertions passed: 456/456
- Failed cycles: 0
- Pass rate: 100%
- Interval: 300 seconds
- stderr: empty

## Coverage and safety

Each cycle exercised valid, missing, malformed, boundary, and unknown arguments
against the live Job Search MCP schemas. The allowed tool surface was restricted to
`get_status`, `list_stored_jobs`, `get_job`, and `check_applied`. No model was used
at L3, and no application, submission, browser, sync, push, or write action was
permitted.

## Trace boundaries

- First trace: `.arl/artifacts/babb174d-26d8-411e-94cd-61638d168d5f/l3-schema-fuzz-trace.jsonl`
- Last trace: `.arl/artifacts/85be8f4f-25ac-4c1c-a8af-ca74ae396c6d/l3-schema-fuzz-trace.jsonl`

## Final gates

- Ruff: PASS
- Pytest: 43 passed
- Mutation attribution: top-1 1.0, top-3 1.0, false repair rate 0.0
- Doctor: core integrations PASS; Docker L1 remains optional and unavailable

