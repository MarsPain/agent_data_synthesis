# Plan 0025 Phase A: Internal Runtime Kernel Hardening

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status

Active as of 2026-06-19. This is the first executable phase of
[0025-awm-runtime-phase-index](../deferred/0025-awm-runtime-phase-index.md).
Later phases remain deferred unless their own triggers are met.

## Goal

Turn the current contacts/mobile runtime protocol into an internal runtime
kernel with explicit capability descriptors and registry lookup, so new domain
runtimes can be consumed without adding domain-specific branches to replay,
reward, or rollout consumers.

## Why This Phase

Plans 0030, 0031, 0032, 0033, and 0034 created the evidence needed for this
phase: shared runtime metadata, sanitized episode logs, episode quality,
executable replay, task-contract splitting, and deterministic reward-label
export. The remaining weakness is that cross-cutting consumers still know about
specific runtime ids and tool names directly.

This phase is about internal framework robustness. It does not extract a
package, connect external MCP servers, train a reward model, or implement RL.

## Architecture

Introduce a runtime registry under the existing `synthesis.runtime` boundary.
The registry owns runtime descriptors: runtime identity, supported capabilities,
state-changing tools, rebuild seed resolution, adapter support labels, and
episode/replay/reward eligibility. Domain packs still own their state schema,
tools, importers, task generators, scripted policies, and verifiers.

Consumers should ask the registry for runtime capability instead of hard-coding
runtime ids such as `contacts_fixture` and `mobile_messages_fixture`.

## Scope

- Add an internal runtime descriptor record for contacts and mobile runtimes.
- Add a runtime registry with deterministic registration and lookup.
- Move runtime capability facts out of replay/reward modules where possible:
  supported runtime ids, state-changing tools, and rebuild seed resolution.
- Keep existing public schemas stable:
  `runtime_metadata_v1`, `episode_log_v1`, `episode_replay_report_v1`,
  `reward_label_v1`, and `reward_label_report_v1`.
- Add a fake/minimal runtime descriptor in tests to prove the registry is not
  contacts/mobile-specific.

## Out of Scope

- Creating an `awm_runtime` package.
- Changing sample, rejection, manifest, or release schemas.
- Training reward models or collecting RL rollouts.
- Starting an MCP server or connecting to external tools.
- Rewriting contacts or mobile environments.

## Proposed Runtime Descriptor

```python
@dataclass(frozen=True)
class RuntimeCapabilityDescriptor:
    runtime_id: str
    runtime_version: str
    domain_id: str
    supports_rebuild: bool
    supports_checkpoint_restore: bool
    supports_episode_replay: bool
    supports_reward_labels: bool
    supports_local_adapter: bool
    state_changing_tools: tuple[str, ...]
    task_taxonomy: tuple[str, ...]
```

The implementation may choose a different name if it fits the codebase better,
but it must preserve this separation of concerns:

- runtime identity and capability live in the descriptor;
- domain business logic remains in domain modules;
- dataset release, profile decisions, and training claims stay outside runtime.

## File Map

- Modify `synthesis/runtime.py`: add descriptor records, registry helpers,
  safety validation, and contacts/mobile registrations.
- Modify `synthesis/episode_replay.py`: replace local supported-runtime and
  seed-resolution constants with registry lookups.
- Modify `synthesis/reward_labels.py`: replace known-runtime and
  state-changing-tool constants with descriptor-derived capability checks.
- Modify `synthesis/domain_pipeline.py` only if it needs a single registration
  point for contacts/mobile descriptor construction.
- Add or extend `tests/test_runtime_contract.py`: descriptor validation,
  registry lookup, fake runtime registration, safety redaction.
- Extend `tests/test_episode_replay.py` and `tests/test_reward_labels.py`:
  prove existing contacts/mobile behavior is unchanged and fake runtime
  capability is handled generically.
- Update `docs/DESIGN.md`, `docs/BACKEND.md`, `docs/DATA.md`, and
  `docs/generated/mobile-domain-pipeline-pressure.md` when implementation
  lands.

## Implementation Tasks

### Task 1: Descriptor Contract

- [ ] Add a focused failing test for a runtime descriptor that includes runtime
  id, domain id, replay support, reward-label support, adapter support, and
  state-changing tools.
- [ ] Implement the descriptor in `synthesis.runtime` without importing dataset
  assembly, profile decisions, release admission, or report builders.
- [ ] Add validation that rejects profile, release, provider prompt, credential,
  host path, or raw source fields in descriptor metadata.
- [ ] Register contacts and mobile descriptors with stable ids.

### Task 2: Registry Lookup

- [ ] Add tests for deterministic lookup, unknown runtime failure, and duplicate
  runtime registration failure.
- [ ] Implement registry helpers such as `registered_runtime_ids()`,
  `runtime_descriptor(runtime_id)`, and a safe test-only registration path.
- [ ] Ensure registry lookup is side-effect free and does not construct domain
  environments.

### Task 3: Replay Consumer Uses Registry

- [ ] Write tests showing replay support is read from the descriptor rather than
  a module-local allowlist.
- [ ] Move contacts/mobile seed resolution behind a runtime registry or
  descriptor-owned resolver boundary.
- [ ] Keep replay report output byte-compatible where schemas require stable
  fields.

### Task 4: Reward Consumer Uses Registry

- [ ] Write tests showing reward-label runtime support and state-changing-tool
  support are descriptor-derived.
- [ ] Remove reward-label module ownership of runtime allowlists.
- [ ] Preserve reward score semantics for existing contacts and mobile
  fixtures.

### Task 5: Fake Runtime Pressure Test

- [ ] Add a minimal fake descriptor that supports reward labels but not replay,
  and prove consumers report capability status without domain branches.
- [ ] Add a minimal fake descriptor that supports neither replay nor reward
  labels, and prove unsupported capability is reported as insufficient evidence
  or unsupported without crashing.
- [ ] Keep fake descriptors test-only.

### Task 6: Docs and Validation

- [ ] Update canonical docs with the runtime descriptor and registry contract.
- [ ] Update 0025 overview status notes with Phase A completion evidence.
- [ ] Run `uv run python scripts/validate_docs.py`.
- [ ] Run `uv run python -m unittest tests.test_runtime_contract tests.test_episode_replay tests.test_reward_labels`.
- [ ] Run `uv run python -m unittest`.

## Acceptance Criteria

- Runtime capability facts are centralized under `synthesis.runtime`.
- Contacts and mobile replay/reward behavior is unchanged.
- A test-only fake runtime descriptor proves consumers no longer require
  contacts/mobile branches for capability decisions.
- No public dataset, release, episode, replay, or reward schema changes are
  introduced.
- Runtime descriptors reject dataset-release, profile-promotion, provider
  prompt, credential, raw source, and host-path leakage.

## Follow-On

After Phase A completes, Phase B can invert replay, quality, and reward
consumers further so their core algorithms depend only on episode records plus
runtime descriptors.
