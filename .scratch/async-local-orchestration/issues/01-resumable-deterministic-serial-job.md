# 01 — Run and Resume a Deterministic Serial Job

**What to build:** Provide an opt-in programmatic job runner that processes a
deterministic candidate set serially through the existing synthesis pipeline,
records durable progress, and resumes after an injected interruption without
reprocessing completed work or changing core dataset results.

**Blocked by:** None — can start immediately.

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Async Local Orchestration](../../../docs/product-specs/async-local-orchestration.md)

## Acceptance criteria

- [x] A synthesis operator can create a stable local job from a validated
  deterministic run configuration and receive an explicit terminal job result.
- [x] Versioned job, work-item, and event records represent the minimum valid
  pending, running, and completed lifecycle for serial execution.
- [x] Work intent is durably recorded before candidate processing begins, and a
  completed work item records whether processing produced an accepted sample or
  a rejection.
- [x] A deterministic interruption between work items leaves valid resumable
  state; resumption skips completed work and admits no candidate twice.
- [x] The resumed run uses the existing candidate-processing, stable merge, and
  dataset-assembly interfaces rather than reimplementing their behavior.
- [x] For identical deterministic input, the completed serial job produces the
  same ordered core dataset artifacts and coverage-independent quality result
  as the synchronous path.
- [x] Orchestration-owned state remains separate from core dataset artifacts,
  and the default synchronous programmatic path is unchanged.
- [x] Focused contract, interruption, equivalence, and default-path regression
  tests pass without provider access.

## Implementation

Implemented `synthesis.orchestration.run_serial_job` with versioned local job,
work-item, and integrity-chained event records under the output directory.
Serial resumption reuses persisted candidate intent and completed provisional
outcomes through the existing pipeline callbacks and stable merge boundary.
The job also binds effective policy, source, environment, metadata, and output
mode inputs before allowing resume; journal recovery tolerates only an
unterminated final JSON append and rejects malformed events and sensitive state.
Focused tests live in `tests/test_orchestration.py`; provider access is not
required.

## Scope guard

Keep this first slice serial and programmatic. Do not add provider resumption,
coverage backfill recovery, concurrency, cancellation, CLI flags, external
queues, or new domain behavior.
