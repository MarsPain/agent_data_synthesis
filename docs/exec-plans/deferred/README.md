# Deferred Plans

Deferred plans have valid design intent but are not currently scheduled for
implementation. They remain here until their trigger conditions are met, then
move back to `../active/` and `../../PLANS.md` is updated.

## Deferred

- [0014-async-local-orchestration-with-durable-queues](0014-async-local-orchestration-with-durable-queues.md)
  - Trigger: single runs exceed ~10 minutes or 100+ candidates, recovery cost
    becomes painful, or per-role/per-provider cost attribution becomes a team
    requirement.
  - Rationale: current fixture-scale runs do not justify async orchestration,
    durable queues, cancellation, and cost tracking complexity.
