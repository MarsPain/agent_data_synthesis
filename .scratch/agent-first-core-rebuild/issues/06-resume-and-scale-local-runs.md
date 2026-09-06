# 06 — Resume and Scale Local Synthesis Runs

**What to build:** Let a synthesis operator run, cancel, and resume thousands of
independent Agent Episodes on one machine with bounded concurrency, stable
outputs, explicit provider ceilings, and no duplicate completed work.

**Blocked by:** [02 — Run provider-neutral multi-turn Agent Episodes](02-run-provider-neutral-agent-episodes.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [ ] The SQLite ledger records Task-slot disposition, in-flight ownership, terminal Episode outcome, provider usage, and stable sequence in transactional state.
- [ ] One run directory permits one active writer, while a crashed process leaves the run resumable without a persisted lock-recovery protocol.
- [ ] Candidate concurrency defaults to four, validates the supported one-through-sixteen range, and never exceeds the configured bound.
- [ ] Cooperative cancellation stops new work, commits completed outcomes, marks incomplete work resumable, and emits an honest non-complete run status.
- [ ] Resume rejects run-configuration or Domain-version drift before a provider call, skips committed terminal Episodes, and restarts incomplete Episodes from fresh Domain state.
- [ ] Out-of-order completion exports demonstrations and negatives in stable sequence and selects duplicate winners deterministically.
- [ ] Explicit accepted and attempt targets, rollout limits, transport retries, and observed model calls provide a finite provider-call ceiling and stop further work when exhausted.
- [ ] Library and thin CLI resume operations produce the same terminal result and artifact set.
- [ ] Failure-injection tests cover interruption before and after terminal commits, cancellation with in-flight work, reverse completion order, and configuration drift.
- [ ] A manual ten-thousand-attempt fake-model benchmark uses streaming processing, stays below 512 MiB peak memory, and resumes without repeating completed Episodes.

## Scope guard

Do not introduce distributed workers, an external broker, a service endpoint,
an append-only hash journal, nested orchestration schemas, or multi-machine
coordination. This is bounded single-process execution on one machine.
