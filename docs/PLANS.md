# Plans

## Lifecycle States

- `active`: work currently intended for implementation.
- `completed`: accepted plans with completion date.
- `tech-debt`: known unresolved debt with impact and target stage.
- `deferred`: planned but postponed until a concrete trigger condition is met.

## Active

No active implementation plans.

## Deferred

- [0014-async-local-orchestration-with-durable-queues](exec-plans/deferred/0014-async-local-orchestration-with-durable-queues.md):
  async job lifecycle, durable file-backed queues, manifest-based resumption,
  concurrency limits, cancellation, and per-role cost tracking; **deferred**
  until single runs exceed ~10 minutes or 100+ candidates. See the plan's
  "补充思考" section for the full deferral rationale.
- [0025-phase-f-awm-runtime-package-extraction](exec-plans/deferred/0025-phase-f-awm-runtime-package-extraction.md):
  deferred until extraction readiness is revisited after completed Phase E1 and
  returns `ready_for_extraction_plan`.

## Phase Indexes

- [0025-awm-runtime-phase-index](exec-plans/deferred/0025-awm-runtime-phase-index.md):
  umbrella decision record for the staged AWM runtime-kernel work. This is not
  a directly executable implementation plan. Historical links to
  [0025-awm-runtime-boundary-and-shared-environment-kernel](exec-plans/deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md)
  are preserved by a redirect stub.

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
- [0015-generated-code-sandboxing-and-executable-admission-controls](exec-plans/completed/0015-generated-code-sandboxing-and-executable-admission-controls.md): added generated-code sandbox contracts, static scans, admission records, restricted local fixture execution, redacted sandbox audit artifacts, and reporting slices. Completed on 2026-05-27.
- [0016-candidate-execution-boundary-and-orchestration-readiness](exec-plans/completed/0016-candidate-execution-boundary-and-orchestration-readiness.md): extracted and tested a structured candidate-processing boundary before deferred async orchestration work. Completed on 2026-05-29.
- [0017-configurable-run-profiles-and-scale-probe](exec-plans/completed/0017-configurable-run-profiles-and-scale-probe.md): added declarative run profiles, deterministic scale-probe generation, sanitized manifest metadata, and synchronous scale evidence before async orchestration or semantic duplicate detection. Completed on 2026-05-29.
- [0018-profile-driven-source-admission-and-contacts-environment-overrides](exec-plans/completed/0018-profile-driven-source-admission-and-contacts-environment-overrides.md): added `run_profile_v2`, profile-local contacts JSON source admission, environment overrides, sanitized manifest source metadata, and source-governed synchronous runs. Completed on 2026-05-30.
- [0019-profile-attributed-quality-and-comparison](exec-plans/completed/0019-profile-attributed-quality-and-comparison.md): added sanitized per-record run-profile attribution for samples and rejections, profile quality slices, and parent-comparison visibility while preserving synchronous profile execution. Completed on 2026-05-30.
- [0020-profile-decision-gates-and-benchmark-reporting](exec-plans/completed/0020-profile-decision-gates-and-benchmark-reporting.md): added opt-in sanitized profile decision reports with async orchestration, semantic duplicate detection, and MVP quality-floor decisions over synchronous profile artifacts. Completed on 2026-05-30.
- [0021-candidate-isolation-and-deterministic-merge](exec-plans/completed/0021-candidate-isolation-and-deterministic-merge.md): added per-candidate environment/registry/adapter isolation and deterministic merge admission for provisional candidate outcomes. Completed on 2026-05-31.
- [0022-held-out-evaluation-and-profile-benchmarking](exec-plans/completed/0022-held-out-evaluation-and-profile-benchmarking.md): added opt-in held-out evaluation reports, deterministic contacts benchmark tasks, capability slices, optional parent evaluation comparison, and profile-decision evidence before async orchestration or semantic duplicate detection. Completed on 2026-05-31.
- [0023-evaluation-quality-ratchet-and-profile-promotion](exec-plans/completed/0023-evaluation-quality-ratchet-and-profile-promotion.md): tightened held-out evaluation semantics, added capability-level thresholds, introduced profile promotion decisions, and kept async orchestration plus semantic duplicate detection deferred until explicit triggers are met. Completed on 2026-05-31.
- [0024-profile-purpose-and-dataset-release-admission](exec-plans/completed/0024-profile-purpose-and-dataset-release-admission.md): added profile-purpose classification and an opt-in dataset release admission report so diagnostic profiles cannot be mistaken for releaseable dataset versions. Completed on 2026-06-09.
- [0025-phase-a-internal-runtime-kernel-hardening](exec-plans/completed/0025-phase-a-internal-runtime-kernel-hardening.md): added immutable runtime capability descriptors, deterministic registry lookup, descriptor-backed replay/reward support, and fake runtime pressure tests. Completed on 2026-06-19.
- [0025-phase-b-consumer-inversion](exec-plans/completed/0025-phase-b-consumer-inversion.md): completed runtime descriptor-driven consumer inversion by removing episode-quality contacts/mobile allowlists, aligning consumer capability status semantics, and preserving replay/reward descriptor behavior. Completed on 2026-06-19.
- [0025-phase-c-rollout-ready-runtime-api](exec-plans/completed/0025-phase-c-rollout-ready-runtime-api.md): added runtime sessions, action request/result envelopes, and diagnostic rollout collection that emits replayable, reward-label-compatible episodes without RL training or default CLI changes. Completed on 2026-06-19.
- [0025-phase-d-adapter-surface-generalization](exec-plans/completed/0025-phase-d-adapter-surface-generalization.md): generalized the opt-in local MCP-compatible adapter surface onto runtime descriptors, runtime sessions, and action envelopes while preserving contacts compatibility and adding mobile local adapter support without external MCP servers. Completed on 2026-06-20.
- [0025-phase-e-extraction-readiness-review](exec-plans/completed/0025-phase-e-extraction-readiness-review.md): completed an evidence-backed extraction decision with status `continue_hardening`, keeping Phase F deferred and pointing the next hardening work at reward-label runtime contracts. Completed on 2026-06-20.
- [0025-phase-e1-reward-label-runtime-contract-hardening](exec-plans/completed/0025-phase-e1-reward-label-runtime-contract-hardening.md): removed reward-label runtime contract allowlists and moved reward preference grouping to runtime descriptor declarations before the next extraction-readiness review. Completed on 2026-06-20.
- [0026-dataset-release-coverage-and-admission-ratchet](exec-plans/completed/0026-dataset-release-coverage-and-admission-ratchet.md): tightened dataset release admission with release completeness thresholds, coverage observations, insufficient-evidence outcomes, and a deterministic release-candidate fixture. Completed on 2026-06-09.
- [0027-dataset-release-pack-and-reproducibility-verification](exec-plans/completed/0027-dataset-release-pack-and-reproducibility-verification.md): added opt-in hash-locked release packs and standalone verification so passed release-candidate artifacts can be audited without rerunning generation. Completed on 2026-06-12.
- [0028-release-quality-evidence-audit-and-card](exec-plans/completed/0028-release-quality-evidence-audit-and-card.md): added opt-in release quality evidence audits and human-readable dataset release cards for release-candidate artifact sets without implementing full semantic duplicate detection or changing default release admission. Completed on 2026-06-12.
- [0029-mobile-agent-second-domain-pipeline-probe](exec-plans/completed/0029-mobile-agent-second-domain-pipeline-probe.md): added a deterministic phone-like messages/reminders/draft-reply domain, mobile tools, mobile state verification, and a minimal synchronous domain pipeline boundary while keeping full AWM runtime extraction deferred. Completed on 2026-06-12.
- [0030-runtime-contract-and-episode-evidence](exec-plans/completed/0030-runtime-contract-and-episode-evidence.md): added shared runtime metadata, contacts/mobile runtime protocol coverage, sanitized in-memory episode evidence, and a diagnostic episode summary reader while keeping full AWM runtime extraction deferred. Completed on 2026-06-13.
- [0031-episode-replay-and-data-quality-scoring-consumer](exec-plans/completed/0031-episode-replay-and-data-quality-scoring-consumer.md): added opt-in episode JSONL export and deterministic episode quality scoring as the first repo-local runtime/episode consumer after plan 0030. Completed on 2026-06-13.
- [0032-executable-episode-replay-consistency-probe](exec-plans/completed/0032-executable-episode-replay-consistency-probe.md): added opt-in executable replay over `episode_log_v1` against fresh contacts/mobile runtimes and `episode_replay_report_v1` package-boundary evidence while keeping runtime package extraction deferred. Completed on 2026-06-13.
- [0033-task-intent-policy-verifier-contract-split](exec-plans/completed/0033-task-intent-policy-verifier-contract-split.md): split `CandidateTask` responsibilities into internal task-intent, policy-hint, expected-outcome, and expected-state contracts while preserving current public artifact schemas and keeping plan 0025 deferred. Completed on 2026-06-14.
- [0034-reward-label-export-and-runtime-scoring-consumer](exec-plans/completed/0034-reward-label-export-and-runtime-scoring-consumer.md): added opt-in deterministic reward-label export and runtime scoring over sanitized episode evidence without reward-model training, RL rollout collection, release admission changes, or AWM runtime package extraction. Completed on 2026-06-14.
- [0035-domain-source-admission-interface](exec-plans/completed/0035-domain-source-admission-interface.md): promoted profile-local source ingestion into a domain source importer protocol, preserved contacts compatibility, added mobile messages source-backed runs, and replaced contacts-specific pipeline source plumbing with generic `domain_environment_input` while keeping controlled network source ingestion contacts-only. Completed on 2026-06-14.
- [0036-domain-aware-held-out-evaluation-and-release-semantics](exec-plans/completed/0036-domain-aware-held-out-evaluation-and-release-semantics.md): made held-out evaluation, profile promotion, and dataset release admission domain-aware across contacts and mobile messages so mismatched evaluation evidence is insufficient rather than releaseable. Completed on 2026-06-19.

## Technical Debt

- Current debt bucket: [exec-plans/tech-debt/README.md](exec-plans/tech-debt/README.md).
- `TD-0001` generated-code sandboxing is resolved by completed plan
  [0015-generated-code-sandboxing-and-executable-admission-controls](exec-plans/completed/0015-generated-code-sandboxing-and-executable-admission-controls.md).
- `TD-0002` semantic duplicate detection remains unresolved until dataset
  volume or curriculum-benchmark signals justify implementation.
