# Plan 0037: Domain Pack Contract and Third Domain Probe

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status

Deferred until one of these activation paths is true:

- Preferred path: [0025 Phase G](../completed/0025-phase-g-runtime-extraction-soak-and-compatibility-hardening.md)
  has completed and accepted the post-extraction runtime boundary.
- Fallback path: a post-E2 readiness review records `keep_internal` or
  `continue_hardening`, and the recorded decision explicitly says a third-domain
  probe is the next best way to pressure-test the runtime/domain-pack boundary
  without extracting `awm_runtime`.

This plan was written before Phase F and Phase G executed. The approved runtime
package boundary is `awm_runtime`; use it directly unless a later 0025 decision
records a different approved boundary.

## Goal

Add a third deterministic domain pack that proves new domains can join the
synthesis pipeline without editing core replay, reward-label, adapter, or
runtime allowlists.

## Why This Plan

Contacts and mobile proved that the framework can support more than one domain,
but both were added before the runtime boundary was fully extracted or soaked.
The next architectural proof is not another runtime refactor; it is a new domain
that uses the stabilized contract from the outside.

The third domain should be deterministic, local, and small. Its purpose is to
pressure-test domain-pack interfaces, not to expand product surface area or add
external integrations.

## Proposed Third Domain

Use a synthetic workspace task domain:

- Domain id: `workspace_tasks_fixture`
- Environment: local deterministic workspace containing projects, task records,
  lightweight documents, and comments.
- Tools:
  - `search_workspace_items`: read-only lookup over projects, tasks, documents,
    and comments.
  - `create_workspace_task`: state-changing task creation with project, title,
    priority, and due-label fields.
  - `add_workspace_comment`: state-changing comment creation on a workspace task.
- Task types:
  - `workspace_item_lookup`
  - `workspace_task_creation`
  - `workspace_comment_update`
  - `workspace_branch_fallback`
- Profile fixture:
  `tests/fixtures/run_profiles/workspace-tasks-fixture.json`
  with generation mode `workspace_fixture`.

If implementation evidence shows a different third deterministic domain is
strictly easier to implement while preserving the same architectural pressure,
the domain may change only if the replacement still has one read-only tool, at
least two state-changing tools, scripted policy support, exact-answer/state
verification, runtime descriptor/session support, replay support, reward-label
support, and held-out evaluation coverage.

## Architecture

The intended shape is:

```text
workspace domain pack
  -> workspace environment
  -> workspace tools
  -> workspace deterministic tasks and scripted policies
  -> workspace verifier state support
  -> runtime descriptor/session registration
  -> domain pipeline bundle
  -> replay / reward-label / rollout / adapter / evaluation consumers
```

Domain-specific behavior stays in workspace-owned modules. Core consumers must
learn about the new runtime through descriptors, domain bundle registration, and
existing domain-aware report plumbing. Do not add workspace-specific branches to
episode replay, reward labels, episode quality, local adapters, dataset release,
or profile decisions except where a domain registry or domain pipeline resolver
is explicitly responsible for routing domains.

## Scope

- Add a deterministic workspace environment with checkpoint, restore, rebuild,
  metadata, and runtime metadata support.
- Add workspace tools with schemas, side-effect metadata, deterministic
  observations, and state-change summaries.
- Add deterministic workspace candidates and scripted solution policies.
- Register the workspace domain in the domain pipeline using the current domain
  registration mechanism. If Phase G introduced a stronger registry, use that
  registry instead of extending conditionals.
- Add a runtime descriptor for `workspace_tasks_fixture`.
- Add replay, reward-label, episode-quality, local-adapter, and rollout coverage
  through existing runtime/session contracts.
- Add domain-aware held-out evaluation and release/profile evidence for the new
  domain.
- Add a workspace run profile and CLI coverage.
- Update docs and generated pressure notes.

## Out of Scope

- Profile-local workspace source ingestion. The first workspace domain is
  deterministic fixture-only.
- External workspace APIs, browser automation, SaaS connectors, remote MCP
  servers, or real user data.
- New generated-code roles or sandbox policy changes.
- Semantic duplicate detection.
- Async orchestration or distributed workers.
- Changing public dataset schemas beyond existing domain-aware fields.
- Training a reward model or running RL algorithms.

## Future-State Assumptions and Adaptation Rules

- If `awm_runtime` exists after Phase G, workspace runtime descriptors, sessions,
  metadata, and action envelopes must import from `awm_runtime`.
- If runtime remains internal, use the approved runtime import boundary from the
  latest 0025 decision and keep the same no-core-allowlist acceptance criteria.
- If Phase G introduced source-level tests that forbid new `synthesis.runtime`
  imports, update the workspace modules to satisfy those tests.
- If Phase G introduced a formal domain-pack registry, register workspace there.
  If not, extend `synthesis.domain_pipeline.build_domain_pipeline_bundle` in the
  smallest possible way and document this as remaining domain-router coupling.
- If Phase G moved adapter manifest primitives to `awm_runtime`, local adapter
  tests should consume those primitives through the new package path.

## File Map

- Create: `synthesis/workspace_environment.py`
  - Workspace records, fixture construction, state inspection, checkpoint,
    restore, rebuild, metadata, and runtime metadata.
- Create: `synthesis/workspace_tools.py`
  - Tool registry builder and tool implementations for workspace lookup, task
    creation, and comment creation.
- Create: `synthesis/workspace_tasks.py`
  - Deterministic workspace candidates and scripted solution policies.
- Modify: `synthesis/domain_pipeline.py`
  - Register or route `workspace_tasks_fixture`.
- Modify: `synthesis/runtime.py` or the extracted runtime registration module
  chosen by Phase G
  - Add the workspace runtime descriptor in synthesis-owned registration code.
- Modify: `synthesis/run_profiles.py`
  - Add `workspace_fixture` generation mode.
- Modify: `synthesis/verification.py`
  - Add exact-state checks for workspace task/comment outcomes if the existing
    verifier cannot express them generically.
- Modify: `synthesis/evaluation.py`
  - Add a workspace held-out suite and domain-aware resolver entry.
- Modify: `synthesis/rollouts.py`
  - Add scripted diagnostic rollout support only through generic runtime-session
    hooks; avoid workspace-specific scoring logic.
- Modify: `tests/fixtures/run_profiles/workspace-tasks-fixture.json`
  - Add deterministic workspace diagnostic profile.
- Create: `tests/test_workspace_environment.py`
- Create: `tests/test_workspace_tools.py`
- Create: `tests/test_workspace_pipeline.py`
- Create or modify: `tests/test_domain_pack_contract.py`
  - No-core-allowlist and domain-pack contract checks.
- Modify: `tests/test_runtime_contract.py`
- Modify: `tests/test_episode_quality.py`
- Modify: `tests/test_episode_replay.py`
- Modify: `tests/test_reward_labels.py`
- Modify: `tests/test_runtime_rollouts.py`
- Modify: `tests/test_mcp_adapters.py`
- Modify: `tests/test_evaluation.py`
- Modify: `tests/test_profile_decisions.py`
- Modify: `tests/test_dataset_release.py`
- Modify: `tests/test_cli.py`
- Modify: `docs/DESIGN.md`, `docs/BACKEND.md`, `docs/DATA.md`,
  `docs/ROADMAP.md`, and `docs/generated/mobile-domain-pipeline-pressure.md`
  or create a new generated note if the mobile-specific note has become too
  narrow.

## Implementation Tasks

### Task 1: Add Workspace Environment Contract Tests

- [ ] Create `tests/test_workspace_environment.py`.
- [ ] Test that `WorkspaceTasksEnvironment.create_fixture(tmp_path)` creates a
  deterministic environment with at least two projects, three tasks, two
  documents, and two comments.
- [ ] Test `search_workspace_items(query="launch", kind="task")` returns a
  deterministic task summary without raw filesystem paths.
- [ ] Test `create_workspace_task(project_id="project_alpha", title="Prepare launch checklist", priority="high", due_label="this_week")`
  records a task that can be inspected by state helpers.
- [ ] Test `add_workspace_comment(task_id=created_task_id, comment="Added launch checklist owner.")`
  records a comment that can be inspected by state helpers.
- [ ] Test checkpoint/restore rolls back created tasks and comments.
- [ ] Test `metadata()` returns `environment.id == "workspace_tasks_fixture"`.
- [ ] Test `runtime_metadata()` uses runtime id `workspace_tasks_fixture`,
  excludes dataset/profile/release/provider/source raw payload fields, and passes
  runtime metadata safety validation.
- [ ] Run:

```bash
uv run python -m unittest tests.test_workspace_environment
```

- [ ] Expected result before implementation: tests fail because the workspace
  environment does not exist.

### Task 2: Implement Workspace Environment

- [ ] Create `synthesis/workspace_environment.py`.
- [ ] Define immutable records for workspace projects, tasks, documents, and
  comments.
- [ ] Implement `WorkspaceTasksEnvironment.create_fixture(output_dir: Path)`.
- [ ] Implement deterministic search, task creation, comment creation,
  state-inspection helpers, checkpoint, restore, rebuild, `metadata()`, and
  `runtime_metadata()`.
- [ ] Keep all state local to the environment. Do not read host files, network
  resources, credentials, browser profiles, or user data.
- [ ] Run:

```bash
uv run python -m unittest tests.test_workspace_environment
```

- [ ] Expected result: workspace environment tests pass.

### Task 3: Add Workspace Tool Registry Tests

- [ ] Create `tests/test_workspace_tools.py`.
- [ ] Test `build_workspace_tool_registry(environment)` exports exactly
  `search_workspace_items`, `create_workspace_task`, and
  `add_workspace_comment`.
- [ ] Test each tool rejects missing required arguments and wrong argument types.
- [ ] Test `search_workspace_items` is read-only and returns a deterministic
  observation summary.
- [ ] Test `create_workspace_task` and `add_workspace_comment` return
  state-change summaries that identify changed state without raw internal state
  dumps.
- [ ] Test the registry side-effect metadata marks only task creation and comment
  creation as state-changing.
- [ ] Run:

```bash
uv run python -m unittest tests.test_workspace_tools
```

- [ ] Expected result before implementation: tests fail because workspace tools
  do not exist.

### Task 4: Implement Workspace Tools

- [ ] Create `synthesis/workspace_tools.py`.
- [ ] Implement `build_workspace_tool_registry(environment)`.
- [ ] Implement `search_workspace_items`, `create_workspace_task`, and
  `add_workspace_comment` using the existing `ToolRegistry` and schema patterns.
- [ ] Ensure all observations and state-change summaries are deterministic and
  sanitized.
- [ ] Run:

```bash
uv run python -m unittest tests.test_workspace_tools tests.test_workspace_environment
```

- [ ] Expected result: workspace environment and tool tests pass.

### Task 5: Add Workspace Candidate and Policy Tests

- [ ] Create `tests/test_workspace_pipeline.py`.
- [ ] Test `generate_workspace_fixture_candidates(seed)` returns at least four
  candidates covering lookup, task creation, comment update, and branch fallback.
- [ ] Test each candidate exports through the existing `CandidateTask` contract
  without adding public workspace-only schema fields.
- [ ] Test `scripted_workspace_solution_policy(task)` uses only workspace tools
  and produces deterministic tool steps.
- [ ] Test workspace expected-state declarations can express created task and
  added comment outcomes.
- [ ] Run:

```bash
uv run python -m unittest tests.test_workspace_pipeline
```

- [ ] Expected result before implementation: tests fail because workspace task
  generation and policy code do not exist.

### Task 6: Implement Workspace Candidates and Policies

- [ ] Create `synthesis/workspace_tasks.py`.
- [ ] Implement deterministic workspace candidates with existing `CandidateTask`
  shapes.
- [ ] Implement `scripted_workspace_solution_policy(task)` using
  `search_workspace_items`, `create_workspace_task`, and
  `add_workspace_comment`.
- [ ] Keep task-intent, policy-hint, expected-outcome, and expected-state behavior
  internal through existing task-contract conversion.
- [ ] Run:

```bash
uv run python -m unittest tests.test_workspace_pipeline
```

- [ ] Expected result: workspace candidate and policy tests pass.

### Task 7: Add Workspace Domain Bundle and Runtime Descriptor Tests

- [ ] Extend `tests/test_workspace_pipeline.py` or create
  `tests/test_domain_pack_contract.py`.
- [ ] Test `build_domain_pipeline_bundle(seed, tmp_path)` accepts
  `seed.domain == "workspace_tasks_fixture"` and returns:
  `domain_id == "workspace_tasks_fixture"`, a workspace environment, a workspace
  registry, an exact-answer verifier, a candidate generator, a policy generator,
  and a runtime session.
- [ ] Extend `tests/test_runtime_contract.py` to prove contacts, mobile, and
  workspace satisfy the shared runtime protocol.
- [ ] Add a descriptor test proving `runtime_descriptor("workspace_tasks_fixture")`
  or the Phase-G-approved descriptor lookup returns replay support,
  reward-label support, local-adapter support, state-changing tools, task
  taxonomy, and reward preference groups without editing replay or reward-label
  allowlists.
- [ ] Run:

```bash
uv run python -m unittest tests.test_workspace_pipeline tests.test_domain_pack_contract tests.test_runtime_contract
```

- [ ] Expected result before implementation: tests fail because the workspace
  domain is not registered.

### Task 8: Register Workspace Domain Pack

- [ ] Modify `synthesis/domain_pipeline.py` or the Phase-G-approved domain-pack
  registry to register `workspace_tasks_fixture`.
- [ ] Modify synthesis-owned runtime registration code to register the workspace
  runtime descriptor.
- [ ] Keep the extracted runtime package free of workspace imports. Runtime
  package tests from Phase G must still pass.
- [ ] Run:

```bash
uv run python -m unittest tests.test_workspace_pipeline tests.test_domain_pack_contract tests.test_runtime_contract tests.test_awm_runtime_package_boundary tests.test_runtime_extraction_compatibility
```

- [ ] Expected result: workspace domain registration works and runtime package
  boundary tests still pass.

### Task 9: Add Workspace Verification Support

- [ ] Add failing tests in `tests/test_workspace_pipeline.py` or
  `tests/test_task_contracts.py` for workspace expected-state checks:
  created task exists with expected project/title/priority/due label, and comment
  exists on the expected task.
- [ ] Modify `synthesis/verification.py` only if existing exact-state helpers
  cannot express the workspace state checks generically.
- [ ] Preserve contacts follow-up and mobile reminder/draft verification behavior.
- [ ] Run:

```bash
uv run python -m unittest tests.test_workspace_pipeline tests.test_task_contracts tests.test_mobile_pipeline tests.test_foundation_pipeline
```

- [ ] Expected result: workspace, contacts, and mobile verification paths pass.

### Task 10: Add Workspace Episode Consumer Coverage

- [ ] Extend `tests/test_episode_quality.py` with a workspace episode-quality
  case that reads descriptor-derived state-changing tools.
- [ ] Extend `tests/test_episode_replay.py` with a workspace replay case that
  rebuilds a fresh workspace runtime and executes actions through
  `RuntimeSession.execute_action(...)`.
- [ ] Extend `tests/test_reward_labels.py` with a workspace reward-label case
  that uses descriptor-derived reward support and preference groups.
- [ ] Extend `tests/test_runtime_rollouts.py` with a diagnostic workspace rollout
  case.
- [ ] Extend `tests/test_mcp_adapters.py` with workspace local-adapter manifest
  and action-envelope execution coverage.
- [ ] Do not add workspace-specific allowlists inside replay, reward labels,
  episode quality, rollouts, or local adapter code.
- [ ] Run:

```bash
uv run python -m unittest tests.test_episode_quality tests.test_episode_replay tests.test_reward_labels tests.test_runtime_rollouts tests.test_mcp_adapters
```

- [ ] Expected result: existing consumers handle workspace through descriptors,
  runtime sessions, action envelopes, and existing domain bundle registration.

### Task 11: Add Workspace Run Profile and CLI Coverage

- [ ] Modify `synthesis/run_profiles.py` to add `workspace_fixture` to generation
  modes.
- [ ] Create `tests/fixtures/run_profiles/workspace-tasks-fixture.json` with:
  schema version `run_profile_v1`, profile id `workspace_tasks_fixture`, dataset
  version `dataset_workspace_tasks_fixture`, profile purpose `diagnostic_probe`,
  seed domain `workspace_tasks_fixture`, and generation mode `workspace_fixture`.
- [ ] Extend `tests/test_run_profiles.py` with a passing workspace profile test
  and a rejection test for mismatched workspace source declarations if source
  fields are supplied.
- [ ] Extend `tests/test_cli.py` with a workspace fixture command that writes
  samples, rejections, manifest, quality report, episodes, replay report, reward
  labels, and reward-label report when the relevant flags are supplied.
- [ ] Run:

```bash
uv run python -m unittest tests.test_run_profiles tests.test_cli
```

- [ ] Expected result: workspace run profile and CLI coverage pass.

### Task 12: Add Domain-Aware Evaluation and Release Evidence

- [ ] Modify `synthesis/evaluation.py` to add a workspace held-out suite and
  resolver entry for `workspace_tasks_fixture`.
- [ ] Extend `tests/test_evaluation.py` with workspace suite identity and report
  generation tests.
- [ ] Extend `tests/test_profile_decisions.py` with a workspace profile-decision
  case and a mismatched-domain insufficient-evidence case.
- [ ] Extend `tests/test_dataset_release.py` with a workspace release-candidate
  evidence case and a mismatched-domain rejection case.
- [ ] Preserve contacts and mobile evaluation/report behavior.
- [ ] Run:

```bash
uv run python -m unittest tests.test_evaluation tests.test_profile_decisions tests.test_dataset_release
```

- [ ] Expected result: workspace evaluation evidence is domain-aware and
  mismatched evaluation remains insufficient for promotion or release.

### Task 13: Add No-Core-Allowlist Regression Tests

- [ ] In `tests/test_domain_pack_contract.py`, add source scans proving workspace
  support did not add workspace-specific branches to:
  `synthesis/episode_quality.py`, `synthesis/episode_replay.py`,
  `synthesis/reward_labels.py`, `synthesis/rollouts.py`,
  `synthesis/mcp.py`, `synthesis/profile_decisions.py`, and
  `synthesis/dataset_release.py`.
- [ ] Allow workspace-specific code only in workspace modules, domain pipeline or
  domain-pack registry, evaluation suite registration, run-profile mode
  validation, tests, docs, and fixtures.
- [ ] Run:

```bash
uv run python -m unittest tests.test_domain_pack_contract
```

- [ ] Expected result: the domain pack is visible through registration and
  descriptors, not through core consumer allowlists.

### Task 14: Run Representative Workspace CLI Commands

- [ ] Run the deterministic workspace profile with replay and reward labels:

```bash
uv run python main.py --run-profile tests/fixtures/run_profiles/workspace-tasks-fixture.json --write-episode-replay-report --write-reward-label-report --output-dir artifacts/workspace-third-domain-probe
```

- [ ] Expected result: command completes with accepted workspace samples,
  replayable episodes, reward labels, and sanitized manifest artifact references.
- [ ] Run the workspace profile with evaluation and profile decision reports:

```bash
uv run python main.py --run-profile tests/fixtures/run_profiles/workspace-tasks-fixture.json --write-evaluation-report --write-profile-decision-report --output-dir artifacts/workspace-third-domain-evaluation
```

- [ ] Expected result: command completes with workspace-domain evaluation evidence
  and no domain mismatch.

### Task 15: Documentation

- [ ] Update `docs/DESIGN.md` with the third-domain proof and the domain-pack
  ownership contract.
- [ ] Update `docs/BACKEND.md` with workspace module boundaries and the rule that
  consumers use runtime descriptors/sessions rather than workspace branches.
- [ ] Update `docs/DATA.md` with workspace environment, tools, tasks, runtime
  descriptor, and evaluation evidence entities.
- [ ] Update `docs/ROADMAP.md` to mark the third-domain probe complete when the
  plan finishes.
- [ ] Create `docs/generated/domain-pack-third-domain-pressure.md` unless the
  existing generated mobile pressure note is explicitly broadened.
- [ ] Link the generated note from `docs/generated/README.md`.
- [ ] Update `docs/PLANS.md` and plan bucket indexes when the plan moves from
  deferred to active or completed.

### Task 16: Validation

- [ ] Run documentation validation:

```bash
uv run python scripts/validate_docs.py
```

- [ ] Run the focused workspace suite:

```bash
uv run python -m unittest tests.test_workspace_environment tests.test_workspace_tools tests.test_workspace_pipeline tests.test_domain_pack_contract
```

- [ ] Run runtime and consumer tests:

```bash
uv run python -m unittest tests.test_runtime_contract tests.test_episode_quality tests.test_episode_replay tests.test_reward_labels tests.test_runtime_rollouts tests.test_mcp_adapters
```

- [ ] Run pipeline, evaluation, release, and CLI tests:

```bash
uv run python -m unittest tests.test_run_profiles tests.test_evaluation tests.test_profile_decisions tests.test_dataset_release tests.test_cli tests.test_foundation_pipeline tests.test_mobile_pipeline
```

- [ ] Run the full suite:

```bash
uv run python -m unittest
```

- [ ] Run both representative workspace CLI commands from Task 14.
- [ ] Record validation evidence in this plan before moving it to
  `../completed/`.

## Acceptance Criteria

- `workspace_tasks_fixture` can generate, execute, verify, replay, score, adapt,
  evaluate, and report deterministic trajectories.
- Adding the third domain does not require workspace-specific allowlists in core
  replay, reward-label, episode-quality, rollout, adapter, profile-decision, or
  dataset-release code.
- Runtime package or approved runtime boundary tests from Phase G still pass.
- Contacts and mobile behavior remains stable.
- Workspace public dataset artifacts use existing sample/rejection/manifest
  schemas.
- Workspace episode, replay, reward-label, evaluation, profile-decision, and
  dataset-release evidence remains sanitized.

## Follow-On

After this plan, consider release-grade review-loop work before scale work:

- human review queue and review outcome import for uncertain samples;
- release candidate history and richer release cards;
- semantic duplicate detection only when release evidence or dataset volume
  triggers `TD-0002`;
- async orchestration only when run duration or candidate volume triggers plan
  [0014](0014-async-local-orchestration-with-durable-queues.md).
