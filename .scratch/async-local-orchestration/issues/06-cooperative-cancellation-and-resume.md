# 06 — Cancel and Resume a Live Synthesis Job

**What to build:** Let a synthesis operator cooperatively cancel a running
serial or concurrent job, stop new work pickup, record the disposition of
in-flight work, retain valid diagnostic progress, and later resume under the
same configuration and authorization.

**Blocked by:** [05 — Run Bounded Work Concurrently With Stable Merge](05-bounded-concurrency-stable-merge.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Async Local Orchestration](../../../docs/product-specs/async-local-orchestration.md)

## Acceptance criteria

- [x] A programmatic cancellation signal transitions a running job through
  cancelling to cancelled and is idempotent when repeated.
- [x] Cancellation prevents new work pickup while allowing bounded in-flight
  work to finish, reach its existing timeout, or remain explicitly interrupted.
- [x] Every completed, failed, cancelled, or interrupted work item has a valid
  durable disposition after cancellation.
- [x] Partial dataset artifacts, when emitted, are rebuilt through the existing
  writer, remain diagnostic and incomplete, and cannot pass fulfillment or
  release gates.
- [x] A cancelled job resumes only after job identity, configuration, journal,
  lock, output ownership, and remaining authorization validate.
- [x] Resumption skips work that completed before or during cancellation and
  requeues only eligible interrupted work.
- [x] Serial and concurrent cancellation/resumption produce the same final core
  artifacts as uninterrupted execution for deterministic inputs.
- [x] Focused repeated-cancel, no-new-pickup, in-flight, partial-artifact,
  authorization, resume, and equivalence tests pass without paid calls.

## Implementation

`run_serial_job` now accepts a thread-safe cooperative cancellation signal and
durably records `job_cancelling`, interrupted work-item dispositions, and
`job_cancelled`. Bounded candidate and coverage executors stop submitting new
work, drain already-started work, and preserve stable merge order. Partial
outputs use the existing dataset writer with an explicit incomplete
orchestration marker; release admission rejects that marker. Cancelled jobs
validate the existing identity, configuration, lock, journal, output, and
authorization bindings before resuming completed outcomes and eligible pending
work.

Focused coverage, repeated-cancel, no-new-pickup, pre-bind resume, partial
artifact, release-gate, and serial/concurrent equivalence tests are in
`tests/test_orchestration.py` and `tests/test_dataset_release.py`.

## Scope guard

Do not add forceful thread termination, remote cancellation endpoints,
unbounded shutdown waits, process supervisors, or automatic resumption.
