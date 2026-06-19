# Plan 0025 Phase B: Runtime Consumer Inversion

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status

Completed on 2026-06-19. Activated after
[0025 Phase A](../completed/0025-phase-a-internal-runtime-kernel-hardening.md)
completed and runtime descriptors became available to replay and reward
consumers.

Phase A already moved replay and reward-label capability decisions onto
runtime descriptors. This phase narrows the remaining work to episode-quality
inversion, shared capability-status semantics, regression coverage, and docs
synchronization.

Implementation complete as of 2026-06-19 in the main workspace. Completion
evidence:

- `synthesis.runtime` owns a shared sanitized runtime capability vocabulary:
  `supported`, `unsupported`, `insufficient_evidence`, and `malformed`.
- `synthesis.episode_quality` accepts an optional runtime registry and derives
  known-runtime and state-changing-tool diagnostics from descriptors.
- `synthesis.episode_replay` and `synthesis.reward_labels` align unsupported
  capability checks through the shared runtime vocabulary while preserving
  existing report statuses.
- Contacts, mobile, and fake descriptors are covered across quality, replay,
  reward, and runtime-contract tests.
- Validation passed:
  `uv run python scripts/validate_docs.py`,
  `uv run python -m unittest tests.test_episode_quality tests.test_episode_replay tests.test_reward_labels tests.test_runtime_contract`,
  and `uv run python -m unittest`.

## Goal

Finish inverting episode quality, executable replay, and reward-label
consumers so their core logic depends on `episode_log_v1` plus runtime
capabilities, not on contacts/mobile domain branches.

## Why This Phase

Phase A centralized runtime capability facts and moved replay/reward decisions
behind descriptors. Episode quality still owns contacts/mobile runtime and
state-changing-tool allowlists, and replay/reward still need shared terminology
for unsupported, insufficient, and malformed evidence. Phase B makes the
consumer layer prove that runtime descriptors are the extension point.

## Architecture

Consumers become capability-driven readers:

```text
episode_log_v1 -> runtime descriptor -> consumer policy -> report
```

The descriptor tells the consumer whether replay, reward labels, state-change
support, adapter execution, or other evidence is available. The consumer then
returns passed, failed, unsupported, malformed, or insufficient-evidence
decisions through existing report schemas.

## Scope

- Refactor `synthesis.episode_quality` to use runtime descriptors for known
  runtime and state-changing-tool decisions.
- Keep `synthesis.episode_replay` and `synthesis.reward_labels` descriptor
  behavior stable while aligning status vocabulary and regression tests.
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

- Modify `synthesis/episode_quality.py`: accept an optional runtime registry,
  consume descriptor-known runtime ids, and derive state-changing tools from
  descriptors.
- Modify `synthesis/runtime.py` only if a shared capability-status vocabulary
  belongs at the runtime boundary.
- Modify `synthesis/episode_replay.py` only for status-vocabulary alignment or
  regression hooks; descriptor-driven replay support already exists.
- Modify `synthesis/reward_labels.py` only for status-vocabulary alignment or
  regression hooks; descriptor-driven reward/state support already exists.
- Modify `synthesis/contracts.py` only if current report contracts need a
  sanitized unsupported-capability reason.
- Extend `tests/test_episode_quality.py`, `tests/test_episode_replay.py`, and
  `tests/test_reward_labels.py`.
- Update `docs/DESIGN.md`, `docs/BACKEND.md`, and `docs/DATA.md`.

## Implementation Tasks

### Task 1: Consumer Capability Vocabulary

- [x] Add tests for a common sanitized capability status vocabulary:
  `supported`, `unsupported`, `insufficient_evidence`, and `malformed`.
- [x] Decide whether the vocabulary should live in `synthesis.runtime` or stay
  local to consumers based on existing report contracts.
- [x] Ensure unsupported capability remains distinct from malformed episode
  evidence and absent evidence.
- [x] Preserve current replay/reward report statuses unless a contract change is
  explicitly required by tests.

### Task 2: Episode Quality Inversion

- [x] Write a test where `build_episode_quality_report(..., runtime_registry=...)`
  accepts a fake descriptor without adding the fake runtime to a module-level
  allowlist.
- [x] Write a test where an unknown runtime produces a sanitized unsupported
  runtime diagnostic rather than a malformed episode diagnostic.
- [x] Move `KNOWN_RUNTIMES` checks to descriptor lookup.
- [x] Move `STATE_CHANGING_TOOLS` checks to descriptor-derived
  `state_changing_tools`.
- [x] Preserve contacts/mobile quality report decisions.

### Task 3: Replay Inversion

- [x] Keep the existing fake replay-support tests passing.
- [x] Confirm replay unsupported runtime semantics line up with the shared
  vocabulary chosen in Task 1.
- [x] Keep rebuild execution domain-owned; replay should keep resolving runtime
  capability through descriptors, not new domain-specific branches.

### Task 4: Reward Inversion

- [x] Keep the existing fake reward-capability and state-changing-tool tests
  passing.
- [x] Confirm reward unsupported runtime semantics line up with the shared
  vocabulary chosen in Task 1.
- [x] Preserve descriptor-derived scalar reward component construction.
- [x] Preserve existing contacts/mobile scalar rewards.

### Task 5: Cross-Consumer Regression

- [x] Run a contacts fixture through quality, replay, and reward labels.
- [x] Run a mobile fixture through quality, replay, and reward labels.
- [x] Assert report schemas and existing decision semantics remain stable.

### Task 6: Docs and Validation

- [x] Document that consumers are capability-driven and domain packs remain
  responsible for business rules.
- [x] Update Phase B completion evidence in the 0025 overview.
- [x] Run `uv run python scripts/validate_docs.py`.
- [x] Run `uv run python -m unittest tests.test_episode_quality tests.test_episode_replay tests.test_reward_labels tests.test_runtime_contract`.
- [x] Run `uv run python -m unittest`.

## Acceptance Criteria

- Episode quality, replay, and reward-label consumers use runtime descriptors
  for runtime/capability decisions.
- New runtime capability can be tested without editing consumer allowlists.
- Existing contacts/mobile reports remain valid and sanitized.
- Unsupported capability is reported distinctly from malformed episode evidence.

## Follow-On

After Phase B, Phase C can add a rollout-ready runtime API because consumers
will already treat runtime capability as a first-class contract.
