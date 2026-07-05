# Plan 0025 Phase G: Runtime Extraction Soak and Compatibility Hardening

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

## Status

Activated by explicit human direction, implemented in an isolated worktree on
2026-07-04, and completed on 2026-07-04.

Activation gates were satisfied before implementation:

- A post-E2 extraction-readiness review recorded extraction readiness through
  the Phase F activation path.
- [0025 Phase F: AWM Runtime Package Extraction](../completed/0025-phase-f-awm-runtime-package-extraction.md)
  has completed and been accepted.
- Phase F recorded `awm_runtime` as the approved in-repository package boundary.
- Existing contacts and mobile fixture runs passed with replay and reward-label
  reports enabled after Phase F and again during this Phase G soak.

The architectural contract remains: runtime contracts must remain independent
of domain packs, source governance, dataset assembly, profile decisions, release
reports, CLI wiring, and provider configuration.

## Goal

Prove the extracted runtime boundary can survive one compatibility cycle without
behavior drift, import leaks, or new domain-specific assumptions.

## Why This Phase

Phase F extracts stable runtime primitives. Extraction alone is not enough:
downstream development needs evidence that the new boundary is the default path
for future runtime work, while old `synthesis.runtime` imports remain stable long
enough for existing consumers and tests to migrate deliberately.

This phase is a soak and hardening phase. It should not move more domain logic
out of the repository and should not add new product capabilities. Its job is to
lock the package boundary, compatibility behavior, and documentation after the
mechanical extraction.

## Architecture

The intended post-Phase-F shape is:

```text
awm_runtime
  -> package-neutral runtime descriptors
  -> runtime registry and capability status
  -> runtime metadata safety checks
  -> runtime sessions and action envelopes
  -> package-neutral episode contract primitives
  -> package-neutral adapter manifest primitives

synthesis.runtime
  -> compatibility re-exports for one migration cycle

synthesis.*
  -> domain packs, candidate processing, source governance, evaluation,
     release/profile reports, CLI artifact writing, and docs
```

If Phase F keeps the extraction boundary inside `synthesis` rather than creating
`awm_runtime/`, this plan still applies by replacing `awm_runtime` with the
approved package-neutral boundary recorded by Phase F. Do not use that
flexibility to weaken the dependency rule: the runtime boundary must not import
domain packs or synthesis-owned report modules.

## Scope

- Add boundary-soak tests that import the extracted runtime package in a fresh
  Python interpreter and prove no forbidden `synthesis.*` modules are loaded.
- Add compatibility tests proving old `synthesis.runtime` imports still expose
  the same public symbols as the extracted boundary for one migration cycle.
- Update runtime consumers so new production imports use the extracted boundary
  where Phase F did not already do so.
- Add source-level guardrails that prevent new runtime consumers from re-centering
  on `synthesis.runtime` except in compatibility tests and compatibility shims.
- Run contacts and mobile representative CLI commands through replay and
  reward-label reports to prove behavior is unchanged.
- Update docs to describe the compatibility window and removal criteria.

## Out of Scope

- Moving contacts or mobile domain packs out of this repository.
- Adding a third domain. That is covered by
  [0037-domain-pack-contract-and-third-domain-probe](0037-domain-pack-contract-and-third-domain-probe.md).
- Publishing `awm_runtime` to PyPI or moving it to another repository.
- Removing `synthesis.runtime` compatibility re-exports during this phase.
- Changing public dataset, rejection, manifest, release, profile-decision, replay,
  or reward-label schemas.
- Adding external MCP servers, async orchestration, distributed workers, reward
  model training, or RL rollout collection.

## Future-State Assumptions and Adaptation Rules

- Expected extracted package: `awm_runtime`.
- Expected compatibility shim: `synthesis/runtime.py`.
- Expected package-boundary tests from Phase F:
  `tests/test_awm_runtime_package_boundary.py`.
- If Phase F splits runtime primitives across submodules, this plan should import
  from the public package exports, not private submodules.
- If Phase F decides that episode persistence remains entirely in `synthesis`,
  this plan should only soak the package-neutral episode record, hashing, and
  validation primitives that Phase F actually extracted.
- If Phase F records a compatibility window longer than one cycle, keep that
  window; this plan still documents the removal criteria but does not shorten it.

## File Map

- Modify: `tests/test_awm_runtime_package_boundary.py`
  - Extend existing package-boundary assertions from Phase F.
- Create or modify: `tests/test_runtime_extraction_compatibility.py`
  - Fresh-interpreter import checks, compatibility re-export checks, and source
    import guardrails.
- Modify: `synthesis/episode_replay.py`
  - Use extracted runtime imports if Phase F left any production imports pointed
    at `synthesis.runtime`.
- Modify: `synthesis/reward_labels.py`
  - Use extracted runtime imports if Phase F left any production imports pointed
    at `synthesis.runtime`.
- Modify: `synthesis/rollouts.py`
  - Use extracted runtime imports if Phase F left any production imports pointed
    at `synthesis.runtime`.
- Modify: `synthesis/mcp.py`
  - Use extracted runtime imports for adapter manifest/action-envelope primitives
    if Phase F left any production imports pointed at `synthesis.runtime`.
- Modify: `synthesis/domain_pipeline.py`
  - Keep domain-pack rebuild ownership in `synthesis`; import only package-neutral
    runtime contracts from the extracted boundary.
- Modify: `synthesis/runtime.py`
  - Keep compatibility re-exports thin and free of new business logic.
- Modify: `docs/DESIGN.md`, `docs/BACKEND.md`, `docs/DATA.md`,
  `docs/ROADMAP.md`, and `README.md`
  - Replace extraction-planning language with post-extraction compatibility and
    ownership language.
- Modify: `docs/generated/awm-runtime-extraction-readiness.md`
  - Record Phase F completion and Phase G soak evidence.
- Modify: `docs/exec-plans/indexes/0025-awm-runtime-phase-index.md`
  - Update 0025 status after Phase G completes.

## Implementation Tasks

### Task 1: Capture Post-Phase-F Boundary Inventory

- [x] Read the Phase F completion notes and list the approved public runtime
  exports in this plan's work notes before editing code.
- [x] Confirm whether the boundary is `awm_runtime` or another approved
  package-neutral boundary.
- [x] Confirm whether package-neutral episode primitives and adapter manifest
  primitives were extracted by Phase F.
- [x] Confirm which modules still import `synthesis.runtime` outside
  compatibility files:

```bash
rg -n "from synthesis\\.runtime|import synthesis\\.runtime" synthesis tests
```

- [x] Record the intended migration target for each production import found by
  the command. Imports inside `synthesis/runtime.py` and explicit compatibility
  tests may remain.

### Task 2: Add Fresh-Interpreter Import-Leak Tests

- [x] Add `tests/test_runtime_extraction_compatibility.py` if Phase F did not
  already create an equivalent file.
- [x] Add a test that starts a fresh Python interpreter, imports the extracted
  boundary, and asserts forbidden modules are absent from `sys.modules`.
- [x] Forbidden modules must include at least:
  `synthesis.datasets`, `synthesis.dataset_release`,
  `synthesis.profile_decisions`, `synthesis.release_pack`,
  `synthesis.release_quality`, `synthesis.sources`, `synthesis.domain_sources`,
  `synthesis.environments`, `synthesis.mobile_environment`,
  `synthesis.domain_pipeline`, `synthesis.pipeline`, and `main`.
- [x] If the extracted package is named `awm_runtime`, use this command to run the
  focused test:

```bash
uv run python -m unittest tests.test_runtime_extraction_compatibility
```

- [x] Expected result: the new import-leak test passes when the extracted package
  is package-neutral and fails if importing it loads any forbidden synthesis
  module.

### Task 3: Add Compatibility Re-Export Tests

- [x] In `tests/test_runtime_extraction_compatibility.py`, import the public
  symbols that Phase F documented as compatibility re-exports from both the
  extracted boundary and `synthesis.runtime`.
- [x] Assert old and new imports point at the same objects for the stable symbols
  Phase F extracted. The expected symbol set should include the Phase-F-approved
  equivalents of:
  `RuntimeCapabilityDescriptor`, `RuntimeRegistry`,
  `runtime_capability_status`, `runtime_descriptor`, `RuntimeMetadata`,
  `runtime_metadata_from_environment`, `RuntimeActionRequest`,
  `RuntimeActionResult`, `RuntimeSession`, and `EnvironmentRuntime`.
- [x] If Phase F extracted episode primitives, add compatibility assertions for
  the extracted episode record/hash/validation symbols that Phase F marks stable.
- [x] Do not assert compatibility for domain-owned descriptor construction,
  domain-specific rebuild seeds, source-governance helpers, dataset artifact
  writing, or CLI functions.
- [x] Run:

```bash
uv run python -m unittest tests.test_runtime_extraction_compatibility
```

- [x] Expected result: compatibility imports pass without changing public dataset
  or report schemas.

### Task 4: Add Source Import Guardrails

- [x] Add a source-level test that scans production modules and fails when new
  runtime-facing consumers import from `synthesis.runtime` instead of the
  extracted boundary.
- [x] The allowlist should be narrow:
  `synthesis/runtime.py`, compatibility tests, and any explicit transitional file
  documented by Phase F.
- [x] Scan at least these production modules:
  `synthesis/domain_pipeline.py`, `synthesis/episodes.py`,
  `synthesis/episode_quality.py`, `synthesis/episode_replay.py`,
  `synthesis/reward_labels.py`, `synthesis/rollouts.py`, and `synthesis/mcp.py`.
- [x] If a module still imports `synthesis.runtime`, either migrate it to the
  extracted boundary or add a one-line rationale in the test allowlist explaining
  why Phase F requires that transitional import.
- [x] Run:

```bash
uv run python -m unittest tests.test_runtime_extraction_compatibility
```

- [x] Expected result: new production code points at the extracted boundary while
  compatibility imports remain available for callers.

### Task 5: Harden Compatibility Shim Ownership

- [x] Inspect `synthesis/runtime.py`.
- [x] Keep the file as a thin compatibility layer. It may re-export stable
  symbols from the extracted boundary and host temporary deprecation comments.
- [x] Remove or reject any new dataset release, profile decision, source
  governance, CLI, provider, contacts, or mobile business logic in
  `synthesis/runtime.py`.
- [x] If Phase F left domain-specific descriptor construction in
  `synthesis.runtime`, move that construction to a synthesis-owned runtime
  registration module or document why it must remain until a named follow-on
  plan.
- [x] Run:

```bash
uv run python -m unittest tests.test_awm_runtime_package_boundary tests.test_runtime_extraction_compatibility tests.test_runtime_contract
```

- [x] Expected result: compatibility shim tests and runtime contract tests pass.

### Task 6: Run Consumer Soak Tests

- [x] Run the focused consumer tests:

```bash
uv run python -m unittest tests.test_episode_logs tests.test_episode_quality tests.test_episode_replay tests.test_reward_labels tests.test_runtime_rollouts tests.test_mcp_adapters
```

- [x] Expected result: all focused runtime consumers pass using the extracted
  boundary or compatibility imports approved by this plan.
- [x] Run the domain pipeline and CLI tests:

```bash
uv run python -m unittest tests.test_mobile_pipeline tests.test_foundation_pipeline tests.test_cli
```

- [x] Expected result: contacts and mobile behavior remains stable.

### Task 7: Run Representative CLI Soak Commands

- [x] Run the contacts fixture with replay and reward-label reports:

```bash
uv run python main.py --write-episode-replay-report --write-reward-label-report --output-dir artifacts/foundation-runtime-extraction-soak
```

- [x] Expected result: command completes, manifest references `episodes`,
  `episode_replay_report`, `reward_labels`, and `reward_label_report`, and no raw
  prompts, credentials, source payloads, or host paths are emitted in runtime
  summaries.
- [x] Run the mobile profile with replay and reward-label reports:

```bash
uv run python main.py --run-profile tests/fixtures/run_profiles/profile-local-mobile-messages.json --write-episode-replay-report --write-reward-label-report --output-dir artifacts/mobile-runtime-extraction-soak
```

- [x] Expected result: command completes with accepted mobile samples and replay
  reports continue to record runtime-session action-envelope evidence.

### Task 8: Update Docs for the Compatibility Window

- [x] Update `docs/DESIGN.md` so runtime primitives are described as living
  behind the extracted boundary, while domain packs remain in `synthesis`.
- [x] Update `docs/BACKEND.md` so module boundaries distinguish
  `awm_runtime`-owned primitives from synthesis-owned pipeline/report modules.
- [x] Update `docs/DATA.md` so runtime metadata, descriptors, action envelopes,
  and episode contract primitives point to the extracted boundary where Phase F
  actually moved them.
- [x] Update `docs/ROADMAP.md` so Phase F extraction and Phase G soak are recorded
  before third-domain work.
- [x] Update `README.md` only if setup, commands, or public import examples change.
- [x] Update `docs/generated/awm-runtime-extraction-readiness.md` with the soak
  outcome and the remaining compatibility window.
- [x] Update `docs/exec-plans/indexes/0025-awm-runtime-phase-index.md` with the
  Phase G outcome.

### Task 9: Validation

- [x] Run documentation validation:

```bash
uv run python scripts/validate_docs.py
```

- [x] Run the focused Phase G suite:

```bash
uv run python -m unittest tests.test_awm_runtime_package_boundary tests.test_runtime_extraction_compatibility tests.test_runtime_contract tests.test_episode_logs tests.test_episode_quality tests.test_episode_replay tests.test_reward_labels tests.test_runtime_rollouts tests.test_mcp_adapters
```

- [x] Run the full suite:

```bash
uv run python -m unittest
```

- [x] Confirm the contacts and mobile CLI soak commands from Task 7 completed.
- [x] Record validation evidence in this plan before moving it to
  `../completed/`.

## Acceptance Criteria

- The extracted runtime boundary imports in a fresh interpreter without loading
  synthesis-owned domain packs, dataset/release/profile modules, source
  governance, CLI code, or provider configuration.
- `synthesis.runtime` remains a compatibility layer for stable Phase-F-extracted
  symbols.
- New production runtime consumers import the extracted boundary directly unless
  Phase F records a specific transitional exception.
- Contacts and mobile replay, reward labels, rollouts, local adapters, and
  pipeline runs behave as they did before extraction.
- Public dataset and report schemas remain stable.
- Docs clearly describe the compatibility window and removal criteria.

## Follow-On

After Phase G is accepted, activate
[0037-domain-pack-contract-and-third-domain-probe](0037-domain-pack-contract-and-third-domain-probe.md)
to prove that a new domain pack can be added without editing core runtime,
replay, reward-label, or adapter allowlists.

## Implementation Notes

- Public package boundary confirmed as `awm_runtime`.
- Package-neutral runtime primitives live in `awm_runtime.runtime`.
- Package-neutral episode transition/log, hashing, redaction, and summary
  primitives live in `awm_runtime.episodes`.
- Adapter manifest construction remains `synthesis.mcp`-owned; Phase F did not
  extract adapter manifest primitives into `awm_runtime`.
- Repository-owned contacts/mobile default descriptor construction remains in
  `synthesis.runtime_registry` because descriptor rebuild seeds are domain-pack
  concerns.
- `synthesis.runtime` and `synthesis.episodes` remain one-cycle compatibility
  shims. New runtime-facing production imports should use `awm_runtime` or
  `synthesis.runtime_registry`.
- Source import guardrails scan runtime-facing production modules and allow only
  explicit compatibility shims/tests to import `synthesis.runtime` or
  `synthesis.episodes`.

## Validation Evidence

- `uv run python -m unittest tests.test_runtime_extraction_compatibility`
  failed before implementation because the Phase G compatibility test module did
  not exist.
- `uv run python -m unittest tests.test_runtime_extraction_compatibility`
  passed with 5 tests after adding fresh-interpreter import-leak,
  compatibility re-export, registry convenience, episode re-export, and source
  guardrail coverage.
- `uv run python -m unittest tests.test_awm_runtime_package_boundary tests.test_runtime_extraction_compatibility tests.test_runtime_contract`
  passed with 27 tests.
- `uv run python -m unittest tests.test_episode_logs tests.test_episode_quality tests.test_episode_replay tests.test_reward_labels tests.test_runtime_rollouts tests.test_mcp_adapters`
  passed with 49 tests.
- `uv run python -m unittest tests.test_mobile_pipeline tests.test_foundation_pipeline tests.test_cli`
  passed with 84 tests.
- `uv run python main.py --write-episode-replay-report --write-reward-label-report --output-dir artifacts/foundation-runtime-extraction-soak`
  completed with `accepted=2 rejected=1`.
- `uv run python main.py --run-profile tests/fixtures/run_profiles/profile-local-mobile-messages.json --write-episode-replay-report --write-reward-label-report --output-dir artifacts/mobile-runtime-extraction-soak`
  completed with `accepted=4 rejected=0`.
- Contacts and mobile soak manifests referenced `episodes`,
  `episode_replay_report`, `reward_labels`, and `reward_label_report`.
- Contacts and mobile replay reports passed and recorded runtime methods
  `rebuild`, `runtime_metadata`, and `execute_action` with no direct registry
  execution methods.
- Runtime summary artifact scans found no raw prompt, provider payload,
  credential, source payload, profile path, host path, or known fixture-path
  leakage.
- `uv run python scripts/validate_docs.py` passed.
- `uv run python -m unittest tests.test_awm_runtime_package_boundary tests.test_runtime_extraction_compatibility tests.test_runtime_contract tests.test_episode_logs tests.test_episode_quality tests.test_episode_replay tests.test_reward_labels tests.test_runtime_rollouts tests.test_mcp_adapters`
  passed with 76 tests.
- `uv run python -m unittest` passed with 416 tests.
