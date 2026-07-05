# Plan 0038: Runtime Compatibility Shim Retirement and Context Sync

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

## Status

Completed on 2026-07-05.

Validation evidence:

- `uv run python -m unittest tests.test_runtime_extraction_compatibility`
  failed before migration for the expected shim-file and old-import guardrails.
- `uv run python -m unittest tests.test_episode_logs tests.test_runtime_contract tests.test_episode_quality tests.test_episode_replay tests.test_reward_labels tests.test_mcp_adapters tests.test_workspace_environment`
  passed after import migration.
- `uv run python -m unittest tests.test_awm_runtime_package_boundary tests.test_runtime_extraction_compatibility`
  passed after shim deletion.
- `uv run python -m unittest tests.test_runtime_contract tests.test_episode_quality tests.test_episode_replay tests.test_reward_labels tests.test_runtime_rollouts tests.test_mcp_adapters tests.test_domain_pack_contract`
  passed with 70 tests.
- `uv run python -m unittest` passed with 450 tests.
- `uv run python scripts/validate_docs.py` passed.
- `uv run python main.py --run-profile tests/fixtures/run_profiles/workspace-tasks-fixture.json --write-episode-replay-report --write-reward-label-report --output-dir artifacts/workspace-shim-retirement-probe`
  completed with `accepted=4`, `rejected=0`, replay decision `passed`, and
  reward-label decision `passed`.
- `uv run python main.py --run-profile tests/fixtures/run_profiles/workspace-tasks-fixture.json --write-evaluation-report --write-profile-decision-report --output-dir artifacts/workspace-shim-retirement-evaluation`
  completed with `accepted=4`, `rejected=0`, evaluation decision `passed`,
  profile promotion `passed`, and async/semantic duplicate work still deferred.

## Goal

Remove the one-cycle `synthesis.runtime` and `synthesis.episodes`
compatibility shims after the `awm_runtime` extraction soak and third-domain
probe, then sync root and canonical docs so they describe the current
three-domain runtime boundary consistently.

## Why This Plan

Plan 0025 Phase F extracted package-neutral runtime and episode primitives into
`awm_runtime`. Phase G kept `synthesis.runtime` and `synthesis.episodes` as
temporary one-cycle compatibility shims while adding import guardrails. Plan
0037 then added `workspace_tasks_fixture` as a third deterministic domain pack
without core replay, reward-label, adapter, or runtime allowlists.

The compatibility cycle has now produced the intended evidence. Keeping the
old imports longer makes future runtime-facing work ambiguous: new tests and
domain packs can keep depending on transitional modules even though the
canonical boundary is `awm_runtime` plus repository-owned descriptor lookup in
`synthesis.runtime_registry`.

There is also a small context drift: some root and canonical entrypoints still
describe two deterministic domains or contacts/mobile-only descriptor ownership
even though workspace is now part of the current implementation shape. Fix that
in the same change set so future plans start from a consistent map.

## Architecture

The post-plan shape is:

```text
awm_runtime
  -> package-neutral runtime descriptors, sessions, action envelopes,
     runtime metadata safety, and episode primitives

synthesis.runtime_registry
  -> repository-owned contacts/mobile/workspace default descriptor construction
     and lookup helpers

synthesis domain packs
  -> contacts, mobile messages, and workspace tasks state/tool/policy behavior

tests and consumers
  -> import package-neutral primitives from awm_runtime
  -> import repository default descriptor lookup from synthesis.runtime_registry
```

`synthesis.runtime` and `synthesis.episodes` should be removed rather than
converted into deeper redirect stubs. Import failures are acceptable because
this repository has not published `awm_runtime` as a separate package and the
Phase G documentation explicitly limited the shims to one migration cycle.

## Scope

- Add failing guardrail tests that require the compatibility shim files to be
  gone and forbid imports from `synthesis.runtime` or `synthesis.episodes`.
- Migrate tests that still import package-neutral runtime or episode primitives
  through the compatibility shims.
- Migrate tests that need default runtime descriptor lookup to
  `synthesis.runtime_registry`.
- Delete `synthesis/runtime.py` and `synthesis/episodes.py`.
- Remove compatibility re-export assertions from package-boundary tests.
- Update root and canonical docs so they describe three deterministic domains,
  direct `awm_runtime` imports, and the closed compatibility window.
- Preserve current public dataset, manifest, quality, evaluation, replay,
  reward-label, release, and adapter artifact schemas.

## Out of Scope

- Publishing `awm_runtime` to PyPI or moving it to another repository.
- Moving domain packs out of this repository.
- Adding workspace profile-local source ingestion.
- Adding external MCP servers, browser automation, SaaS connectors, or real
  user data access.
- Activating async orchestration, distributed workers, semantic duplicate
  detection, reward-model training, or Agentic RL.
- Changing default CLI behavior or default artifact families.

## File Map

- Modify: `tests/test_runtime_extraction_compatibility.py`
  - Replace shim re-export tests with removal and import-forbid guardrails.
- Modify: `tests/test_awm_runtime_package_boundary.py`
  - Remove compatibility re-export checks and keep package-boundary checks.
- Modify: `tests/test_episode_logs.py`
  - Import episode primitives from `awm_runtime` and runtime metadata from
    `awm_runtime`.
- Modify: `tests/test_runtime_contract.py`
  - Import package-neutral primitives from `awm_runtime` and default registry
    helpers from `synthesis.runtime_registry`.
- Modify: `tests/test_episode_quality.py`, `tests/test_episode_replay.py`,
  `tests/test_reward_labels.py`, `tests/test_mcp_adapters.py`,
  `tests/test_workspace_environment.py`
  - Replace compatibility-shim imports with `awm_runtime` or
    `synthesis.runtime_registry` imports according to ownership.
- Delete: `synthesis/runtime.py`
- Delete: `synthesis/episodes.py`
- Modify: `README.md`
  - Describe three deterministic domains and direct runtime imports.
- Modify: `docs/DESIGN.md`, `docs/BACKEND.md`, `docs/DATA.md`,
  `docs/ROADMAP.md`, `docs/generated/awm-runtime-extraction-readiness.md`
  - Close the compatibility window and align domain/runtime ownership language.
- Modify: `docs/PLANS.md`, `docs/exec-plans/active/README.md`
  - Track this plan as active.

## Implementation Tasks

### Task 1: Add Shim Removal Guardrail Tests

- [x] Modify `tests/test_runtime_extraction_compatibility.py`.
- [x] Remove
  `test_synthesis_runtime_reexports_boundary_owned_runtime_symbols`,
  `test_synthesis_runtime_registry_convenience_functions_match_with_explicit_registry`,
  and `test_synthesis_episodes_reexports_boundary_episode_symbols`.
- [x] Add import parsing helpers near the top of the file:

```python
import ast


def _python_files_under(paths: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for root in paths:
        root_path = Path(root)
        if root_path.is_file() and root_path.suffix == ".py":
            files.append(root_path)
            continue
        if root_path.is_dir():
            files.extend(
                path
                for path in root_path.rglob("*.py")
                if ".venv" not in path.parts
            )
    return sorted(files)


def _removed_shim_import_violations(paths: tuple[str, ...]) -> list[str]:
    removed_modules = {"synthesis.runtime", "synthesis.episodes"}
    violations: list[str] = []
    for path in _python_files_under(paths):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in removed_modules:
                violations.append(f"{path}:{node.lineno}: from {node.module} import ...")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in removed_modules:
                        violations.append(f"{path}:{node.lineno}: import {alias.name}")
    return violations
```

- [x] Add the removal tests:

```python
    def test_runtime_compatibility_shim_files_are_removed(self) -> None:
        self.assertFalse(Path("synthesis/runtime.py").exists())
        self.assertFalse(Path("synthesis/episodes.py").exists())

    def test_no_python_imports_reference_removed_runtime_shims(self) -> None:
        violations = _removed_shim_import_violations(("synthesis", "tests"))
        self.assertEqual(violations, [])
```

- [x] Keep
  `test_awm_runtime_import_does_not_load_forbidden_synthesis_modules` and update
  `test_runtime_facing_production_modules_do_not_import_compatibility_shims` so
  it no longer allowlists `synthesis/episodes.py`.
- [x] Run:

```bash
uv run python -m unittest tests.test_runtime_extraction_compatibility
```

- [x] Expected result before migration: failure because `synthesis/runtime.py`,
  `synthesis/episodes.py`, and current tests still import the removed shim
  modules.

### Task 2: Migrate Remaining Test Imports

- [x] In `tests/test_episode_logs.py`, replace:

```python
from synthesis.episodes import build_episode_log, summarize_episode_for_quality
from synthesis.episodes import deterministic_content_hash
from synthesis.runtime import RuntimeMetadata
```

with:

```python
from awm_runtime import (
    RuntimeMetadata,
    build_episode_log,
    deterministic_content_hash,
    summarize_episode_for_quality,
)
```

- [x] In `tests/test_runtime_contract.py`, import package-neutral symbols from
  `awm_runtime`:

```python
from awm_runtime import (
    EnvironmentRuntime,
    RuntimeActionRequest,
    RuntimeActionResult,
    RuntimeCapabilityDescriptor,
    RuntimeRegistry,
    RuntimeSession,
    validate_runtime_metadata_safety,
)
```

- [x] In `tests/test_runtime_contract.py`, import default registry helpers from
  `synthesis.runtime_registry`:

```python
from synthesis.runtime_registry import registered_runtime_ids, runtime_descriptor
```

- [x] In `tests/test_episode_quality.py`, `tests/test_episode_replay.py`, and
  `tests/test_reward_labels.py`, replace `from synthesis.episodes import
  build_episode_log` with:

```python
from awm_runtime import build_episode_log
```

- [x] In those same files, replace fake registry imports from
  `synthesis.runtime` with:

```python
from awm_runtime import RuntimeCapabilityDescriptor, RuntimeRegistry
```

- [x] In `tests/test_episode_replay.py`, replace runtime session/action imports
  with:

```python
from awm_runtime import RuntimeActionRequest, RuntimeSession
```

- [x] In `tests/test_mcp_adapters.py`, replace default descriptor lookup imports
  with:

```python
from synthesis.runtime_registry import runtime_descriptor
```

  and replace descriptor primitive imports with:

```python
from awm_runtime import RuntimeCapabilityDescriptor
```

- [x] In `tests/test_workspace_environment.py`, replace:

```python
from synthesis.runtime import validate_runtime_metadata_safety
```

with:

```python
from awm_runtime import validate_runtime_metadata_safety
```

- [x] Run:

```bash
uv run python -m unittest tests.test_episode_logs tests.test_runtime_contract tests.test_episode_quality tests.test_episode_replay tests.test_reward_labels tests.test_mcp_adapters tests.test_workspace_environment
```

- [x] Expected result after import migration but before shim deletion: focused
  tests pass except the removal guardrail still fails because shim files exist.

### Task 3: Delete Compatibility Shims and Simplify Boundary Tests

- [x] Delete `synthesis/runtime.py`.
- [x] Delete `synthesis/episodes.py`.
- [x] In `tests/test_awm_runtime_package_boundary.py`, remove checks that import
  `synthesis.runtime` or `synthesis.episodes`.
- [x] Keep package-neutral checks that prove `awm_runtime` imports do not load
  forbidden synthesis modules.
- [x] Run:

```bash
uv run python -m unittest tests.test_awm_runtime_package_boundary tests.test_runtime_extraction_compatibility
```

- [x] Expected result: both focused boundary test modules pass, and no Python
  file imports `synthesis.runtime` or `synthesis.episodes`.

### Task 4: Update Runtime and Domain Context Docs

- [x] Update `README.md`:
  - change "two deterministic domains" to "three deterministic domains";
  - list contacts, mobile messages, and workspace tasks in "What Works Now";
  - change the default descriptor registry wording from contacts/mobile to
    contacts/mobile/workspace;
  - remove the one-cycle compatibility-shim statement.
- [x] Update `docs/DESIGN.md`:
  - replace the one-cycle compatibility-shim paragraph with a direct statement
    that runtime-facing production code imports `awm_runtime` or
    `synthesis.runtime_registry`;
  - replace contacts/mobile-only allowlist wording with
    contacts/mobile/workspace where it describes current supported domains;
  - keep external MCP, async orchestration, RL, and package publishing deferred.
- [x] Update `docs/BACKEND.md`:
  - remove `synthesis.runtime` and `synthesis.episodes` from proposed module
    boundaries;
  - describe `synthesis.runtime_registry` as contacts/mobile/workspace
    descriptor ownership;
  - update workflow text that says replay rebuilds only contacts/mobile fixture
    runtimes when the current boundary also supports workspace.
- [x] Update `docs/DATA.md`:
  - ensure runtime and episode entity descriptions name `awm_runtime` directly;
  - remove any remaining compatibility-shim wording.
- [x] Update `docs/ROADMAP.md`:
  - record this plan as the post-0037 compatibility cleanup step;
  - keep async orchestration and semantic duplicate detection deferred under
    their existing trigger conditions.
- [x] Update `docs/generated/awm-runtime-extraction-readiness.md`:
  - change the Phase G "compatibility window remains one migration cycle"
    language to "closed by plan 0038";
  - record that shim removal requires direct imports from `awm_runtime` and
    `synthesis.runtime_registry`.
- [x] Run:

```bash
uv run python scripts/validate_docs.py
```

- [x] Expected result: documentation validation passes.

### Task 5: Run Behavioral Regression Checks

- [x] Run focused runtime and consumer tests:

```bash
uv run python -m unittest tests.test_runtime_contract tests.test_episode_quality tests.test_episode_replay tests.test_reward_labels tests.test_runtime_rollouts tests.test_mcp_adapters tests.test_domain_pack_contract
```

- [x] Run full test suite:

```bash
uv run python -m unittest
```

- [x] Run documentation validation:

```bash
uv run python scripts/validate_docs.py
```

- [x] Run representative workspace replay and reward-label command:

```bash
uv run python main.py --run-profile tests/fixtures/run_profiles/workspace-tasks-fixture.json --write-episode-replay-report --write-reward-label-report --output-dir artifacts/workspace-shim-retirement-probe
```

- [x] Run representative workspace evaluation and profile decision command:

```bash
uv run python main.py --run-profile tests/fixtures/run_profiles/workspace-tasks-fixture.json --write-evaluation-report --write-profile-decision-report --output-dir artifacts/workspace-shim-retirement-evaluation
```

- [x] Expected result: all tests and docs validation pass; both workspace
  commands produce accepted candidates, no replay/reward regressions, and no
  compatibility-shim imports reappear.

### Task 6: Complete Plan Lifecycle Updates

- [x] Move this plan from `docs/exec-plans/active/` to
  `docs/exec-plans/completed/` after implementation is accepted.
- [x] Add completion date and validation evidence to the plan status section.
- [x] Update `docs/PLANS.md`:
  - remove this plan from `Active`;
  - add it to `Completed`;
  - keep plan 0014 and `TD-0002` deferred unless their triggers are met.
- [x] Update `docs/exec-plans/active/README.md` and
  `docs/exec-plans/completed/README.md`.
- [x] Run:

```bash
uv run python scripts/validate_docs.py
```

- [x] Expected result: plan lifecycle links remain valid and docs validation
  passes.

## Acceptance Criteria

- `synthesis/runtime.py` and `synthesis/episodes.py` no longer exist.
- No Python source or test file imports `synthesis.runtime` or
  `synthesis.episodes`.
- Package-neutral runtime and episode primitives are imported from
  `awm_runtime`.
- Repository-owned default descriptor lookup is imported from
  `synthesis.runtime_registry`.
- Runtime package-boundary tests still prove `awm_runtime` does not load
  forbidden synthesis modules.
- Root and canonical docs consistently describe three deterministic domains and
  the closed compatibility window.
- Public dataset, manifest, quality, evaluation, replay, reward-label, release,
  and adapter artifact schemas remain unchanged.
- Async orchestration, semantic duplicate detection, external MCP servers, RL,
  and package publishing remain deferred.

## Validation

- `uv run python -m unittest tests.test_runtime_extraction_compatibility`
- `uv run python -m unittest tests.test_awm_runtime_package_boundary tests.test_runtime_extraction_compatibility`
- `uv run python -m unittest tests.test_runtime_contract tests.test_episode_quality tests.test_episode_replay tests.test_reward_labels tests.test_runtime_rollouts tests.test_mcp_adapters tests.test_domain_pack_contract`
- `uv run python -m unittest`
- `uv run python scripts/validate_docs.py`
- `uv run python main.py --run-profile tests/fixtures/run_profiles/workspace-tasks-fixture.json --write-episode-replay-report --write-reward-label-report --output-dir artifacts/workspace-shim-retirement-probe`
- `uv run python main.py --run-profile tests/fixtures/run_profiles/workspace-tasks-fixture.json --write-evaluation-report --write-profile-decision-report --output-dir artifacts/workspace-shim-retirement-evaluation`
