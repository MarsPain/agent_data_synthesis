# Plans

## Lifecycle States

- `active`: work currently intended for implementation.
- `completed`: accepted plans with completion date.
- `tech-debt`: known unresolved debt with impact and target stage.
- `deferred`: planned but postponed until a concrete trigger condition is met.

## Active

No plans currently active.

## Deferred

- [0014-async-local-orchestration-with-durable-queues](exec-plans/active/0014-async-local-orchestration-with-durable-queues.md):
  async job lifecycle, durable file-backed queues, manifest-based resumption,
  concurrency limits, cancellation, and per-role cost tracking; **deferred**
  until single runs exceed ~10 minutes or 100+ candidates. See the plan's
  "补充思考" section for the full deferral rationale.

## Completed

- [0001-foundation](exec-plans/completed/0001-foundation.md): established the local executable framework foundation. Completed on 2026-05-16.
- [0002-data-contracts-and-quality-gates](exec-plans/completed/0002-data-contracts-and-quality-gates.md): enforced dataset contracts and quality gates over the local foundation runner. Completed on 2026-05-16.
- [0003-quality-reporting-and-curriculum-foundation](exec-plans/completed/0003-quality-reporting-and-curriculum-foundation.md): added quality reports, metric slicing, duplicate gates, logical gates, parent comparison, and first-pass curriculum metadata. Completed on 2026-05-16.
- [0004-remote-llm-generation-lineage-and-retry-loop](exec-plans/completed/0004-remote-llm-generation-lineage-and-retry-loop.md): propagated remote LLM lineage, added bounded provider retries, classified generation-stage failures, and preserved inspectable artifacts. Completed on 2026-05-16.
- [0005-solution-policy-and-multi-step-stateful-trajectories](exec-plans/completed/0005-solution-policy-and-multi-step-stateful-trajectories.md): separated task generation from solution-policy execution and added a multi-step stateful trajectory foundation. Completed on 2026-05-16.
- [0006-critic-refinement-and-regeneration-loop](exec-plans/completed/0006-critic-refinement-and-regeneration-loop.md): added a bounded critic/refinement loop with one repaired rerun, refinement lineage, and refined outcome metrics. Completed on 2026-05-16.
- [0007-role-contracts-and-generator-orchestration](exec-plans/completed/0007-role-contracts-and-generator-orchestration.md): formalized role contracts, registry-backed LLM routing, role lineage, disabled future-role guardrails, and role-level quality visibility. Completed on 2026-05-16.
- [0008-failure-driven-tool-expansion-and-capability-gap-routing](exec-plans/completed/0008-failure-driven-tool-expansion-and-capability-gap-routing.md): added capability-gap diagnostics, bounded tool proposals, curated local tool admission, proposal artifacts, and tool-expansion quality reporting. Completed on 2026-05-17.
- [0009-multi-path-branching-trajectory-foundation](exec-plans/completed/0009-multi-path-branching-trajectory-foundation.md): added bounded branch plans, checkpointed local branch execution, selected-branch lineage, and branch-level quality reporting. Completed on 2026-05-17.
- [0010-agentinstruct-seed-transformation-and-editor-loop](exec-plans/completed/0010-agentinstruct-seed-transformation-and-editor-loop.md): added seed transformation, taxonomy-driven task expansion, enabled task suggester/editor roles, expansion lineage, and reporting slices. Completed on 2026-05-17.
- [0011-provenance-licensing-and-sandbox-gates](exec-plans/completed/0011-provenance-licensing-and-sandbox-gates.md): added source provenance, license eligibility, default-deny network policy, sandbox policy, source-event audit artifacts, and source-governance quality slices. Completed on 2026-05-17.
- [0012-controlled-network-backed-environment-synthesis](exec-plans/completed/0012-controlled-network-backed-environment-synthesis.md): added controlled opt-in HTTPS source ingestion, allowlisted host enforcement, request budgets, payload limits, contacts environment-source admission, and sanitized fetch/admission audit events. Completed on 2026-05-17.
- [0013-mcp-compatible-environment-tool-adapters](exec-plans/completed/0013-mcp-compatible-environment-tool-adapters.md): added local MCP-compatible adapter manifest, tool-call request/result envelopes, adapter lineage, quality slices, and in-process contacts shim. Completed on 2026-05-18.

## Technical Debt

- Current debt bucket: [exec-plans/tech-debt/README.md](exec-plans/tech-debt/README.md).
