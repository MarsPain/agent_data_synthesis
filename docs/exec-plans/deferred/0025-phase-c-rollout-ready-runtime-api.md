# Plan 0025 Phase C: Rollout-Ready Runtime API

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status

Deferred. Activate only after
[0025 Phase B](0025-phase-b-consumer-inversion.md) has completed and consumers
can use runtime descriptors generically.

## Goal

Add the minimum runtime API needed for future Agentic rollout collection without
implementing RL algorithms, reward model training, distributed workers, or GPU
infrastructure.

## Why This Phase

Reward labels in plan 0034 make training-signal consumers visible, but the
framework still lacks a narrow rollout-facing runtime interface. Phase C adds
the execution semantics that future rollout collectors need: reset, checkpoint,
restore, list tools, execute action, observe transition, and export episode.

This phase should make future RL work possible without making this repository an
RL training system.

## Architecture

Introduce a runtime action boundary:

```text
RuntimeSession
  -> reset/rebuild
  -> checkpoint/restore
  -> list_tools
  -> execute_action(ActionRequest)
  -> ActionResult
  -> EpisodeTransition
```

Domain packs keep their domain-specific tool implementations and verification
rules. The runtime API only standardizes how an agent or collector interacts
with those tools.

## Scope

- Define internal action request/result records for runtime execution.
- Add a `RuntimeSession` or equivalent runtime-facing object for one
  environment instance.
- Implement contacts and mobile adapters to the session API.
- Add a deterministic local rollout collector that executes scripted policies
  through the runtime API and exports `episode_log_v1`.
- Keep rollout collection opt-in and test-only or diagnostic at first.

## Out of Scope

- RL algorithms, policy optimization, preference optimization, PPO, DPO, GRPO,
  or reward model training.
- Async/distributed rollout workers.
- External MCP servers.
- Changing dataset release or profile promotion.
- Changing default `main.py` output.

## File Map

- Modify or extend `synthesis/runtime.py`: action request/result records,
  session protocol, session capability validation.
- Modify `synthesis/domain_pipeline.py`: expose runtime session construction
  for contacts/mobile bundles.
- Modify `synthesis/execution.py` only if existing policy execution should
  share action-envelope code with the runtime session.
- Add `synthesis/rollouts.py` or similarly named module for deterministic
  diagnostic rollout collection.
- Add `tests/test_runtime_rollouts.py`.
- Extend `tests/test_runtime_contract.py`, `tests/test_episode_logs.py`, and
  `tests/test_episode_replay.py`.
- Update `docs/DESIGN.md`, `docs/BACKEND.md`, `docs/DATA.md`, and
  `docs/ROADMAP.md`.

## Implementation Tasks

### Task 1: Action Request and Result Contracts

- [ ] Add failing tests for `runtime_action_request_v1` with tool name,
  sanitized arguments, runtime id, and optional action id.
- [ ] Add failing tests for `runtime_action_result_v1` with status,
  observation hash, state-change hash, error class, and side-effect summary.
- [ ] Implement contracts without raw prompts, credentials, host paths, or raw
  source payloads.

### Task 2: Runtime Session Protocol

- [ ] Add a protocol test that requires reset/rebuild, checkpoint/restore,
  list-tools, and execute-action behavior.
- [ ] Implement the session protocol in `synthesis.runtime`.
- [ ] Adapt contacts and mobile domain bundles to expose runtime sessions.

### Task 3: Existing Execution Compatibility

- [ ] Add tests proving current scripted policy execution can be represented as
  runtime action requests and results.
- [ ] Share serialization logic between existing trajectory events and runtime
  action results where it reduces duplication.
- [ ] Preserve public sample trajectory shape.

### Task 4: Diagnostic Rollout Collector

- [ ] Add a deterministic rollout collector that accepts a runtime descriptor,
  scripted policy, and max step count.
- [ ] Export sanitized `episode_log_v1` records from rollout execution.
- [ ] Add contacts/mobile tests proving generated rollout episodes can be
  consumed by replay and reward labels.

### Task 5: Safety and Limits

- [ ] Add max-step enforcement and unsupported-tool rejection.
- [ ] Add checkpoint/restore tests proving failed rollout steps do not corrupt
  reusable runtime state.
- [ ] Ensure raw arguments and observations are redacted or hashed according to
  existing episode rules.

### Task 6: Docs and Validation

- [ ] Document that rollout collection is diagnostic infrastructure, not RL
  training.
- [ ] Update 0025 overview with Phase C completion evidence.
- [ ] Run `uv run python scripts/validate_docs.py`.
- [ ] Run `uv run python -m unittest tests.test_runtime_rollouts tests.test_runtime_contract tests.test_episode_replay tests.test_reward_labels`.
- [ ] Run `uv run python -m unittest`.

## Acceptance Criteria

- Contacts and mobile runtimes can be driven through a shared action/session
  API.
- A diagnostic rollout collector can emit replayable, reward-label-compatible
  episodes.
- No RL training, external workers, or default CLI behavior changes are added.
- Runtime action/result records are sanitized and validated.

## Follow-On

After Phase C, Phase D can generalize the local adapter surface so runtime
sessions can be consumed through a manifest/envelope boundary.
