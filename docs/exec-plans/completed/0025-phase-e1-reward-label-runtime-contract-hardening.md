# Plan 0025 Phase E1: Reward Label Runtime Contract Hardening

## Status

Completed on 2026-06-20 after
[0025 Phase E](0025-phase-e-extraction-readiness-review.md) returned
`continue_hardening`.

Phase F remains deferred until a fresh extraction-readiness review returns
`ready_for_extraction_plan`.

## Goal

Remove reward-label runtime-contract assumptions that force core contract edits
for every new runtime, while preserving current contacts and mobile label
artifacts.

## Why This Phase

Phase E found that replay, quality, rollout, and adapter consumers mostly use
runtime descriptors or sessions, but reward-label validation still enforced a
contract-level reward runtime allowlist. That blocked runtime package extraction
because a new runtime would still require editing core reward-label contracts.

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

## Implementation Summary

- Removed `synthesis.contracts.REWARD_LABEL_RUNTIMES` as a hard reward-label
  contract gate.
- Kept `reward_label_v1.runtime_id` structurally validated as a non-empty
  string.
- Made `reward_label_report_v1` validate each label summary runtime id against
  report-local `observed.runtime_counts` evidence.
- Added `RuntimeCapabilityDescriptor.reward_preference_groups` so runtimes own
  reward preference grouping declarations.
- Moved contacts and mobile preference group mappings into their runtime
  descriptors, preserving existing contacts/mobile group ids.
- Added a deterministic generic preference-group fallback for runtimes that do
  not declare a specific grouping.

## Changed Files

- `synthesis/contracts.py`
- `synthesis/reward_labels.py`
- `synthesis/runtime.py`
- `tests/test_contracts.py`
- `tests/test_reward_labels.py`
- `tests/test_runtime_contract.py`
- `docs/generated/awm-runtime-extraction-readiness.md`

## Implementation Tasks

### Task 1: Contract Pressure Tests

- [x] Add failing tests for a fake reward-capable runtime whose labels and
  label reports validate without changing a contract-level runtime allowlist.
- [x] Add regression tests for existing contacts and mobile label/report
  validation.

### Task 2: Descriptor-Derived Runtime Validation

- [x] Remove or retire `REWARD_LABEL_RUNTIMES` as a hard contract gate.
- [x] Validate reward-label runtime ids against descriptor-backed evidence or
  runtime ids observed in the corresponding report inputs.
- [x] Keep malformed and unsupported runtime semantics explicit.

### Task 3: Preference Group Generalization

- [x] Replace `_preference_group_id` contacts/mobile tool branches with
  descriptor taxonomy, a runtime-owned grouping field, or a stable generic
  fallback.
- [x] Preserve deterministic ranking and tie-breaking.

### Task 4: Validation

- [x] Run `uv run python scripts/validate_docs.py`.
- [x] Run `uv run python -m unittest tests.test_reward_labels tests.test_runtime_contract`.
- [x] Run `uv run python -m unittest`.

## Acceptance Criteria

- [x] Adding a new reward-capable runtime no longer requires editing a
  reward-label contract allowlist.
- [x] Contacts and mobile reward-label reports remain valid.
- [x] Reward preference groups are deterministic without contacts/mobile-specific
  tool branches.
- [x] Phase F remains deferred until a new extraction-readiness review returns
  `ready_for_extraction_plan`.

## Validation Evidence

- `uv run python scripts/validate_docs.py` passed.
- `uv run python -m unittest tests.test_reward_labels tests.test_runtime_contract`
  passed with 28 tests.
- `uv run python -m unittest` passed with 403 tests.
