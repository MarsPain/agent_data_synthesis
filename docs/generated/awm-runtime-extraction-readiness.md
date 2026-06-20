# AWM Runtime Extraction Readiness

Generated for Plan 0025 Phase E on 2026-06-20.

## Decision

Status: `continue_hardening`

Do not activate Phase F package extraction yet. The runtime boundary has real
multi-consumer pressure and enough structure to continue hardening, but it is
not ready to become a package boundary because reward-label contracts still own
runtime allowlists and domain-shaped grouping rules.

Next plan pointer:
[0025 Phase E1: Reward Label Runtime Contract Hardening](../exec-plans/deferred/0025-phase-e1-reward-label-runtime-contract-hardening.md).

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

Extraction is still blocked by two boundary leaks:

- `synthesis.contracts.REWARD_LABEL_RUNTIMES` hard-codes reward-label runtime
  ids and is enforced by `validate_reward_label_record` and
  `validate_reward_label_report_record`.
- `synthesis.reward_labels._preference_group_id` maps known contacts/mobile
  tool names to capability labels instead of deriving grouping from descriptor
  taxonomy or another runtime-owned capability declaration.

## Readiness Criteria

| Criterion | Status | Evidence |
| --- | --- | --- |
| At least two production domain runtimes use the same descriptor/session boundary. | Pass | `synthesis.runtime.DEFAULT_RUNTIME_REGISTRY`; `synthesis.domain_pipeline.DomainPipelineBundle.runtime_session`; `tests.test_runtime_contract.RuntimeContractTest.test_contacts_and_mobile_satisfy_shared_runtime_protocol`. |
| At least one fake/minimal runtime test proves the boundary is not contacts/mobile-specific. | Pass | `tests.test_runtime_contract` fake descriptor coverage; `tests.test_episode_quality.test_fake_runtime_descriptor_is_accepted_without_consumer_allowlist`; `tests.test_episode_replay.test_fake_runtime_without_replay_support_reports_unsupported`; `tests.test_reward_labels.test_fake_runtime_reward_capability_status_is_descriptor_derived`. |
| Synthesis, episode quality, executable replay, reward labels, rollouts, and local adapter manifests consume descriptors or sessions. | Partial pass | `synthesis.domain_pipeline`, `synthesis.episode_quality`, `synthesis.episode_replay`, `synthesis.reward_labels`, `synthesis.rollouts`, and `synthesis.mcp` consume descriptors, sessions, action envelopes, or episode logs. Reward-label contract validation still has a runtime allowlist. |
| Runtime metadata and descriptors reject dataset/release/profile/provider/credential/raw-source/host-path leakage. | Pass | `synthesis.runtime.validate_runtime_descriptor_safety`, `synthesis.runtime.validate_runtime_metadata_safety`, `tests.test_runtime_contract.test_runtime_descriptor_safety_rejects_profile_release_paths_prompts_and_secrets`, and adapter redaction tests in `tests.test_mcp_adapters`. |
| Adding a new runtime does not require editing core replay or reward-label allowlists. | Fail | Replay uses descriptor lookup. Reward-label contracts still require edits to `synthesis.contracts.REWARD_LABEL_RUNTIMES`. |
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
  `runtime_capability_status`, but exported label records still must satisfy
  `synthesis.contracts.REWARD_LABEL_RUNTIMES`.
- `synthesis.rollouts` drives runtime sessions with `RuntimeActionRequest` and
  emits `episode_log_v1`.
- `synthesis.mcp.LocalRuntimeAdapterShim` builds manifests from
  `RuntimeCapabilityDescriptor` plus `RuntimeSession`.

Remaining domain assumptions:

- `synthesis.domain_pipeline.build_domain_pipeline_bundle` remains the domain
  pack router for contacts and mobile. That is acceptable because domain packs
  are intentionally out of the extraction boundary.
- `synthesis.reward_labels._preference_group_id` should stop encoding
  contacts/mobile tool names before extraction.

## Consumer Evidence

| Consumer | Runtime boundary used | Coverage |
| --- | --- | --- |
| Synthesis/domain bundle | `DomainPipelineBundle.runtime_session`, `EnvironmentRuntime`, registry builders | Contacts and mobile bundle tests. |
| Episode quality | `runtime_descriptor`, descriptor state-changing tools | Contacts, mobile, fake runtime, unknown runtime tests. |
| Executable replay | `runtime_capability_status`, `runtime_descriptor`, descriptor rebuild seed and state-changing tools | Contacts, mobile, fake unsupported runtime, registry override tests. |
| Reward labels | `runtime_capability_status`, `runtime_descriptor`, descriptor state-changing tools | Contacts, mobile, fake capability-status tests; blocked by contract allowlist. |
| Diagnostic rollouts | `RuntimeSession.checkpoint`, `restore_checkpoint`, `execute_action`; `RuntimeActionRequest` | Contacts and mobile rollout tests producing replayable reward-compatible episodes. |
| Local adapters | `RuntimeCapabilityDescriptor`, `RuntimeSession`, runtime action envelopes | Contacts runtime-backed manifest, mobile adapter execution, unsupported fake runtime rejection, redaction tests. |

## API Surface Audit

Extraction-eligible after hardening:

- `RuntimeCapabilityDescriptor`: capability declaration for runtime identity,
  rebuild, replay, reward labels, local adapter support, state-changing tools,
  task taxonomy, rebuild seed, and safe descriptor metadata.
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

Needs hardening before extraction:

- Reward label contract runtime validation should derive from runtime
  descriptors or report-local runtime evidence, not `REWARD_LABEL_RUNTIMES`.
- Reward preference grouping should derive from descriptor taxonomy or a
  runtime-owned grouping declaration, not hard-coded contacts/mobile tool names.
- `RuntimeSession.rebuild` should be either exercised by consumers or marked as
  package-facing experimental before extraction.

No removal is recommended in Phase E because this phase is a decision gate and
must not change runtime APIs.

## Risks

- If Phase F starts now, package consumers would inherit a reward-label contract
  that still requires repository edits for every new runtime id.
- The runtime package boundary would be blurred by `DomainSeed` rebuild coupling
  unless Phase F explicitly keeps domain-pack rebuild policy outside the package
  or introduces a package-neutral rebuild recipe.
- Adapter support is local and in-process only. That is acceptable for this
  extraction decision, but external adapter behavior must remain a later plan.

## Required Next Step

Run the Phase E1 hardening plan before revisiting extraction. The hardening
plan should remove the reward-label runtime allowlist, replace domain-specific
preference grouping with descriptor-derived grouping, and add fake runtime
contract tests that validate labels and label reports without contacts/mobile
contract edits.
