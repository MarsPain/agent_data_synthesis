# 02 — Reject Unsafe Job Resumption

**What to build:** Make local job resumption fail closed when durable state is
owned by another writer, belongs to a different run configuration, or contains
unsafe lifecycle or journal corruption, while recovering one crash-truncated
final append without executing candidate or provider work prematurely.

**Blocked by:** [01 — Run and Resume a Deterministic Serial Job](01-resumable-deterministic-serial-job.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Async Local Orchestration](../../../docs/product-specs/async-local-orchestration.md)

## Acceptance criteria

- [ ] A normalized configuration identity binds the job to its run profile,
  domain, generation settings, enabled features, and declared authorization
  limits without retaining credentials or raw paths.
- [ ] Resumption rejects job, configuration, or output-ownership mismatch before
  candidate processing or provider construction.
- [ ] Invalid job/work-item transitions, unsupported schema versions, duplicate
  or reordered events, and integrity-invalid mid-journal records fail closed.
- [ ] Reload can discard one incomplete final append, records that recovery,
  and reconstructs the same last valid state.
- [ ] An exclusive local job lock prevents simultaneous writers without
  modifying job state when acquisition fails.
- [ ] Stale-lock recovery is explicit, validates durable state first, and cannot
  silently take ownership from a live writer.
- [ ] The hardened runner still completes and resumes the deterministic serial
  tracer bullet from ticket 01 with equivalent core artifacts.
- [ ] Focused corruption, lock, configuration-drift, transition, and regression
  tests pass without provider access.

## Scope guard

Do not introduce distributed locking, a database, multi-process workers,
provider calls, or automatic deletion or repair of integrity-invalid history.
