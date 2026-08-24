# Advanced L4 agent two-hour soak report

Date: 2026-08-24

## Result

- Status: PASS
- Elapsed time: 7421.938 seconds (2 h 3 min 42 s)
- Cycles: 18/18 PASS
- Long-horizon cycles: 9/9 PASS
- Error-recovery cycles: 9/9 PASS
- Failures: 0
- Pass rate: 100%
- Interval: 300 seconds
- Model/harness: `qwen3.8-27b` / ZCode `0.16.3`
- stderr: empty

## Strict trace evidence

The 18 independent model sessions produced 99 allowed MCP calls:

- `get_status`: 9
- `list_stored_jobs`: 18
- `get_job`: 27
- `check_applied`: 27
- `list_cvs`: 9
- `list_applications`: 9

No live-search, browser, application, submission, sync, push, blocklist mutation,
or file-writing tool was called.

Each long-horizon cycle used seven calls in an exact order. Qwen retained two
dynamic job IDs, fetched them as one batch, checked both application states,
requested CV recommendations for the first job, and inspected application
history. Each error-recovery cycle first requested the fixed missing ID
`arl-missing-job`, observed the structured `unknown` response, found a real local
job, retried `get_job`, and completed `check_applied`.

## Trace boundaries

- First check: `2026-08-24T20:08:35.801524+00:00`
- First session: `sess_ad38606f-6811-4e3e-8efe-8e9953c3f4ae`
- First trace: `.arl/artifacts/3f6a8839-699a-46b4-90ef-b416acc48a3e/qwen-long-horizon-trace.jsonl`
- Last check: `2026-08-24T22:04:34.037136+00:00`
- Last session: `sess_764b979d-034c-488b-84c4-337de08ee618`
- Last trace: `.arl/artifacts/360d71c4-e2cc-4ac6-bf49-240e14f616a5/qwen-error-recovery-trace.jsonl`

SQLite contains 18 matching production checks, all with
`scenario trace assertions passed`.

## Defect found before the clean soak

The first error-recovery control exposed an ARL oracle defect: the oracle looked
for formatted JSON as a substring of an escaped MCP content field. The underlying
Qwen trace was correct. ARL now parses the nested response payload structurally;
the regression test and repeated live control passed. The clean soak then ran
without a failure.

## Final gates

- Ruff: PASS
- Pytest: 45 passed
- Mutation attribution: top-1 1.0, top-3 1.0, false repair rate 0.0
- Doctor: core integrations PASS; Docker L1 remains optional and unavailable
- Runtime Markdown and JSON reports regenerated

