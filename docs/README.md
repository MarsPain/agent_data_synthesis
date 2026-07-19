# Documentation Index

`docs/` contains canonical design, specification, security, data, operational
configuration, generated analysis, and reference material. Domain terminology
lives in [../CONTEXT.md](../CONTEXT.md), while current work state lives only in
the configured issue tracker.

## Core Docs

- [DESIGN.md](DESIGN.md): system principles, bounded contexts, and contracts.
- [BACKEND.md](BACKEND.md): backend service boundaries and execution model.
- [DATA.md](DATA.md): canonical data schemas, lineage, and dataset outputs.
- [SECURITY.md](SECURITY.md): sandboxing, trust boundaries, secrets, and external integrations.
- [PRODUCT_SENSE.md](PRODUCT_SENSE.md): users, value model, success metrics, and non-goals.
- [ROADMAP.md](ROADMAP.md): staged development direction.

## Agent Configuration

- [agents/issue-tracker.md](agents/issue-tracker.md): Local Markdown tracker
  configuration and artifact ownership rules.
- [../.scratch/README.md](../.scratch/README.md): current issues, dependencies,
  assignment, activation triggers, and technical debt.

## Deep Design

- [design-docs/agent-data-synthesis-framework.md](design-docs/agent-data-synthesis-framework.md): full framework architecture.
- [design-docs/algorithm-flow-and-architecture.md](design-docs/algorithm-flow-and-architecture.md): explanatory walkthrough of the current algorithm flow, architecture layers, gates, and dataset artifacts.
- [design-docs/architecture-explainers.md](design-docs/architecture-explainers.md): detailed explanations of architecture and algorithm concepts such as the AWM environment model.
- [design-docs/representative-scale-and-downstream-evidence.md](design-docs/representative-scale-and-downstream-evidence.md): approved evidence boundary for representative three-domain runs and external downstream benchmark result exchange.
- [design-docs/domain-aware-representative-generation.md](design-docs/domain-aware-representative-generation.md): approved domain-owned generation-spec and representative-eligibility boundary for Plan 0043.
- [design-docs/representative-provider-schema-hardening.md](design-docs/representative-provider-schema-hardening.md): approved repair for strict real-provider schema failures and truthful zero-accepted reporting.

## Product Specs

- [product-specs/framework-mvp.md](product-specs/framework-mvp.md): MVP scope and acceptance criteria.
- [product-specs/async-local-orchestration.md](product-specs/async-local-orchestration.md): desired behavior and acceptance for resumable local orchestration.
- [product-specs/semantic-duplicate-detection.md](product-specs/semantic-duplicate-detection.md): desired behavior and evaluation boundary for semantic duplicate detection.

## References

- [references/agent-data-synthesis-pdf-analysis.md](references/agent-data-synthesis-pdf-analysis.md): structured analysis of `Agent-数据合成.pdf`.

## Generated Artifacts

- [generated/README.md](generated/README.md): index for future generated schemas, diagrams, reports, and benchmark outputs.
- [generated/awm-runtime-extraction-readiness.md](generated/awm-runtime-extraction-readiness.md): Phase E extraction readiness decision for the internal AWM runtime kernel.

## Historical Execution Records

- [PLANS.md](PLANS.md): compatibility index for the legacy execution-plan archive; it does not own current work state.
- [exec-plans/active/README.md](exec-plans/active/README.md): historical empty active bucket retained for link compatibility.
- [exec-plans/completed/README.md](exec-plans/completed/README.md): complete accepted-plan history.
- [exec-plans/completed/0046-final-answer-grounding-and-generation-diversity.md](exec-plans/completed/0046-final-answer-grounding-and-generation-diversity.md): latest completed plan for grounded final answers, expected-state reference grounding, and deterministic generation diversity validated by the `_30_v5` representative gate.
- [exec-plans/completed/0045-domain-parameterized-multi-batch-generation-reliability.md](exec-plans/completed/0045-domain-parameterized-multi-batch-generation-reliability.md): completed plan for reliable domain-parameterized multi-batch generation and validated three-domain representative evidence.
- [exec-plans/completed/0044-representative-provider-schema-hardening.md](exec-plans/completed/0044-representative-provider-schema-hardening.md): completed plan for strict provider schema diagnostics, replayable prompt grounding, truthful zero-accepted reports, and successful three-domain probes.
- [exec-plans/completed/0043-domain-aware-representative-generation-and-campaign-readiness.md](exec-plans/completed/0043-domain-aware-representative-generation-and-campaign-readiness.md): latest completed plan for bounded three-domain LLM task-contract generation and representative campaign readiness.
- [exec-plans/deferred/README.md](exec-plans/deferred/README.md): archived deferred-plan records with links to canonical specs and issues.
- [exec-plans/indexes/README.md](exec-plans/indexes/README.md): historical plan indexes and decision records.
- [exec-plans/tech-debt/README.md](exec-plans/tech-debt/README.md): archived technical-debt records; current debt state is in `.scratch/`.
