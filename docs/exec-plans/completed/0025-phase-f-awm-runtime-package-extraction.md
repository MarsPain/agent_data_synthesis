# Plan 0025 Phase F: AWM Runtime Package Extraction

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

## Status

Activated by explicit human direction, implemented in the main workspace on
2026-07-04, and accepted on 2026-07-04.

Implementation chose an in-repository `awm_runtime` package boundary rather
than PyPI publication or a separate repository. `awm_runtime` owns stable
runtime and episode primitives; repository-owned contacts/mobile default
descriptor construction lives in `synthesis.runtime_registry`; `synthesis.runtime`
and `synthesis.episodes` remain compatibility shims for one migration cycle.

## Goal

Extract the stable internal runtime kernel into an `awm_runtime`-style package
boundary while preserving compatibility for the synthesis pipeline and existing
runtime consumers.

## Why This Phase

Extraction is justified only when the runtime kernel has become shared
infrastructure for synthesis, replay, reward labels, rollout collection, and
adapter surfaces. The extracted unit should be the runtime contract and
execution evidence model, not contacts or mobile domain fixtures.

## Architecture

The package boundary separates:

```text
awm_runtime
  -> runtime descriptors
  -> runtime registry primitives
  -> runtime sessions
  -> action request/result envelopes
  -> episode transition/log contracts

agent_data_synthesis
  -> domain packs
  -> default contacts/mobile runtime descriptor construction
  -> task generation
  -> policy execution orchestration
  -> verification and quality
  -> dataset/release/profile reports
```

Domain packs stay in this repository initially. They depend on `awm_runtime`;
`awm_runtime` must not depend on domain packs or dataset assembly.

## Scope

- Create a package boundary for runtime descriptors, sessions, envelopes,
  safety validation, and episode log primitives.
- Add compatibility imports or shims so existing `synthesis.runtime` consumers
  continue to work during migration.
- Move only stable runtime primitives that a future readiness review marks
  extraction-eligible.
- Keep domain packs, source governance, profile decisions, dataset release, and
  quality reports in this repository.
- Add cross-boundary tests proving synthesis and consumers still work.

## Out of Scope

- Moving contacts/mobile domain packs out of the repository.
- Publishing to PyPI or creating a separate repository unless a later plan
  explicitly covers release operations.
- Changing public dataset artifacts.
- Adding external MCP servers.
- Adding RL training or distributed rollout infrastructure.

## Implementation Tasks

### Task 1: Package Boundary Skeleton

- [x] Add package directory and module exports for the extraction-eligible
  symbols identified by a future readiness review.
- [x] Add tests proving `awm_runtime` imports do not import `synthesis.datasets`,
  `synthesis.dataset_release`, `synthesis.profile_decisions`, or domain packs.
- [x] Add compatibility re-exports in `synthesis.runtime`.

### Task 2: Move Runtime Primitives

- [x] Move runtime descriptors, descriptor registry, runtime metadata safety
  validation, session protocols, and action envelopes.
- [x] Keep symbol names stable through compatibility re-exports.
- [x] Run runtime contract tests after each move.

### Task 3: Move Episode Primitives

- [x] Move episode transition/log primitives and redaction/hash helpers if Phase
  E marked them stable.
- [x] Keep dataset-specific episode persistence in `synthesis` if it depends on
  artifact manifests.
- [x] Preserve `episode_log_v1` validation behavior.

### Task 4: Update Consumers

- [x] Update replay, reward labels, rollout, adapter, and domain pipeline code
  to consume the package boundary.
- [x] Keep synthesis-owned report writing, manifest updates, and CLI flags in
  `synthesis`.
- [x] Run focused consumer tests after each module migration.

### Task 5: Compatibility and Migration

- [x] Add tests proving old import paths still work for one release cycle.
- [x] Document compatibility shims and planned removal criteria.
- [x] Ensure docs and examples use the new package boundary where appropriate.

### Task 6: Validation

- [x] Run `uv run python scripts/validate_docs.py`.
- [x] Run `uv run python -m unittest tests.test_awm_runtime_package_boundary tests.test_runtime_contract tests.test_episode_logs tests.test_episode_replay tests.test_reward_labels tests.test_mcp_adapters`.
- [x] Run `uv run python -m unittest`.
- [x] Run representative CLI commands for contacts and mobile profile runs with
  replay and reward-label reports enabled.

## Acceptance Criteria

- Runtime primitives live behind an `awm_runtime` package boundary or equivalent
  extraction boundary approved by a future readiness review.
- `awm_runtime` has no dependency on dataset release, profile decisions, source
  governance, CLI, or domain packs.
- Existing synthesis pipeline behavior and public artifacts remain stable.
- Compatibility re-exports preserve current internal imports during migration.
- Extraction is documented and validated by full tests.

## Implementation Notes

- Public package boundary: `awm_runtime`.
- Runtime primitives moved to `awm_runtime.runtime`.
- Episode transition/log, hashing, redaction, and summary primitives moved to
  `awm_runtime.episodes`.
- Repository-owned default runtime descriptors moved to
  `synthesis.runtime_registry` because contacts/mobile rebuild seeds are
  domain-pack concerns, not package-neutral runtime primitives.
- `synthesis.runtime` and `synthesis.episodes` are compatibility re-export
  modules only.
- `synthesis.__init__` now lazily exports pipeline entrypoints so importing
  `synthesis.contracts` does not import dataset/domain pipeline modules.
- `synthesis.contracts` lazily imports `CandidateTask` only when candidate-task
  validation runs, keeping `awm_runtime` import-neutral with respect to task
  generation.

## Validation Evidence

- `uv run python -m unittest tests.test_awm_runtime_package_boundary` failed
  before implementation because `awm_runtime` did not exist.
- `uv run python -m unittest tests.test_awm_runtime_package_boundary tests.test_runtime_contract tests.test_episode_logs tests.test_episode_replay tests.test_reward_labels tests.test_mcp_adapters tests.test_runtime_rollouts`
  passed with 61 tests.
- `uv run python scripts/validate_docs.py` passed.
- `uv run python -m unittest` passed with 411 tests.
- `uv run python main.py --write-episode-replay-report --write-reward-label-report --output-dir artifacts/foundation-phase-f-validation`
  completed with `accepted=2 rejected=1`.
- `uv run python main.py --run-profile tests/fixtures/run_profiles/profile-local-mobile-messages.json --write-episode-replay-report --write-reward-label-report --output-dir artifacts/mobile-phase-f-validation`
  completed with `accepted=4 rejected=0`.

## Follow-On

After Phase F,
[0025 Phase G: Runtime Extraction Soak and Compatibility Hardening](0025-phase-g-runtime-extraction-soak-and-compatibility-hardening.md)
ran before third-domain work, external MCP servers, distributed rollout
workers, or separate repository publishing. Each later capability still
requires a new plan and explicit trigger.
