# Documentation Index

`docs/` is the source of truth for the Agent Data Synthesis framework.

## Core Docs

- [DESIGN.md](DESIGN.md): system principles, bounded contexts, and contracts.
- [BACKEND.md](BACKEND.md): backend service boundaries and execution model.
- [DATA.md](DATA.md): canonical data schemas, lineage, and dataset outputs.
- [SECURITY.md](SECURITY.md): sandboxing, trust boundaries, secrets, and external integrations.
- [PRODUCT_SENSE.md](PRODUCT_SENSE.md): users, value model, success metrics, and non-goals.
- [ROADMAP.md](ROADMAP.md): staged development direction.
- [PLANS.md](PLANS.md): execution plan index and lifecycle state.

## Deep Design

- [design-docs/agent-data-synthesis-framework.md](design-docs/agent-data-synthesis-framework.md): full framework architecture.
- [design-docs/algorithm-flow-and-architecture.md](design-docs/algorithm-flow-and-architecture.md): explanatory walkthrough of the current algorithm flow, architecture layers, gates, and dataset artifacts.
- [design-docs/architecture-explainers.md](design-docs/architecture-explainers.md): detailed explanations of architecture and algorithm concepts such as the AWM environment model.
- [design-docs/representative-scale-and-downstream-evidence.md](design-docs/representative-scale-and-downstream-evidence.md): approved evidence boundary for representative three-domain runs and external downstream benchmark result exchange.
- [design-docs/domain-aware-representative-generation.md](design-docs/domain-aware-representative-generation.md): approved domain-owned generation-spec and representative-eligibility boundary for Plan 0043.

## Product Specs

- [product-specs/framework-mvp.md](product-specs/framework-mvp.md): MVP scope and acceptance criteria.

## References

- [references/agent-data-synthesis-pdf-analysis.md](references/agent-data-synthesis-pdf-analysis.md): structured analysis of `Agent-数据合成.pdf`.

## Generated Artifacts

- [generated/README.md](generated/README.md): index for future generated schemas, diagrams, reports, and benchmark outputs.
- [generated/awm-runtime-extraction-readiness.md](generated/awm-runtime-extraction-readiness.md): Phase E extraction readiness decision for the internal AWM runtime kernel.

## Execution Plans

- [PLANS.md](PLANS.md): canonical execution-plan lifecycle and current state.
- [exec-plans/active/README.md](exec-plans/active/README.md): active plan bucket.
- [exec-plans/completed/README.md](exec-plans/completed/README.md): complete accepted-plan history.
- [exec-plans/completed/0043-domain-aware-representative-generation-and-campaign-readiness.md](exec-plans/completed/0043-domain-aware-representative-generation-and-campaign-readiness.md): latest completed plan for bounded three-domain LLM task-contract generation and representative campaign readiness.
- [exec-plans/deferred/README.md](exec-plans/deferred/README.md): deferred plans and activation triggers.
- [exec-plans/indexes/README.md](exec-plans/indexes/README.md): historical plan indexes and decision records.
- [exec-plans/tech-debt/README.md](exec-plans/tech-debt/README.md): technical debt bucket.
