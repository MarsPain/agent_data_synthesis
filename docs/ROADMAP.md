# Roadmap

## Stage 0: Context and Architecture

- Establish root entrypoints and canonical docs.
- Define framework contracts from the source PDF.
- Add documentation validation.

## Stage 1: Local Executable Prototype

- Implement seed intake and domain config.
- Add remote OpenAI-compatible LLM provider configuration with `AGENT_DATA_LLM_BASE_URL`, `AGENT_DATA_API_KEY`, and `AGENT_DATA_LLM_MODEL`.
- Build SQLite-backed environment generation.
- Define Python tool registry and schema contracts.
- Generate simple tasks through the remote LLM provider with executable verifiers.
- Export accepted samples as JSONL with manifests.
- Record provenance and config hashes needed for later impact analysis.

## Stage 2: Quality and Curriculum

- Add difficulty scoring and curriculum policies.
- Add logical validators and diversity metrics.
- Add failure classification and retry loops.
- Add human review queue format for uncertain samples.
- Add metric slicing by domain, difficulty, tool combination, generator role, and verifier type.
- Add parent-version comparison reports for quality, coverage, cost, and held-out task performance.

## Stage 3: Agentic Generation Loop

- Separate task generation from solution-policy execution and preserve policy
  lineage.
- Add multi-step, stateful trajectories before broader branching behavior.
- Add a bounded critic/refinement loop that diagnoses failed trajectories, reruns
  one repaired attempt, and reports refined outcomes separately. Completed in
  plan 0006.
- Add generator role contracts, registry-backed routing, role lineage, disabled
  future-role guardrails, and role-level quality visibility. Completed in plan
  0007.
- Add tool expansion when failures indicate missing capability. Completed in
  plan 0008 with capability-gap diagnostics, bounded tool proposals, curated
  local tool admission, proposal artifacts, and reporting.
- Add multi-path trajectory generation and branching behavior-tree tasks.
  Completed in plan 0009 with bounded branch plans, checkpointed local branch
  execution, selected-branch lineage, and branch-level quality reporting.
- Add AgentInstruct-style seed transformation, taxonomy-driven task expansion, and suggester/editor refinement.
  Completed in plan 0010 with deterministic seed transformations, task
  suggester/editor roles, edited-candidate lineage, inspectable suggestion
  rejections, and reporting slices.
- Add provenance, licensing, network-policy, sandbox-policy, and source-event
  audit gates before controlled network-backed environment synthesis. Completed
  in plan 0011 with source bundles, source-policy hashes, source audit events,
  default-deny external-source gates, and quality slices.
- Add controlled network-backed environment synthesis. Implemented in plan 0012
  with explicit CLI opt-in, allowlisted HTTPS JSON fetches, request and payload
  limits, contacts environment-source admission, sanitized fetch/admission
  events, and no-network fixture tests.

## Stage 4: Interoperability and Scale

- Add MCP-compatible environment/tool adapters. Implemented in plan 0013 as an
  opt-in local adapter manifest, tool-call envelopes, adapter lineage, quality
  slices, and in-process contacts shim before any external MCP server
  integration.
- Add generated-code sandboxing and executable admission controls. Implemented
  in plan 0015 with typed generated executable records, Python static safety
  scanning, explicit sandbox admission, restricted local fixture execution,
  redacted sandbox audits, and quality slices before external MCP servers or
  generated executable roles are enabled.
- Harden the candidate execution boundary before async orchestration. Implemented
  in plan 0016 with structured per-candidate outcomes while preserving the
  synchronous default pipeline.
- Add configurable run profiles and deterministic synchronous scale probing
  before async orchestration. Implemented in plan 0017 with `run_profile_v1`,
  sanitized manifest attribution, and contacts-domain scale-probe fixtures used
  to decide whether plan 0014 or semantic duplicate detection should be
  reactivated.
- Add profile-driven local contacts source admission before async orchestration.
  Implemented in plan 0018 with `run_profile_v2`, profile-relative contacts JSON
  ingestion through source governance, sanitized source metadata, and environment
  overrides over the existing synchronous pipeline.
- Generalize profile-local source admission across domains before adding more
  source-backed domains. Implemented in plan 0035 with a domain source importer
  protocol, contacts compatibility importer, mobile messages importer, and
  generic `domain_environment_input` pipeline plumbing while keeping controlled
  network ingestion contacts-only.
- Add profile-attributed quality and comparison before async orchestration.
  Implemented in plan 0019 with sanitized per-record profile attribution,
  profile quality slices, and parent-comparison visibility over profile slice
  keys.
- Add profile decision gates and benchmark reporting before async orchestration.
  Implemented in plan 0020 with opt-in sanitized decision reports over
  synchronous profile artifacts, explicit async and semantic-duplicate gates,
  and MVP quality-floor decisions.
- Add candidate isolation and deterministic merge admission before async
  orchestration. Implemented in plan 0021 with per-candidate environment,
  registry, and adapter rebuilds, candidate-local tool expansion, and stable
  sequence-ordered duplicate admission over provisional outcomes.
- Add held-out evaluation and profile benchmarking before async orchestration.
  Implemented in plan 0022 with opt-in deterministic contacts evaluation
  reports, capability slices, parent evaluation comparison, and
  profile-decision evidence without changing default synchronous generation.
- Tighten held-out evaluation quality ratchets and profile promotion gates before
  async orchestration. Implemented in plan 0023 with controlled-failure
  benchmark semantics, per-capability thresholds, semantic duplicate watch
  rationale, and profile promotion separated from the MVP quality floor.
- Make held-out evaluation and release evidence domain-aware before adding more
  domains. Implemented in plan 0036 with contacts/mobile held-out suite
  resolution, mobile evaluation evidence, profile-promotion domain mismatch
  gates, and dataset release domain mismatch gates.
- Add profile-purpose classification and dataset release admission before async
  orchestration. Implemented in plan 0024 with explicit profile-purpose metadata and
  opt-in dataset release admission so diagnostic profiles remain distinct from
  releaseable dataset versions while preserving the synchronous artifact path.
- Tighten dataset release admission with release completeness gates before async
  orchestration. Implemented in plan 0026 with minimum accepted-sample,
  rejection-rate, task-type coverage, and tool-combination coverage gates so
  small release-candidate smoke runs cannot be mistaken for sufficiently
  covered local MVP dataset versions.
- Add hash-locked dataset release packs and standalone reproducibility
  verification before async orchestration. Implemented in plan 0027 with
  opt-in `dataset_release_pack.json`, artifact hashes and byte counts,
  manifest-aware pack creation, and offline drift detection without rerunning
  candidate generation.
- Add release quality evidence audit and a human-readable dataset release card
  before async orchestration. Implemented in plan 0028 with opt-in
  `release_quality_audit.json`, duplicate-family risk signals, and
  `dataset_release_card.md` without implementing full semantic duplicate
  detection or changing default release admission.
- Add a second deterministic mobile-agent-like domain before full AWM runtime
  extraction. Implemented in plan 0029 with synthetic phone message threads,
  reminders, draft replies, mobile tools, domain bundle selection,
  candidate-local mobile isolation, mobile state verification, and
  `mobile_fixture` run-profile support while keeping the runtime boundary
  internal.
- Stabilize the internal runtime contract and episode evidence before full AWM
  runtime extraction. Implemented in plan 0030 with explicit
  `runtime_metadata_v1`, shared contacts/mobile runtime protocol coverage,
  sanitized in-memory `episode_log_v1` evidence, and a diagnostic episode
  summary reader while keeping package extraction, reward/RL consumers, async
  orchestration, and semantic duplicate detection deferred.
- Add the first real runtime/episode consumer before full AWM runtime
  extraction. Implemented in plan 0031 with opt-in `episodes.jsonl` export and
  deterministic `episode_quality_report_v1` scoring over contacts/mobile
  episode evidence while keeping executable replay, reward training, Agentic
  RL, async orchestration, release admission changes, and package extraction
  deferred.
- Add an executable episode replay consistency probe before full AWM runtime
  extraction. Implemented in plan 0032 with opt-in replay of `episode_log_v1`
  against fresh contacts/mobile runtimes and `episode_replay_report_v1`
  package-boundary evidence while keeping reward/RL, external MCP servers,
  async orchestration, release admission changes, and package extraction
  deferred.
- Split overloaded task/policy/verifier fields before full AWM runtime
  extraction. Implemented in plan 0033 with internal task-intent, policy-hint,
  expected-outcome, and expected-state contracts while preserving
  `CandidateTask` compatibility, default CLI behavior, public dataset schemas,
  and sanitized episode consumers.
- Add deterministic reward-label export before reward/RL workflows and full AWM
  runtime extraction. Implemented in plan 0034 as an opt-in
  `reward_labels.jsonl` and `reward_label_report.json` consumer over sanitized
  episode, quality, replay, and task-contract evidence without training a
  reward model or changing release admission.
- Prepare the environment layer for a future shared AWM runtime without
  prematurely splitting it into a separate project. Plan 0025 Phase C adds
  runtime sessions, action envelopes, and diagnostic rollout collection after
  plans 0031, 0032, 0033, and 0034 supplied repo-local data-quality,
  executable replay, task/policy/verifier, and reward-label evidence. Runtime
  package extraction still needs adapter generalization and an explicit
  extraction-readiness review.
- Add async orchestration with durable queues.
- Evaluate Ray-style distributed workers if throughput requires it.
- Add monitoring dashboards and cost controls.
- Add row-level scheduling, message offloading, and per-role resource metrics if distributed orchestration is adopted.
- Keep LLM inference behind remote provider APIs; do not add local LLM cluster deployment as a roadmap item.
