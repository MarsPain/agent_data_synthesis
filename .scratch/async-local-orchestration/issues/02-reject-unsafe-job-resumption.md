# 02 — Reject Unsafe Job Resumption

**What to build:** Make local job resumption fail closed when durable state is
owned by another writer, belongs to a different run configuration, or contains
unsafe lifecycle or journal corruption, while recovering one crash-truncated
final append without executing candidate or provider work prematurely.

**Blocked by:** [01 — Run and Resume a Deterministic Serial Job](01-resumable-deterministic-serial-job.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Async Local Orchestration](../../../docs/product-specs/async-local-orchestration.md)

## Acceptance criteria

- [x] A normalized configuration identity binds the job to its run profile,
  domain, generation settings, enabled features, and declared authorization
  limits without retaining credentials or raw paths.
- [x] Resumption rejects job, configuration, or output-ownership mismatch before
  candidate processing or provider construction.
- [x] Invalid job/work-item transitions, unsupported schema versions, duplicate
  or reordered events, and integrity-invalid mid-journal records fail closed.
- [x] Reload can discard one incomplete final append, records that recovery,
  and reconstructs the same last valid state.
- [x] An exclusive local job lock prevents simultaneous writers without
  modifying job state when acquisition fails.
- [x] Stale-lock recovery is explicit, validates durable state first, and cannot
  silently take ownership from a live writer.
- [x] The hardened runner still completes and resumes the deterministic serial
  tracer bullet from ticket 01 with equivalent core artifacts.
- [x] Focused corruption, lock, configuration-drift, transition, and regression
  tests pass without provider access.

## Implementation

Added normalized configuration and authorization-limit identity fields, a
hash-bound output owner, POSIX-exclusive local locking with explicit stale-lock
recovery, snapshot-to-journal validation, strict lifecycle and event-payload
validation, and bounded final-append recovery. Resume validates durable state,
identity, output ownership, and execution inputs before candidate processing.
Focused tests cover copied output state, snapshot corruption, live and stale
locks, redaction, lifecycle shape, interruption recovery, and ticket-01
artifact equivalence; the full 795-test suite passes without provider access.

## Scope guard

Do not introduce distributed locking, a database, multi-process workers,
provider calls, or automatic deletion or repair of integrity-invalid history.
