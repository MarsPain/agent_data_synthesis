# ISSUE-0001: Async Local Orchestration

- **Status:** Deferred
- **Assignee:** Unassigned
- **Parent spec:** [Async Local Orchestration](../docs/product-specs/async-local-orchestration.md)
- **Dependencies:** None currently blocking design; implementation depends on an
  observed activation trigger.
- **Legacy record:** [Plan 0014](../docs/exec-plans/deferred/0014-async-local-orchestration-with-durable-queues.md)

## Activation Trigger

Start implementation when at least one condition is observed:

- a representative run exceeds roughly 10 minutes or 100 candidates and
  interruption recovery has material value;
- a failed long-running provider campaign makes partial-result recovery a
  concrete cost;
- per-role or per-provider cost attribution becomes an operator requirement.

## Current Disposition

Keep the default runner synchronous and preserve the candidate-processing seam.
The repository has not recorded evidence that the additional queue, resumption,
cancellation, and concurrency complexity is warranted yet.
