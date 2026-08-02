# 03 — Resume Provider Work Within Cumulative Authorization

**What to build:** Allow one fake-provider-backed synthesis job to resume across
generation-stage interruptions while checkpointing validated task contracts,
classifying ambiguous remote attempts honestly, and enforcing one cumulative
logical-call authorization across the original run and every resume.

**Blocked by:** [02 — Reject Unsafe Job Resumption](02-reject-unsafe-job-resumption.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Async Local Orchestration](../../../docs/product-specs/async-local-orchestration.md)

## Acceptance criteria

- [x] Provider work intent and a stable attempt identity are journaled before a
  remote call can begin.
- [x] A provider response that passes schema and domain validation is
  checkpointed as a normalized task contract, allowing candidate processing to
  resume without repeating generation.
- [x] Interruptions before provider work, after validated-contract checkpoint,
  during candidate processing, and after terminal outcome persistence each
  resume from the earliest incomplete phase without duplicate admission.
- [x] A lost response after provider acceptance becomes an explicit ambiguous
  attempt rather than an exactly-once transport claim.
- [x] Known and ambiguous issued logical calls consume the persisted cumulative
  authorization, and the runner stops before an action could exceed it.
- [x] Bounded transport retries remain owned and reported by the provider
  adapter; orchestration adds no unbounded or speculative retry loop.
- [x] Resume validates the original provider and model aliases without
  persisting credentials, raw prompts, raw response envelopes, grounding rows,
  or provider error bodies.
- [x] Fake-provider interruption, ambiguity, budget-exhaustion, checkpoint,
  redaction, and deterministic artifact tests pass with no paid calls.

## Implementation

Added provider-backed serial generation through an injected fake-compatible
provider seam. Provider intent, stable attempt IDs, issued logical-call
numbers, sanitized usage, ambiguity, and validated task-contract checkpoints
are journaled before candidate admission. Resume reuses checkpointed contracts,
classifies unresolved issued attempts as `ProviderResponseLost`, validates
provider/model aliases and cumulative budget, and never persists credentials,
raw prompts, response envelopes, grounding context, or provider error bodies.
Bounded adapter transport failures are conservative and explicitly ambiguous.
Focused fake-provider and provider-adapter tests cover every interruption
boundary, ambiguity recovery, budget exhaustion, alias drift, redaction, and
deterministic core-artifact equivalence; no paid provider calls are used.

## Scope guard

Do not use a real provider, broaden authorization during resume, claim
exactly-once provider delivery, or add coverage scheduling or concurrency in
this slice.
