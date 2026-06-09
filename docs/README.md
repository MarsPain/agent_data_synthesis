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

## Product Specs

- [product-specs/framework-mvp.md](product-specs/framework-mvp.md): MVP scope and acceptance criteria.

## References

- [references/agent-data-synthesis-pdf-analysis.md](references/agent-data-synthesis-pdf-analysis.md): structured analysis of `Agent-数据合成.pdf`.

## Generated Artifacts

- [generated/README.md](generated/README.md): index for future generated schemas, diagrams, reports, and benchmark outputs.

## Execution Plans

- [exec-plans/active/README.md](exec-plans/active/README.md): active plan bucket.
- [exec-plans/completed/README.md](exec-plans/completed/README.md): completed plan bucket.
- [exec-plans/deferred/README.md](exec-plans/deferred/README.md): deferred plan bucket.
- [exec-plans/deferred/0014-async-local-orchestration-with-durable-queues.md](exec-plans/deferred/0014-async-local-orchestration-with-durable-queues.md): deferred async local orchestration with durable queues plan.
- [exec-plans/deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md](exec-plans/deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md): deferred staged extraction path for a shared AWM environment runtime boundary.
- [exec-plans/completed/0011-provenance-licensing-and-sandbox-gates.md](exec-plans/completed/0011-provenance-licensing-and-sandbox-gates.md): source provenance, license eligibility, default-deny network policy, sandbox policy, source-event audit artifacts, and reporting slices.
- [exec-plans/completed/0012-controlled-network-backed-environment-synthesis.md](exec-plans/completed/0012-controlled-network-backed-environment-synthesis.md): controlled opt-in HTTPS source ingestion, allowlisted host enforcement, request budgets, payload limits, contacts environment-source admission, and sanitized fetch/admission audit events.
- [exec-plans/completed/0013-mcp-compatible-environment-tool-adapters.md](exec-plans/completed/0013-mcp-compatible-environment-tool-adapters.md): local MCP-compatible adapter manifest, tool-call request/result envelopes, adapter lineage, quality slices, and in-process contacts shim.
- [exec-plans/completed/0015-generated-code-sandboxing-and-executable-admission-controls.md](exec-plans/completed/0015-generated-code-sandboxing-and-executable-admission-controls.md): generated-code sandbox contracts, static scans, executable admission records, restricted local fixture execution, redacted audits, and quality slices.
- [exec-plans/completed/0016-candidate-execution-boundary-and-orchestration-readiness.md](exec-plans/completed/0016-candidate-execution-boundary-and-orchestration-readiness.md): structured candidate-processing boundary, outcome records, ordered pipeline admission, and orchestration-readiness constraints.
- [exec-plans/completed/0017-configurable-run-profiles-and-scale-probe.md](exec-plans/completed/0017-configurable-run-profiles-and-scale-probe.md): declarative run profiles, deterministic contacts scale-probe generation, sanitized manifest attribution, and synchronous scale evidence.
- [exec-plans/completed/0018-profile-driven-source-admission-and-contacts-environment-overrides.md](exec-plans/completed/0018-profile-driven-source-admission-and-contacts-environment-overrides.md): profile-driven local contacts source admission, environment overrides, sanitized run-profile source metadata, and source-governed synchronous runs.
- [exec-plans/completed/0019-profile-attributed-quality-and-comparison.md](exec-plans/completed/0019-profile-attributed-quality-and-comparison.md): sanitized per-record run-profile attribution, profile quality slices, and parent-comparison visibility.
- [exec-plans/completed/0020-profile-decision-gates-and-benchmark-reporting.md](exec-plans/completed/0020-profile-decision-gates-and-benchmark-reporting.md): profile decision gates and benchmark reporting over synchronous profile artifacts.
- [exec-plans/completed/0021-candidate-isolation-and-deterministic-merge.md](exec-plans/completed/0021-candidate-isolation-and-deterministic-merge.md): candidate isolation and deterministic merge admission over provisional outcomes.
- [exec-plans/completed/0022-held-out-evaluation-and-profile-benchmarking.md](exec-plans/completed/0022-held-out-evaluation-and-profile-benchmarking.md): held-out evaluation reports and profile benchmarking evidence.
- [exec-plans/completed/0023-evaluation-quality-ratchet-and-profile-promotion.md](exec-plans/completed/0023-evaluation-quality-ratchet-and-profile-promotion.md): held-out evaluation quality ratchets and profile promotion decisions.
- [exec-plans/completed/0024-profile-purpose-and-dataset-release-admission.md](exec-plans/completed/0024-profile-purpose-and-dataset-release-admission.md): profile-purpose classification and opt-in dataset release admission reports.
- [exec-plans/completed/0026-dataset-release-coverage-and-admission-ratchet.md](exec-plans/completed/0026-dataset-release-coverage-and-admission-ratchet.md): dataset release completeness gates and deterministic release-candidate admission.
- [exec-plans/tech-debt/README.md](exec-plans/tech-debt/README.md): technical debt bucket.
