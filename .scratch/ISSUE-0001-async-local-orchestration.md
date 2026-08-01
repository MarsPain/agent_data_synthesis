# ISSUE-0001: Async Local Orchestration

- **Status:** ready-for-agent
- **Assignee:** Unassigned
- **Parent spec:** [Async Local Orchestration](../docs/product-specs/async-local-orchestration.md)
- **Dependencies:** None; the runtime activation trigger has been observed.
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
