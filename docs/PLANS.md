# Plans

## Lifecycle States

- `active`: work currently intended for implementation.
- `completed`: accepted plans with completion date.
- `tech-debt`: known unresolved debt with impact and target stage.

## Active

- No active execution plan.

## Completed

- [0001-foundation](exec-plans/completed/0001-foundation.md): established the local executable framework foundation. Completed on 2026-05-16.
- [0002-data-contracts-and-quality-gates](exec-plans/completed/0002-data-contracts-and-quality-gates.md): enforced dataset contracts and quality gates over the local foundation runner. Completed on 2026-05-16.
- [0003-quality-reporting-and-curriculum-foundation](exec-plans/completed/0003-quality-reporting-and-curriculum-foundation.md): added quality reports, metric slicing, duplicate gates, logical gates, parent comparison, and first-pass curriculum metadata. Completed on 2026-05-16.
- [0004-remote-llm-generation-lineage-and-retry-loop](exec-plans/completed/0004-remote-llm-generation-lineage-and-retry-loop.md): propagated remote LLM lineage, added bounded provider retries, classified generation-stage failures, and preserved inspectable artifacts. Completed on 2026-05-16.
- [0005-solution-policy-and-multi-step-stateful-trajectories](exec-plans/completed/0005-solution-policy-and-multi-step-stateful-trajectories.md): separated task generation from solution-policy execution and added a multi-step stateful trajectory foundation. Completed on 2026-05-16.
- [0006-critic-refinement-and-regeneration-loop](exec-plans/completed/0006-critic-refinement-and-regeneration-loop.md): added a bounded critic/refinement loop with one repaired rerun, refinement lineage, and refined outcome metrics. Completed on 2026-05-16.
- [0007-role-contracts-and-generator-orchestration](exec-plans/completed/0007-role-contracts-and-generator-orchestration.md): formalized role contracts, registry-backed LLM routing, role lineage, disabled future-role guardrails, and role-level quality visibility. Completed on 2026-05-16.

## Technical Debt

- Current debt bucket: [exec-plans/tech-debt/README.md](exec-plans/tech-debt/README.md).
