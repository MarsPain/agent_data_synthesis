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
- [0025-awm-runtime-boundary-and-shared-environment-kernel](0025-awm-runtime-boundary-and-shared-environment-kernel.md)
  - Trigger: reward-model-driven data quality evaluation, Agentic RL rollout
    execution, a second domain environment, or external MCP environment servers
    need to consume the same environment runtime contract.
  - Rationale: the AWM environment runtime should become shared infrastructure,
    but only after its contract is validated by multiple consumers.
