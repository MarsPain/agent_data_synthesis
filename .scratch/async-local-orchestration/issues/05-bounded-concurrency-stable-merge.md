# 05 — Run Bounded Work Concurrently With Stable Merge

**What to build:** Allow independent durable work items to execute with an
operator-selected positive concurrency bound while preserving candidate-local
isolation, cumulative provider limits, stable sequence merge, duplicate
admission, coverage reconciliation, and deterministic core artifacts.

**Blocked by:** [04 — Resume Coverage Assignments and Bounded Backfill](04-coverage-resumption-and-backfill.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Async Local Orchestration](../../../docs/product-specs/async-local-orchestration.md)

## Acceptance criteria

- [x] Async execution defaults to concurrency one and rejects zero, negative,
  non-integer, or implementation-unsafe concurrency values before work begins.
- [x] A configured bound limits simultaneous work pickup and remote-attempt
  reservation without permitting the cumulative authorization to overshoot.
- [x] Concurrent work preserves candidate-local environment rebuild,
  checkpoint, tool-registry, adapter, mutation, execution, and verification
  isolation.
- [x] A deterministic test forces provisional outcomes to finish in reverse
  order and proves that merge still follows stable sequence index.
- [x] Exact-duplicate admission chooses the same winner as serial execution,
  and review, proposal, episode, rejection, and coverage ordering remain stable.
- [x] Serial and concurrent fake-provider coverage jobs produce equivalent core
  artifacts for identical inputs; only orchestration timing and usage ordering
  may differ.
- [x] Interrupted concurrent work resumes without duplicating completed items
  or exceeding the original concurrency and budget bounds.
- [x] Focused bound, isolation, reverse-completion, duplicate, coverage,
  interruption, and equivalence tests pass without paid calls.

## Implementation

`run_serial_job` now accepts a validated positive `max_concurrency` bound,
defaults omitted values to one worker, and persists the selected bound as part
of the job configuration. Candidate
work and independent coverage-assignment provider calls use bounded local
executors while the existing stable sequence merge remains the sole assembler
for core artifacts. Durable journal mutation and provider-attempt reservation
are serialized so cumulative authorization cannot overshoot under overlap;
resumption reuses the original bound and skips completed work. Focused
orchestration tests cover bounds, reverse completion, candidate isolation,
duplicate admission, coverage equivalence, provider interruption, and
serial/concurrent artifact parity.

## Scope guard

Do not add multi-process or distributed workers, speculative duplicate work,
automatic concurrency tuning, or an external queue or semaphore service.
