# 04 — Resume Coverage Assignments and Bounded Backfill

**What to build:** Make a coverage-driven fake-provider job recover its stable
assignments and accepted-only reconciliation from durable terminal outcomes, so
that interruption during an initial wave or bounded deficit backfill resumes to
the same fulfilled or bounded-underfilled result as synchronous execution.

**Blocked by:** [03 — Resume Provider Work Within Cumulative Authorization](03-provider-resumption-and-budget.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Async Local Orchestration](../../../docs/product-specs/async-local-orchestration.md)

## Acceptance criteria

- [x] Each durable coverage work item retains locally issued assignment,
  sequence, plan, cell, and grounding-scope identity without accepting
  provider-asserted fulfillment.
- [x] Resume reconstructs planned, in-flight, accepted, rejected, and remaining
  counts from durable outcomes before issuing another assignment.
- [x] Only accepted and locally validated assignments reduce a deficit after
  resume; rejected and interrupted attempts remain visible and bounded.
- [x] Interruption during the initial assignment wave resumes without issuing a
  duplicate assignment or changing stable ordering.
- [x] Interruption during deficit backfill resumes under the original attempt
  ceiling and cumulative provider authorization.
- [x] Fulfilled and bounded-underfilled fake-provider cases produce the same
  reconciliation, samples, rejections, and coverage evidence as their
  synchronous equivalents.
- [x] Partial coverage output remains diagnostic and cannot satisfy fulfillment
  or release gates until the job completes normally.
- [x] Focused initial-wave, rejection, backfill, attempt-exhaustion, resume, and
  equivalence tests pass without paid calls.

## Implementation

Coverage-enabled serial jobs now journal each locally issued assignment and
wave before provider work, checkpoint validated contracts, record generation
rejections as terminal outcomes, and replay the scheduler from durable
assignment state. Resume reuses checkpointed candidates, retries only
unresolved assignments under the original provider budget, and reconciles
accepted/rejected outcomes through the existing coverage scheduler. The
pipeline uses stable assignment sequence indexes so fulfilled and bounded-
underfilled async artifacts match synchronous fake-provider runs.

## Scope guard

Do not change coverage catalogs, profiles, assignment selection, fulfillment
semantics, attempt ratios, grounding reuse, or provider authorization limits.
