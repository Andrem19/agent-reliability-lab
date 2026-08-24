# Architecture decision record

## Goal and invariant

ARL's primary output is experimentally supported attribution to one layer of
`model -> harness -> tool client -> MCP server -> environment`. Repair is permitted
only after attribution and only inside the corresponding repair domain.

The orchestrator, scheduler, hypothesis scoring, experiment ranking, safety policy,
and repair gates are deterministic code. Models evaluate or diagnose bounded evidence;
they do not control the state machine.

## Vertical slices

Each milestone owns a runnable end-to-end slice and an acceptance gate. A failed gate
stops progression. M0 through M7 have executable gates; M7's temporal gate is based on
real elapsed time rather than an accelerated or mocked clock.

## Component boundaries

- `arl.targets`: the external target contract and filesystem registry. V1 validates a
  one-server topology while retaining a list-shaped contract for future composition.
- `arl.storage`: SQLite metadata and append-only JSONL events. All persistence goes
  through redaction. Mutation ground truth has no evidence-facing query method.
- `arl.safety`: recursive redaction, five-source risk classification, side-effect
  firewall in the trace path, and provenance-aware injection handling.
- `arl.runtime`: bounded subprocess execution with explicit timeout classification.
- `arl.repair.worktree`: validated repository-root and worktree-root operations. It
  never writes directly to the target's main worktree.
- `arl.engines`: direct SDK execution, fuzz, chaos, protocol compatibility,
  metamorphic and differential checks.
- `arl.isolation`: scored hypotheses, deterministic experiment planning, and
  counterfactual matrices.
- `arl.providers`: transport-aware fallback and circuit breaking; reasoning failures
  escalate and never silently change the executor model.
- `arl.scenarios`: capability graph, deterministic synthesis lint and coverage selector.
- `arl.diagnosis`: persistent patterns retrieved only after independent diagnosis.
- `arl.orchestrator`: bounded or time-based soak loop with atomic checkpoints.
- `arl.doctor`: evidence-based capability discovery; missing optional production
  runtime reports WARN, while broken core storage/contracts report FAIL.

There is no provider, harness, engine, or environment abstraction in M0 because those
interfaces do not yet have two concrete callers. They are introduced in their first
vertical slices (M1/M4/M5), using the actual discovered CLI/protocol contracts.

## Safety invariants

1. Default execution mode is SAFE_LIVE.
2. Black/gray-box targets cannot enable repair.
3. Event payloads are redacted before both SQLite and JSONL writes.
4. Every process has a positive timeout and a distinct timed-out result.
5. Worktree creation validates the exact Git root and a single configured child path.
6. Production Qwen unavailability is `test_infra_unavailable`, not a fallback trigger.
7. Mutation ground truth is stored separately and cannot enter diagnostic evidence.

## Acceptance status

M0–M6 are accepted by automated and real vertical tests. M4 additionally passed real
ZCode/Qwen and native Z.ai GLM-5.3 Job Search MCP workflows with proxy trace evidence.
The repair path has also diagnosed, patched, replayed, regression-tested, and staged a
real Google Drive OAuth defect without modifying the target's `main` branch. M7 passed
a literal 7243-second Job Search MCP soak with 24/24 successful cycles and no failures.
