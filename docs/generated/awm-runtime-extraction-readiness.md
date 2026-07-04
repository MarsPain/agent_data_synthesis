# AWM Runtime Extraction Readiness

Generated for Plan 0025 Phase E on 2026-06-20. Updated after Phase E1
reward-label runtime contract hardening on 2026-06-20, Phase E2
runtime-session replay boundary hardening on 2026-06-29, and Phase F
in-repository package-boundary extraction on 2026-07-04.

## Decision

Status: `extracted_in_repository`

Phase F was activated by explicit human direction and implemented as an
in-repository package boundary. The runtime boundary has real multi-consumer
pressure and now has a concrete `awm_runtime` package for package-neutral
runtime and episode primitives. Phase E1 removed the reward-label runtime
allowlist and moved reward preference grouping to runtime descriptor
declarations. Phase E2 removed executable replay's direct tool-registry
execution path and now drives supported replay actions through
`RuntimeSession.execute_action(...)` and action envelopes. Phase F then moved
runtime descriptors, registry primitives, metadata safety checks, runtime
sessions, action envelopes, episode transitions/logs, redaction, hashing, and
episode summaries into `awm_runtime`.

Next plan pointer:
[0025 Phase G: Runtime Extraction Soak and Compatibility Hardening](../exec-plans/active/0025-phase-g-runtime-extraction-soak-and-compatibility-hardening.md).

## Summary

Evidence supports the internal runtime direction:

- Contacts and mobile runtimes both use `RuntimeCapabilityDescriptor`,
  `RuntimeSession`, runtime action envelopes, and sanitized runtime metadata.
- Fake descriptor tests prove parts of the consumer boundary are not limited to
  contacts or mobile.
- Episode quality, executable replay, reward labels, diagnostic rollout
  collection, and local adapter manifests now consume runtime descriptors,
  sessions, action envelopes, or episode logs.
- Runtime descriptor and metadata safety checks reject dataset version, release
  admission, profile promotion, provider prompts, credentials, raw sources, and
  host paths.

Phase E originally identified two reward-label boundary leaks. Phase E1 has
now addressed both:

- `validate_reward_label_record` no longer uses a contract-level runtime
  allowlist, and `validate_reward_label_report_record` validates summary
  runtime ids against report-local `observed.runtime_counts` evidence.
- `synthesis.reward_labels._preference_group_id` now reads
  `RuntimeCapabilityDescriptor.reward_preference_groups` and falls back to a
  deterministic generic tool-derived grouping.

Phase E2 addressed the replay/session boundary leak:

- `synthesis.episode_replay.replay_episode` rebuilds the candidate through the
  domain pipeline, obtains a `RuntimeSession`, constructs
  `RuntimeActionRequest` records for each action, and compares
  `RuntimeActionResult` observation and state-change hashes against
  `episode_log_v1` transition hashes.
- `episode_replay_report_v1.runtime_boundary_evidence` now records
  `execute_action` as runtime-session evidence and records no direct registry
  methods for the replay consumer.

Phase F established the package boundary:

- `awm_runtime.runtime` owns package-neutral runtime descriptors, registry
  primitives, capability status vocabulary, metadata safety checks, runtime
  sessions, and action envelopes.
- `awm_runtime.episodes` owns package-neutral episode transition/log,
  deterministic hash, redaction, and episode-summary primitives.
- `synthesis.runtime_registry` owns repository-specific contacts/mobile default
  descriptor construction because those descriptors still contain domain-pack
  rebuild seeds.
- `synthesis.runtime` and `synthesis.episodes` remain compatibility re-export
  shims for one migration cycle.

## Readiness Criteria

| Criterion | Status | Evidence |
| --- | --- | --- |
| At least two production domain runtimes use the same descriptor/session boundary. | Pass | `synthesis.runtime.DEFAULT_RUNTIME_REGISTRY`; `synthesis.domain_pipeline.DomainPipelineBundle.runtime_session`; `tests.test_runtime_contract.RuntimeContractTest.test_contacts_and_mobile_satisfy_shared_runtime_protocol`. |
| At least one fake/minimal runtime test proves the boundary is not contacts/mobile-specific. | Pass | `tests.test_runtime_contract` fake descriptor coverage; `tests.test_episode_quality.test_fake_runtime_descriptor_is_accepted_without_consumer_allowlist`; `tests.test_episode_replay.test_fake_runtime_without_replay_support_reports_unsupported`; `tests.test_reward_labels.test_fake_runtime_reward_capability_status_is_descriptor_derived`. |
| Synthesis, episode quality, executable replay, reward labels, rollouts, and local adapter manifests consume descriptors or sessions. | Pass | `synthesis.domain_pipeline`, `synthesis.episode_quality`, `synthesis.episode_replay`, `synthesis.reward_labels`, `synthesis.rollouts`, and `synthesis.mcp` consume descriptors, sessions, action envelopes, or episode logs. Replay now executes actions through `RuntimeSession.execute_action(...)`; reward-label contracts now use record/report-local runtime evidence instead of a contract allowlist. |
| Runtime metadata and descriptors reject dataset/release/profile/provider/credential/raw-source/host-path leakage. | Pass | `synthesis.runtime.validate_runtime_descriptor_safety`, `synthesis.runtime.validate_runtime_metadata_safety`, `tests.test_runtime_contract.test_runtime_descriptor_safety_rejects_profile_release_paths_prompts_and_secrets`, and adapter redaction tests in `tests.test_mcp_adapters`. |
| Adding a new runtime does not require editing core replay or reward-label allowlists. | Pass | Replay uses descriptor lookup. Reward-label fake-runtime tests validate labels and reports without adding the fake runtime to a contract allowlist. |
| Unused runtime methods are removed or explicitly marked experimental. | Pass | `RuntimeSession` methods are exercised by rollouts, adapter shims, replay, and tests. `RuntimeSession.rebuild` is covered by runtime contract tests, while executable replay deliberately keeps domain-pack rebuild ownership in `synthesis.domain_pipeline` and consumes the rebuilt candidate as a `RuntimeSession`. |
| Docs define runtime, domain pack, synthesis, reward, release, and adapter ownership. | Pass | `docs/exec-plans/deferred/0025-awm-runtime-phase-index.md`, `docs/DESIGN.md`, `docs/BACKEND.md`, `docs/DATA.md`, and Phase A-D completion notes define the intended ownership boundaries. |

## Boundary Leakage Audit

Runtime-facing modules:

- `synthesis.runtime` contains explicit forbidden-key checks for dataset release,
  dataset version, profile decisions, provider payloads, credentials, raw
  sources, and local paths. These are safety rules, not leakage.
- `RuntimeCapabilityDescriptor.descriptor_metadata` and `RuntimeMetadata.export`
  both pass through safety validation before export.
- `RuntimeActionRequest.export` and `RuntimeActionResult.export` sanitize
  action arguments, observations, and state changes before validation.

Consumer modules:

- `synthesis.episode_quality` resolves runtime identity through
  `runtime_descriptor` and derives state-changing tools from descriptors.
- `synthesis.episode_replay` checks `supports_episode_replay` through
  `runtime_capability_status`, rebuilds through descriptor seeds and the domain
  pipeline, derives state-changing tools from descriptors, and executes replay
  actions through `RuntimeSession.execute_action(...)`.
- `synthesis.reward_labels` checks reward capability through
  `runtime_capability_status`, exports descriptor-owned preference groups, and
  writes reports whose summaries are validated against report-local runtime
  counts.
- `synthesis.rollouts` drives runtime sessions with `RuntimeActionRequest` and
  emits `episode_log_v1`.
- `synthesis.mcp.LocalRuntimeAdapterShim` builds manifests from
  `RuntimeCapabilityDescriptor` plus `RuntimeSession`.

Remaining domain assumptions:

- `synthesis.domain_pipeline.build_domain_pipeline_bundle` remains the domain
  pack router for contacts and mobile. That is acceptable because domain packs
  are intentionally out of the extraction boundary.
- Contacts and mobile keep their existing preference group ids through
  `RuntimeCapabilityDescriptor.reward_preference_groups`; fake runtimes can
  declare their own grouping without reward-label module edits.

## Consumer Evidence

| Consumer | Runtime boundary used | Coverage |
| --- | --- | --- |
| Synthesis/domain bundle | `DomainPipelineBundle.runtime_session`, `EnvironmentRuntime`, registry builders | Contacts and mobile bundle tests. |
| Episode quality | `runtime_descriptor`, descriptor state-changing tools | Contacts, mobile, fake runtime, unknown runtime tests. |
| Executable replay | `runtime_capability_status`, `runtime_descriptor`, descriptor rebuild seed, `RuntimeSession.execute_action`, `RuntimeActionRequest`, `RuntimeActionResult`, and descriptor state-changing tools | Contacts and mobile session-boundary tests, fake unsupported runtime, registry override tests, sanitized summary contract tests. |
| Reward labels | `runtime_capability_status`, `runtime_descriptor`, descriptor state-changing tools, descriptor reward preference groups, report-local runtime evidence | Contacts, mobile, fake capability-status tests, fake label/report contract validation. |
| Diagnostic rollouts | `RuntimeSession.checkpoint`, `restore_checkpoint`, `execute_action`; `RuntimeActionRequest` | Contacts and mobile rollout tests producing replayable reward-compatible episodes. |
| Local adapters | `RuntimeCapabilityDescriptor`, `RuntimeSession`, runtime action envelopes | Contacts runtime-backed manifest, mobile adapter execution, unsupported fake runtime rejection, redaction tests. |

## API Surface Audit

Extraction-eligible after hardening:

- `RuntimeCapabilityDescriptor`: capability declaration for runtime identity,
  rebuild, replay, reward labels, local adapter support, state-changing tools,
  task taxonomy, reward preference grouping, rebuild seed, and safe descriptor
  metadata.
- `RuntimeRegistry`, `registered_runtime_ids`, `runtime_descriptor`,
  `runtime_registry_with`, and `runtime_capability_status`: descriptor lookup
  and capability status vocabulary.
- `RuntimeMetadata` and `runtime_metadata_from_environment`: sanitized runtime
  identity, reset, state backend, checkpoint strategy, source provenance,
  sandbox policy, and adapter metadata.
- `RuntimeActionRequest` and `RuntimeActionResult`: action envelope records,
  content hashes, failure envelopes, state-change summaries, and redaction.
- `RuntimeSession`: checkpoint/restore/list-tools/execute-action session
  boundary used by rollouts, adapters, replay, and tests.
- `EnvironmentRuntime`: protocol used by domain environments to expose runtime
  metadata, checkpointing, restore, and rebuild behavior.

Internal-only until another plan separates domain packs:

- Default contacts/mobile descriptor construction and `_mobile_messages_seed`.
- `RuntimeCapabilityDescriptor.rebuild_seed` when it points at
  `synthesis.seeds.DomainSeed`; this is useful internally but couples replay
  rebuild to this repository's domain-pack model.

Needs hardening or review after extraction:

- Phase G should soak the compatibility window, add stronger import-boundary
  guardrails, and confirm representative contacts/mobile replay plus
  reward-label behavior remains stable.

No removal is recommended for compatibility shims until Phase G records the
compatibility window and removal criteria.

## Risks

- Future consumers may blur the runtime package boundary if they move
  domain-pack rebuild policy or `DomainSeed` construction into `awm_runtime`.
- The compatibility shims can become permanent technical debt unless Phase G
  records explicit removal criteria.
- Adapter support is local and in-process only. That is acceptable for this
  extraction decision, but external adapter behavior must remain a later plan.

## Required Next Step

Run Phase G compatibility soak before third-domain work, external MCP servers,
distributed rollout workers, or separate repository publishing. Phase F has
already kept domain-pack rebuild policy outside `awm_runtime` by placing
repository-owned default descriptor construction in `synthesis.runtime_registry`.
