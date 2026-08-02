# 03 — Resume Provider Work Within Cumulative Authorization

**What to build:** Allow one fake-provider-backed synthesis job to resume across
generation-stage interruptions while checkpointing validated task contracts,
classifying ambiguous remote attempts honestly, and enforcing one cumulative
logical-call authorization across the original run and every resume.

**Blocked by:** [02 — Reject Unsafe Job Resumption](02-reject-unsafe-job-resumption.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Async Local Orchestration](../../../docs/product-specs/async-local-orchestration.md)

## Acceptance criteria

- [ ] Provider work intent and a stable attempt identity are journaled before a
  remote call can begin.
- [ ] A provider response that passes schema and domain validation is
  checkpointed as a normalized task contract, allowing candidate processing to
  resume without repeating generation.
- [ ] Interruptions before provider work, after validated-contract checkpoint,
  during candidate processing, and after terminal outcome persistence each
  resume from the earliest incomplete phase without duplicate admission.
- [ ] A lost response after provider acceptance becomes an explicit ambiguous
  attempt rather than an exactly-once transport claim.
- [ ] Known and ambiguous issued logical calls consume the persisted cumulative
  authorization, and the runner stops before an action could exceed it.
- [ ] Bounded transport retries remain owned and reported by the provider
  adapter; orchestration adds no unbounded or speculative retry loop.
- [ ] Resume validates the original provider and model aliases without
  persisting credentials, raw prompts, raw response envelopes, grounding rows,
  or provider error bodies.
- [ ] Fake-provider interruption, ambiguity, budget-exhaustion, checkpoint,
  redaction, and deterministic artifact tests pass with no paid calls.

## Scope guard

Do not use a real provider, broaden authorization during resume, claim
exactly-once provider delivery, or add coverage scheduling or concurrency in
this slice.
