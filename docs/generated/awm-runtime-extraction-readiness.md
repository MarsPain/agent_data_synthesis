# AWM Runtime Extraction Readiness

Generated for Plan 0025 Phase E on 2026-06-20. Updated after Phase E1
reward-label runtime contract hardening on 2026-06-20.

## Decision

Status: `continue_hardening`

Do not activate Phase F package extraction yet. The runtime boundary has real
multi-consumer pressure and enough structure to continue hardening. Phase E1
removed the reward-label runtime allowlist and moved reward preference grouping
to runtime descriptor declarations, but Phase F still requires a fresh
extraction-readiness review before activation.

Next plan pointer:
[0025 Phase E1: Reward Label Runtime Contract Hardening](../exec-plans/completed/0025-phase-e1-reward-label-runtime-contract-hardening.md).

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

## Readiness Criteria

| Criterion | Status | Evidence |
| --- | --- | --- |
| At least two production domain runtimes use the same descriptor/session boundary. | Pass | `synthesis.runtime.DEFAULT_RUNTIME_REGISTRY`; `synthesis.domain_pipeline.DomainPipelineBundle.runtime_session`; `tests.test_runtime_contract.RuntimeContractTest.test_contacts_and_mobile_satisfy_shared_runtime_protocol`. |
| At least one fake/minimal runtime test proves the boundary is not contacts/mobile-specific. | Pass | `tests.test_runtime_contract` fake descriptor coverage; `tests.test_episode_quality.test_fake_runtime_descriptor_is_accepted_without_consumer_allowlist`; `tests.test_episode_replay.test_fake_runtime_without_replay_support_reports_unsupported`; `tests.test_reward_labels.test_fake_runtime_reward_capability_status_is_descriptor_derived`. |
| Synthesis, episode quality, executable replay, reward labels, rollouts, and local adapter manifests consume descriptors or sessions. | Pass | `synthesis.domain_pipeline`, `synthesis.episode_quality`, `synthesis.episode_replay`, `synthesis.reward_labels`, `synthesis.rollouts`, and `synthesis.mcp` consume descriptors, sessions, action envelopes, or episode logs. Reward-label contracts now use record/report-local runtime evidence instead of a contract allowlist. |
| Runtime metadata and descriptors reject dataset/release/profile/provider/credential/raw-source/host-path leakage. | Pass | `synthesis.runtime.validate_runtime_descriptor_safety`, `synthesis.runtime.validate_runtime_metadata_safety`, `tests.test_runtime_contract.test_runtime_descriptor_safety_rejects_profile_release_paths_prompts_and_secrets`, and adapter redaction tests in `tests.test_mcp_adapters`. |
| Adding a new runtime does not require editing core replay or reward-label allowlists. | Pass | Replay uses descriptor lookup. Reward-label fake-runtime tests validate labels and reports without adding the fake runtime to a contract allowlist. |
| Unused runtime methods are removed or explicitly marked experimental. | Partial pass | `RuntimeSession` methods are exercised by rollouts, adapter shims, and tests. `RuntimeSession.rebuild` exists for the package-shaped session API but current executable replay rebuilds through `rebuild_domain_pipeline_bundle`; this should be documented or exercised before extraction. |
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
  `runtime_capability_status`, rebuilds through descriptor seeds, and derives
  state-changing tools from descriptors.
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
| Executable replay | `runtime_capability_status`, `runtime_descriptor`, descriptor rebuild seed and state-changing tools | Contacts, mobile, fake unsupported runtime, registry override tests. |
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
  boundary used by rollouts and adapters.
- `EnvironmentRuntime`: protocol used by domain environments to expose runtime
  metadata, checkpointing, restore, and rebuild behavior.

Internal-only until another plan separates domain packs:

- Default contacts/mobile descriptor construction and `_mobile_messages_seed`.
- `RuntimeCapabilityDescriptor.rebuild_seed` when it points at
  `synthesis.seeds.DomainSeed`; this is useful internally but couples replay
  rebuild to this repository's domain-pack model.

Needs hardening or review before extraction:

- `RuntimeSession.rebuild` should be either exercised by consumers or marked as
  package-facing experimental before extraction.
- A new extraction-readiness review should re-evaluate the package boundary now
  that Phase E1 reward-label contract blockers are removed.

No removal is recommended in Phase E because this phase is a decision gate and
must not change runtime APIs.

## Risks

- If Phase F starts without a fresh review, package consumers may inherit
  unresolved session rebuild semantics or domain-pack rebuild coupling.
- The runtime package boundary would be blurred by `DomainSeed` rebuild coupling
  unless Phase F explicitly keeps domain-pack rebuild policy outside the package
  or introduces a package-neutral rebuild recipe.
- Adapter support is local and in-process only. That is acceptable for this
  extraction decision, but external adapter behavior must remain a later plan.

## Required Next Step

Run a fresh extraction-readiness review before activating Phase F. Phase E1 has
removed the reward-label runtime allowlist, replaced domain-specific preference
grouping with descriptor-owned grouping, and added fake runtime contract tests
that validate labels and label reports without contacts/mobile contract edits.
