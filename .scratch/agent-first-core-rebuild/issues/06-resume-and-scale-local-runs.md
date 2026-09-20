# 06 — Resume and Scale Local Synthesis Runs

**What to build:** Extend the serial ledger and provider accounting into
bounded concurrent run/cancel/resume operations with stable outputs, frozen
inputs, and budgets that survive repeated interruption.

**Blocked by:** [02 — Run provider-neutral multi-turn Agent Episodes](02-run-provider-neutral-agent-episodes.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [x] SQLite records slot allocation, compiled Task cases, in-flight ownership, terminal outcomes, request reservations/results, usage, and stable sequence; terminal Candidate outcomes commit transactionally.
- [x] One run directory admits one active writer through a process-lifetime lock; a crashed process leaves it resumable without a persisted lock-recovery schema.
- [x] Concurrency defaults to four, validates one through sixteen, and stays bounded. Cancellation stops new dispatch, saves completed outcomes, and emits an honest partial status.
- [x] Resume verifies configuration, Domain version, and frozen input fingerprint before calls; changing the original source path's content cannot change resumed state, while a missing/corrupt snapshot fails closed.
- [x] Persisted Task cases and identities survive resume. Terminal Episodes are skipped; incomplete Episodes restart in original initial state without re-inventing the task.
- [x] Every physical request, including all roles, repair, retry, and Episode restart, consumes a durable reservation before dispatch. Unknown outcomes remain charged; repeated resumes never reset counters or report unknown tokens as zero.
- [x] Insufficient remaining budget stops work with a bounded partial-result reason. Reports distinguish task attempts, physical requests, retries, known usage, and unknown usage.
- [x] Failed generation/compilation and duplicate slots remain charged to the attempt ceiling; replayed in-flight slot work consumes remaining request budget without allocating a new task identity.
- [x] Reverse completion order preserves stable export and deterministic duplicate winners; accepted and attempt targets remain explicit and bounded.
- [x] Known impossible unique-task targets fail before paid work. Domain slot exhaustion, already-admitted semantic keys, bounded replacement, and unknown capacity produce distinct honest outcomes without unbounded duplicate generation.
- [x] Library and thin CLI resume produce equivalent terminal results and artifacts.
- [x] Failure injection covers before/after Task-case persistence, request dispatch, response persistence, and terminal commits, including multiple consecutive crashes and cancellation with in-flight work.
- [x] A manual ten-thousand-attempt fake-model benchmark declares enough unique task capacity, streams export, stays below 512 MiB peak memory, and resumes without repeated terminal Episodes. Report attempts and unique accepted count separately from any production-Domain capacity claim.

## Delivery evidence

- Focused engine, recovery, concurrency, CLI, and benchmark coverage lives in
  `tests/test_agent_first_resume_scale.py`; the repository suite and documentation
  validation pass.
- The provider-free final scale probe ran 10,000 unique test-Domain attempts:
  10,000 accepted terminal Episodes, 11,250 physical fake-model requests, zero
  provider calls during terminal resume, 19.889 seconds elapsed, and 76.86 MiB
  peak memory. Its capacity and quality claim is explicitly limited to the test
  Domain and fake model.

## Scope guard

Do not introduce distributed workers, brokers, service endpoints, append-only
journals, nested orchestration schemas, or exactly-once claims for remote
requests. Engine scale evidence does not establish production task diversity or
real-model quality. This ticket can use test Domains without waiting for the
production adapter tickets.
