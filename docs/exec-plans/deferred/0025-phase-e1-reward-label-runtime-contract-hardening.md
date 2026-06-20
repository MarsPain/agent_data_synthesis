# Plan 0025 Phase E1: Reward Label Runtime Contract Hardening

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status

Deferred after [0025 Phase E](../completed/0025-phase-e-extraction-readiness-review.md)
returned `continue_hardening` on 2026-06-20. Activate this before revisiting
Phase F package extraction.

## Goal

Remove reward-label runtime-contract assumptions that force core contract edits
for every new runtime, while preserving current contacts and mobile label
artifacts.

## Why This Phase

Phase E found that replay, quality, rollout, and adapter consumers mostly use
runtime descriptors or sessions, but reward-label validation still enforces
`synthesis.contracts.REWARD_LABEL_RUNTIMES`. That blocks runtime package
extraction because a new runtime would still require editing core reward-label
allowlists.

## Scope

- Replace reward-label runtime id allowlist validation with descriptor-backed
  or report-local runtime evidence.
- Replace contacts/mobile tool-name preference grouping with descriptor-derived
  grouping or a runtime-owned grouping declaration.
- Add fake runtime tests proving label and label-report contracts validate
  without adding the fake runtime to a module-level allowlist.
- Preserve current contacts and mobile reward-label outputs where possible.

## Out of Scope

- Package extraction.
- Reward model training or RL optimization.
- Moving domain packs out of this repository.
- Changing dataset release, profile promotion, source governance, or adapter
  protocols except where they consume reward-label runtime evidence.

## File Map

- Modify `synthesis/contracts.py`.
- Modify `synthesis/reward_labels.py`.
- Extend `tests/test_reward_labels.py`.
- Extend `tests/test_runtime_contract.py` if descriptor fields are added.
- Update `docs/generated/awm-runtime-extraction-readiness.md` or a successor
  generated report if the extraction decision is revisited.

## Implementation Tasks

### Task 1: Contract Pressure Tests

- [ ] Add failing tests for a fake reward-capable runtime whose labels and
  label reports validate without changing a contract-level runtime allowlist.
- [ ] Add regression tests for existing contacts and mobile label/report
  validation.

### Task 2: Descriptor-Derived Runtime Validation

- [ ] Remove or retire `REWARD_LABEL_RUNTIMES` as a hard contract gate.
- [ ] Validate reward-label runtime ids against descriptor-backed evidence or
  runtime ids observed in the corresponding report inputs.
- [ ] Keep malformed and unsupported runtime semantics explicit.

### Task 3: Preference Group Generalization

- [ ] Replace `_preference_group_id` contacts/mobile tool branches with
  descriptor taxonomy, a runtime-owned grouping field, or a stable generic
  fallback.
- [ ] Preserve deterministic ranking and tie-breaking.

### Task 4: Validation

- [ ] Run `uv run python scripts/validate_docs.py`.
- [ ] Run `uv run python -m unittest tests.test_reward_labels tests.test_runtime_contract`.
- [ ] Run `uv run python -m unittest`.

## Acceptance Criteria

- Adding a new reward-capable runtime no longer requires editing a
  reward-label contract allowlist.
- Contacts and mobile reward-label reports remain valid.
- Reward preference groups are deterministic without contacts/mobile-specific
  tool branches.
- Phase F remains deferred until a new extraction-readiness review returns
  `ready_for_extraction_plan`.
