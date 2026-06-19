# Plan 0025 Phase F: AWM Runtime Package Extraction

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status

Deferred behind
[0025 Phase E](0025-phase-e-extraction-readiness-review.md). Do not activate
until the extraction readiness report returns `ready_for_extraction_plan`.

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

The package boundary should separate:

```text
awm_runtime
  -> runtime descriptors
  -> runtime sessions
  -> action request/result envelopes
  -> episode transition/log contracts
  -> adapter manifest primitives

agent_data_synthesis
  -> domain packs
  -> task generation
  -> policy execution orchestration
  -> verification and quality
  -> dataset/release/profile reports
```

Domain packs may stay in this repository initially. They depend on
`awm_runtime`; `awm_runtime` must not depend on domain packs or dataset
assembly.

## Scope

- Create a package boundary for runtime descriptors, sessions, envelopes,
  safety validation, and episode log primitives.
- Add compatibility imports or shims so existing `synthesis.runtime` consumers
  continue to work during migration.
- Move only stable runtime primitives that Phase E marked extraction-eligible.
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

## File Map

Exact paths depend on the packaging decision from Phase E. If extraction stays
in-repository first, use:

- Create `awm_runtime/` package with runtime primitives.
- Modify `synthesis/runtime.py` to re-export compatibility symbols.
- Modify `synthesis/episodes.py`, `synthesis/episode_replay.py`,
  `synthesis/reward_labels.py`, `synthesis/mcp.py`, and
  `synthesis/domain_pipeline.py` to import from the package boundary.
- Add `tests/test_awm_runtime_package_boundary.py`.
- Extend existing runtime, episode, replay, reward, adapter, and pipeline tests.
- Update `pyproject.toml` only if packaging metadata requires it.
- Update `docs/DESIGN.md`, `docs/BACKEND.md`, `docs/DATA.md`,
  `docs/SECURITY.md`, `docs/ROADMAP.md`, and `README.md`.

## Implementation Tasks

### Task 1: Package Boundary Skeleton

- [ ] Add package directory and module exports for the extraction-eligible
  symbols identified by Phase E.
- [ ] Add tests proving `awm_runtime` imports do not import `synthesis.datasets`,
  `synthesis.dataset_release`, `synthesis.profile_decisions`, or domain packs.
- [ ] Add compatibility re-exports in `synthesis.runtime`.

### Task 2: Move Runtime Primitives

- [ ] Move runtime descriptors, descriptor registry, runtime metadata safety
  validation, session protocols, and action envelopes.
- [ ] Keep symbol names stable through compatibility re-exports.
- [ ] Run runtime contract tests after each move.

### Task 3: Move Episode Primitives

- [ ] Move episode transition/log primitives and redaction/hash helpers if Phase
  E marked them stable.
- [ ] Keep dataset-specific episode persistence in `synthesis` if it depends on
  artifact manifests.
- [ ] Preserve `episode_log_v1` validation behavior.

### Task 4: Update Consumers

- [ ] Update replay, reward labels, rollout, adapter, and domain pipeline code
  to consume the package boundary.
- [ ] Keep synthesis-owned report writing, manifest updates, and CLI flags in
  `synthesis`.
- [ ] Run focused consumer tests after each module migration.

### Task 5: Compatibility and Migration

- [ ] Add tests proving old import paths still work for one release cycle.
- [ ] Document compatibility shims and planned removal criteria.
- [ ] Ensure docs and examples use the new package boundary where appropriate.

### Task 6: Validation

- [ ] Run `uv run python scripts/validate_docs.py`.
- [ ] Run `uv run python -m unittest tests.test_awm_runtime_package_boundary tests.test_runtime_contract tests.test_episode_logs tests.test_episode_replay tests.test_reward_labels tests.test_mcp_adapters`.
- [ ] Run `uv run python -m unittest`.
- [ ] Run representative CLI commands for contacts and mobile profile runs with
  replay and reward-label reports enabled.

## Acceptance Criteria

- Runtime primitives live behind an `awm_runtime` package boundary or equivalent
  extraction boundary approved by Phase E.
- `awm_runtime` has no dependency on dataset release, profile decisions, source
  governance, CLI, or domain packs.
- Existing synthesis pipeline behavior and public artifacts remain stable.
- Compatibility re-exports preserve current internal imports during migration.
- Extraction is documented and validated by full tests.

## Follow-On

After Phase F, future work may consider external MCP servers, distributed
rollout workers, or separate repository publishing, but each requires a new
plan and explicit trigger.
