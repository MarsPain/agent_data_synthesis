# Plan 0025 Phase E2: Runtime Session Replay Boundary Hardening

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status

Planned on 2026-06-29. Implementation completed on 2026-06-29; awaiting
follow-on extraction-readiness review before Phase F activation.

Phase F remains deferred until a fresh extraction-readiness review returns
`ready_for_extraction_plan`.

## Implementation Decision

Executable replay keeps domain-pack rebuild ownership in
`synthesis.domain_pipeline`: descriptors provide the rebuild seed, the domain
pipeline rebuilds the candidate runtime, and replay consumes the rebuilt bundle
through `DomainPipelineBundle.runtime_session()`.

Replay does not call `RuntimeSession.rebuild(...)` directly because contacts
and mobile rebuild policy is still domain-pack behavior, not package-boundary
behavior. `RuntimeSession.rebuild(...)` remains covered by runtime contract
tests as a session affordance, while replay now proves the package-facing
execution boundary by driving every supported action through
`RuntimeSession.execute_action(...)`, `RuntimeActionRequest`, and
`RuntimeActionResult`.

## Goal

Make executable episode replay exercise the `RuntimeSession` boundary end to
end before AWM runtime package extraction.

## Why This Phase

Phase E returned `continue_hardening`, and Phase E1 removed the reward-label
runtime contract blockers. The remaining package-boundary risk is narrower:
`RuntimeSession.rebuild` exists for the package-shaped session API, but the
current executable replay consumer still rebuilds through
`DomainPipelineBundle` and executes actions directly through the raw tool
registry.

That means replay proves the domain pipeline can rebuild and execute supported
runtimes, but it does not yet prove a future `awm_runtime` package boundary can
serve a real execution consumer through runtime sessions and action envelopes.

This phase turns replay into that proof without extracting a package.

## Architecture

The intended boundary is:

```text
domain pack
  -> RuntimeCapabilityDescriptor
  -> RuntimeSession
  -> RuntimeActionRequest / RuntimeActionResult
  -> episode_log_v1
  -> executable replay consumer
```

Domain packs still own domain-specific rebuild policy, fixture state, tool
registries, scripted policies, verifiers, and source importers. The runtime
session boundary owns cross-domain execution semantics: runtime identity,
checkpoint/restore, rebuild, list-tools, action-envelope execution, sanitized
observations, and state-change evidence.

## Current Gap

Before this phase, `synthesis.episode_replay.replay_episode(...)`:

- resolves replay support through runtime descriptors;
- builds a base domain pipeline bundle from the descriptor rebuild seed;
- rebuilds a domain pipeline bundle for the candidate;
- replays actions by calling `bundle.registry.execute(...)` directly.

The last two bullets keep executable replay coupled to the repository-local
domain bundle shape. They should be narrowed so domain-pack rebuild stays in
`synthesis.domain_pipeline`, but replay executes actions through
`RuntimeSession` and `RuntimeActionRequest`.

## Scope

- Add tests that fail while executable replay bypasses `RuntimeSession`.
- Route replay action execution through `RuntimeSession.execute_action(...)`
  and `RuntimeActionResult` records.
- Exercise `RuntimeSession.rebuild(...)` from a real replay path or document a
  deliberate alternative if implementation evidence shows direct session
  rebuild is not the right package-facing API.
- Keep domain-pack rebuild ownership outside `synthesis.runtime` and outside any
  future `awm_runtime` package boundary.
- Preserve existing contacts and mobile replay report schemas and decisions.
- Preserve sanitization rules for replay summaries, action arguments,
  observations, state changes, prompts, credentials, source payloads, and host
  paths.
- Update the 0025 phase index and generated readiness note only after the
  implementation evidence is available.

## Out of Scope

- Extracting an `awm_runtime` package.
- Moving contacts or mobile domain packs out of this repository.
- Changing default dataset sample, rejection, manifest, quality report, profile
  decision, or dataset release schemas.
- Reward model training, Agentic RL rollout collection, PPO, DPO, GRPO, or GPU
  infrastructure.
- External MCP server discovery or remote adapter execution.
- Async orchestration, durable queues, cancellation, worker pools, or per-role
  resource accounting from plan 0014.
- Semantic duplicate detection from `TD-0002`.

## File Map

- Modify `synthesis/episode_replay.py`:
  route supported replay execution through runtime sessions and action
  envelopes.
- Modify `synthesis/domain_pipeline.py` only if a small session-rebuild helper
  is needed to keep domain-pack rebuild policy explicit.
- Modify `synthesis/runtime.py` only if `RuntimeSession` needs a minimal
  package-boundary affordance or clearer error semantics.
- Extend `tests/test_episode_replay.py` with session-boundary assertions.
- Extend `tests/test_runtime_contract.py` when `RuntimeSession.rebuild` behavior
  changes or becomes part of replay evidence.
- Extend `tests/test_runtime_rollouts.py` or `tests/test_mcp_adapters.py` only
  if shared runtime-session behavior changes.
- Update `docs/generated/awm-runtime-extraction-readiness.md` after
  implementation evidence is available.
- Update `docs/exec-plans/deferred/0025-awm-runtime-phase-index.md` when this
  phase completes or when the readiness review decision changes.

## Implementation Tasks

### Task 1: Replay Boundary Pressure Tests

- [x] Add a focused test proving supported episode replay executes actions
  through `RuntimeSession.execute_action(...)` instead of direct
  `ToolRegistry.execute(...)`.
- [x] Cover both contacts and mobile replay paths.
- [x] Add or extend fake/minimal runtime coverage so unsupported runtimes remain
  descriptor-driven and do not require a replay allowlist.
- [x] Assert replay summaries remain sanitized and schema-compatible.

### Task 2: Runtime-Session Replay Execution

- [x] Change replay setup so domain-pack rebuild creates or exposes a
  `RuntimeSession` for the replayed candidate runtime.
- [x] Re-execute each episode action by constructing a `RuntimeActionRequest`
  and calling `RuntimeSession.execute_action(...)`.
- [x] Compare replayed `RuntimeActionResult.observation_hash` and
  `state_change_hash` against episode transition hashes.
- [x] Preserve current failed-check semantics for malformed arguments, unsupported
  tools, runtime mismatches, rebuild failures, and metadata drift.

### Task 3: Rebuild Ownership Decision

- [x] Decide whether replay should call `RuntimeSession.rebuild(...)` directly
  or call a domain-pipeline helper that returns a rebuilt `RuntimeSession`.
- [x] N/A: direct session rebuild is not used by replay; runtime contract tests
  continue to prove `RuntimeSession.rebuild(...)` works for contacts and mobile
  session affordance coverage.
- [x] If a domain-pipeline helper remains necessary, document why domain-pack
  rebuild policy is outside the runtime package boundary and mark
  `RuntimeSession.rebuild` semantics accordingly.
- [x] Ensure `synthesis.runtime` does not import domain packs, dataset release,
  profile decisions, source governance, CLI modules, or concrete contacts/mobile
  builders.

### Task 4: Documentation and Readiness Update

- [x] Update `docs/generated/awm-runtime-extraction-readiness.md` with the E2
  evidence.
- [ ] Update the 0025 phase index with the E2 outcome.
- [x] Keep Phase F deferred unless a separate fresh readiness review returns
  `ready_for_extraction_plan`.
- [x] Document any remaining blockers as `continue_hardening` or
  `keep_internal` evidence.

### Task 5: Validation

- [x] Run `uv run python scripts/validate_docs.py`.
- [x] Run `uv run python -m unittest tests.test_episode_replay tests.test_runtime_contract`.
- [x] Run `uv run python -m unittest tests.test_runtime_rollouts tests.test_mcp_adapters tests.test_reward_labels`.
- [x] Run `uv run python -m unittest`.
- [x] Run representative CLI commands for contacts and mobile with
  `--write-episode-replay-report` and `--write-reward-label-report` enabled.

## Validation Evidence

- `uv run python -m unittest tests.test_episode_replay` failed before the
  implementation because replay reports did not record `execute_action` as
  runtime boundary evidence.
- `uv run python -m unittest tests.test_episode_replay tests.test_runtime_contract`
  passed with 28 tests.
- `uv run python -m unittest tests.test_runtime_rollouts tests.test_mcp_adapters tests.test_reward_labels`
  passed with 22 tests.
- `uv run python scripts/validate_docs.py` passed.
- `uv run python -m unittest` passed with 406 tests.
- `uv run python main.py --write-episode-replay-report --write-reward-label-report --output-dir artifacts/foundation-e2-validation`
  completed with `accepted=2 rejected=1`.
- `uv run python main.py --run-profile tests/fixtures/run_profiles/profile-local-mobile-messages.json --write-episode-replay-report --write-reward-label-report --output-dir artifacts/mobile-e2-validation`
  completed with `accepted=4 rejected=0`.
- Both generated replay reports record `runtime_methods_used` including
  `execute_action` and `registry_methods_used` as an empty list.

## Acceptance Criteria

- Executable replay for supported contacts and mobile episodes executes actions
  through `RuntimeSession` and action envelopes.
- Replay no longer needs direct registry execution in the main action replay
  path.
- Adding a fake unsupported runtime still reports descriptor-derived
  `runtime_supported` failure without editing replay allowlists.
- Replay report schemas, sanitization, and existing contacts/mobile decisions
  remain stable.
- Domain-pack rebuild ownership is explicit and does not leak domain builders
  into `synthesis.runtime`.
- The readiness document records whether this phase changes the extraction
  decision to `ready_for_extraction_plan`, leaves it at `continue_hardening`, or
  recommends `keep_internal`.

## Follow-On

After this phase completes, run a fresh extraction-readiness review. Only move
[0025 Phase F: AWM Runtime Package Extraction](../deferred/0025-phase-f-awm-runtime-package-extraction.md)
to active if that review returns `ready_for_extraction_plan`.
