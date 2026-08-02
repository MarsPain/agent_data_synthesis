# ISSUE-0001: Async Local Orchestration

- **What to build:** Add an opt-in, repository-local orchestration runner that
  durably journals candidate work, resumes interrupted jobs, preserves stable
  merge and artifact semantics, supports cooperative cancellation and bounded
  concurrency, and reports sanitized per-role provider usage.
- **Blocked by:** None; the runtime activation trigger has been observed.
- **Dependencies:** None; existing candidate-processing and deterministic merge
  seams are implementation-ready.
- **Status:** ready-for-agent
- **Assignee:** Unassigned
- **Parent spec:** [Async Local Orchestration](../docs/product-specs/async-local-orchestration.md)
- **Legacy record:** [Plan 0014](../docs/exec-plans/deferred/0014-async-local-orchestration-with-durable-queues.md)

## Activation Trigger

Start implementation when at least one condition is observed:

- a representative run exceeds roughly 10 minutes or 100 candidates and
  interruption recovery has material value;
- a failed long-running provider campaign makes partial-result recovery a
  concrete cost;
- per-role or per-provider cost attribution becomes an operator requirement.

## Current Disposition

The target-30 representative coverage campaign recorded contacts runtime of
738.273 seconds and mobile-messages runtime of 662.632 seconds, exceeding the
rough ten-minute activation threshold. The scale evidence also emitted the
`async_orchestration` signal. Implementation is now ready to be assigned, but
remains outside coverage campaign ticket 06. Keep the default runner
synchronous until the opt-in orchestration path is implemented and validated.

## Acceptance criteria

- [ ] The default command remains synchronous; async execution requires an
  explicit programmatic or CLI opt-in and defaults to concurrency one.
- [ ] Versioned job, work-item, event-journal, and usage-summary contracts fail
  closed on invalid identities, transitions, schemas, or configuration drift.
- [ ] A resumable serial tracer bullet persists work intent before side effects,
  checkpoints validated generated task contracts, and skips completed work.
- [ ] Coverage-driven jobs reconstruct assignment reconciliation and bounded
  backfill from durable terminal outcomes without changing coverage semantics.
- [ ] Known and ambiguous provider attempts consume one cumulative logical-call
  budget across the original run and every resume; retries remain bounded.
- [ ] Bounded concurrency preserves stable sequence merge, duplicate admission,
  coverage fulfillment, and deterministic core artifact content.
- [ ] Cooperative cancellation stops new work pickup and leaves a valid,
  diagnostic, resumable job without presenting partial output as complete.
- [ ] Existing source, remote-context, sandbox, mutation, role, provider-host,
  verification, quality, and release controls are unchanged and cannot be
  bypassed by async mode.
- [ ] Orchestration artifacts contain no credentials, headers, raw prompts, raw
  provider responses, private source payloads, environment variables, or local
  absolute paths.
- [ ] Deterministic sync-versus-async equivalence, interruption recovery,
  provider ambiguity, cancellation, journal corruption, lock, usage, CLI,
  documentation, and full-suite validation pass.

## Scope guard

Do not add an external broker, distributed workers, a service or dashboard,
multi-process execution, an exactly-once provider claim, unbounded retries, or
automatic async activation. Do not change domain behavior, coverage or release
thresholds, or infer new provider authorization from a resumed job.
