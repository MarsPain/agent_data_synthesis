# Plan 0025 Phase B: Runtime Consumer Inversion

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status

Deferred. Activate only after
[0025 Phase A](../active/0025-phase-a-internal-runtime-kernel-hardening.md) has completed
and runtime descriptors are available to consumers.

## Goal

Invert episode quality, executable replay, and reward-label consumers so their
core logic depends on `episode_log_v1` plus runtime capabilities, not on
contacts/mobile domain branches.

## Why This Phase

Phase A centralizes runtime capability facts. Phase B makes the consumers prove
that centralization is useful. A generic Agent runtime-backed synthesis
framework should allow a new runtime to participate in replay or reward-label
workflows by registering capabilities, not by editing each consumer module.

## Architecture

Consumers become capability-driven readers:

```text
episode_log_v1 -> runtime descriptor -> consumer policy -> report
```

The descriptor tells the consumer whether replay, reward labels, state-change
support, adapter execution, or other evidence is available. The consumer then
returns passed, failed, unsupported, or insufficient-evidence decisions through
existing report schemas.

## Scope

- Refactor `synthesis.episode_quality`, `synthesis.episode_replay`, and
  `synthesis.reward_labels` to use runtime descriptors for capability decisions.
- Keep report schemas and artifact names stable.
- Distinguish unsupported runtime capability from malformed episode evidence.
- Add tests using contacts, mobile, and fake descriptors.

## Out of Scope

- Adding a new production domain.
- Changing task generation, candidate processing, or verifier behavior.
- Adding rollout collection.
- External MCP server integration.
- Package extraction.

## File Map

- Modify `synthesis/episode_quality.py`: consume descriptor-known runtime ids
  and capability labels where relevant.
- Modify `synthesis/episode_replay.py`: use descriptor-driven rebuild/replay
  support and unsupported-capability reporting.
- Modify `synthesis/reward_labels.py`: use descriptor-driven reward-label and
  state-change support.
- Modify `synthesis/contracts.py` only if current report contracts need a
  sanitized unsupported-capability reason.
- Extend `tests/test_episode_quality.py`, `tests/test_episode_replay.py`, and
  `tests/test_reward_labels.py`.
- Update `docs/DESIGN.md`, `docs/BACKEND.md`, and `docs/DATA.md`.

## Implementation Tasks

### Task 1: Consumer Capability Vocabulary

- [ ] Add tests for a common sanitized capability status vocabulary:
  `supported`, `unsupported`, `insufficient_evidence`, and `malformed`.
- [ ] Implement the vocabulary close to `synthesis.runtime` or the consumer
  module that owns the report contract.
- [ ] Ensure unsupported capability does not count as executable failure unless
  the existing report contract already requires a failed check.

### Task 2: Episode Quality Inversion

- [ ] Write a test where a fake descriptor marks episode-quality support as
  disabled and the quality report returns a sanitized unsupported capability
  decision.
- [ ] Move known-runtime checks to descriptor lookup.
- [ ] Preserve contacts/mobile quality report decisions.

### Task 3: Replay Inversion

- [ ] Write a test where a fake descriptor supports replay and a separate fake
  descriptor does not.
- [ ] Refactor replay runtime validation to use descriptor capability instead of
  a module-level runtime allowlist.
- [ ] Keep rebuild execution domain-owned; the consumer should call the runtime
  resolver, not import new domain-specific branches.

### Task 4: Reward Inversion

- [ ] Write a test where state support is derived from descriptor
  state-changing-tool metadata.
- [ ] Refactor scalar reward component construction to use descriptor capability
  and tool-side-effect metadata where available.
- [ ] Preserve existing contacts/mobile scalar rewards.

### Task 5: Cross-Consumer Regression

- [ ] Run a contacts fixture through quality, replay, and reward labels.
- [ ] Run a mobile fixture through quality, replay, and reward labels.
- [ ] Assert report schemas and existing decision semantics remain stable.

### Task 6: Docs and Validation

- [ ] Document that consumers are capability-driven and domain packs remain
  responsible for business rules.
- [ ] Update Phase B completion evidence in the 0025 overview.
- [ ] Run `uv run python scripts/validate_docs.py`.
- [ ] Run `uv run python -m unittest tests.test_episode_quality tests.test_episode_replay tests.test_reward_labels tests.test_runtime_contract`.
- [ ] Run `uv run python -m unittest`.

## Acceptance Criteria

- Episode quality, replay, and reward-label consumers use runtime descriptors
  for runtime/capability decisions.
- New runtime capability can be tested without editing consumer allowlists.
- Existing contacts/mobile reports remain valid and sanitized.
- Unsupported capability is reported distinctly from malformed episode evidence.

## Follow-On

After Phase B, Phase C can add a rollout-ready runtime API because consumers
will already treat runtime capability as a first-class contract.
