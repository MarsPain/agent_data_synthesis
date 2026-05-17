# Plan 0010: AgentInstruct Seed Transformation and Editor Loop

## Status

Completed on 2026-05-17.

## Goal

Add the next Stage 3 foundation for AgentInstruct-style seed transformation,
taxonomy-driven task expansion, and a bounded suggester/editor refinement loop.
The pipeline should increase verified trajectory yield per seed by proposing
task intents from a capability taxonomy, editing them into executable
`CandidateTask` records, and preserving role lineage and edit outcomes without
weakening existing executable verification gates.

## Basis

This plan follows
[0009-multi-path-branching-trajectory-foundation](../completed/0009-multi-path-branching-trajectory-foundation.md).
The repository now has deterministic and remote task generation, separate
solution-policy execution, stateful trajectories, critic/refinement, role
contracts, failure-driven tool expansion, and bounded branch execution.

The next unfinished Stage 3 item in [../../ROADMAP.md](../../ROADMAP.md) is
AgentInstruct-style seed transformation, taxonomy-driven task expansion, and
suggester/editor refinement.

Relevant current constraints:

- [../../DESIGN.md](../../DESIGN.md) requires curriculum-aware generation that
  progresses from simple tasks to ambiguous, multi-step, branching tasks.
- [../../BACKEND.md](../../BACKEND.md) already defines disabled
  `task_suggester` and `task_editor` role guardrails that must be explicitly
  enabled by a plan before provider calls are allowed.
- [../../DATA.md](../../DATA.md) requires lineage for generation roles, quality
  slicing by role output type, and dataset-level comparison over quality and
  coverage rather than raw sample count.
- [../../SECURITY.md](../../SECURITY.md) requires prompts, provider payloads,
  credentials, and executable behavior to stay sanitized and auditable.

## Scope

- Add a small seed-transformation contract that records source seed id,
  transformation type, target taxonomy node, capability target, and intended
  difficulty movement.
- Add a taxonomy expansion layer for the contacts fixture that can produce
  deterministic transformation requests for existing capabilities: single-tool
  lookup, multi-step follow-up, verification-failure fixture, and branching
  fallback.
- Enable bounded `task_suggester` and `task_editor` roles with explicit output
  contracts, lineage metadata, and disabled-role regression tests.
- Add deterministic local suggester/editor fixtures so the default suite can
  validate the loop without remote credentials.
- Add optional remote task-suggester/editor generation through the existing
  OpenAI-compatible provider boundary.
- Route edited tasks through the normal candidate schema validation, tool
  availability checks, solution-policy execution, verification, refinement,
  duplicate gates, and quality reporting.
- Preserve suggestion and edit lineage on accepted samples and rejected
  candidates.
- Add quality-report visibility for seed transformations, taxonomy nodes,
  suggestion outcomes, editor actions, and edit rejection causes.

## Out of Scope

- Environment generation, verifier generation, judge verification, or
  network-backed environment synthesis.
- Arbitrary executable code generation by suggester or editor roles.
- New tool implementations beyond the existing contacts-domain tools.
- Distributed queues, durable workers, dashboards, or MCP adapters.
- Semantic duplicate detection beyond the current exact duplicate gate.
- Human UI for reviewing suggestions or edits.

## Architecture

The loop should sit before candidate execution and reuse the existing downstream
pipeline:

- `synthesis.seeds` owns seed transformation records and deterministic
  transformation requests.
- `synthesis.tasks` owns taxonomy expansion, task suggestions, edited
  candidate-task assembly, deterministic fixtures, and remote parsing for
  `task_suggester` and `task_editor` outputs.
- `synthesis.roles` enables `task_suggester` and `task_editor` only after their
  output types and validation behavior are covered by tests.
- `synthesis.contracts` validates seed transformations, task suggestions,
  edited task records, and lineage shape before execution.
- `synthesis.pipeline` optionally runs the suggester/editor loop before the
  existing candidate attempt path.
- `synthesis.datasets` persists suggestion/editor lineage and rejected
  suggestion or edit details without storing raw provider prompts or payloads.
- `synthesis.quality` reports transformation, taxonomy, suggestion, editor, and
  role-level slices.

## File Map

- Modify `synthesis/seeds.py` with seed transformation records and deterministic
  contacts-domain transformation requests.
- Modify `synthesis/tasks.py` with task suggestion and edited-task contracts,
  deterministic fixtures, remote prompt construction, and parser functions.
- Modify `synthesis/roles.py` to enable `task_suggester` and `task_editor` with
  versioned output types.
- Modify `synthesis/contracts.py` with validation for transformation,
  suggestion, and edited-task records.
- Modify `synthesis/pipeline.py` with an optional
  `enable_task_expansion`/generator hook that feeds edited candidates into the
  existing attempt path.
- Modify `synthesis/datasets.py` to preserve suggestion and editor lineage on
  accepted samples and rejected records.
- Modify `synthesis/quality.py` with transformation and editor outcome metrics
  and deterministic slice keys.
- Extend tests in `tests/test_roles.py`, `tests/test_contracts.py`,
  `tests/test_foundation_pipeline.py`, `tests/test_quality_reporting.py`, and
  `tests/test_llm_provider.py` where remote schema failures need coverage.
- Update [../../BACKEND.md](../../BACKEND.md),
  [../../DATA.md](../../DATA.md), [../../ROADMAP.md](../../ROADMAP.md), and
  [../../PLANS.md](../../PLANS.md) when implementation lands or the plan moves
  lifecycle state.

## Implementation Tasks

### Task 1: Define Transformation and Suggestion Contracts

- [x] Add a seed-transformation record shape with source seed id,
  transformation type, target taxonomy node, capability target, difficulty
  movement, and lineage.
- [x] Add task-suggestion records that describe intent, required capabilities,
  target tools, constraints, expected verification mode, and rejection reason.
- [x] Add edited-task records that either contain a valid `CandidateTask` mapping
  or a classified edit rejection.
- [x] Add contract tests for malformed transformations, unsupported taxonomy
  nodes, missing capability targets, invalid edited candidates, and sanitized
  lineage.

### Task 2: Add Deterministic Taxonomy Expansion

- [x] Extend the foundation seed taxonomy beyond the current single-tool and
  verification-failure fixtures to include follow-up state changes and branch
  fallback recovery.
- [x] Add deterministic transformation requests for contacts-domain coverage
  without changing default serial behavior unless task expansion is enabled.
- [x] Add deterministic task suggestions that exercise at least one accepted
  edited task and one rejected suggestion.
- [x] Keep ordering curriculum-aware and stable for unit tests.

### Task 3: Enable Suggester and Editor Roles

- [x] Change `task_suggester` from disabled guardrail to enabled
  `task_suggestion` output role with bounded remote JSON retry policy.
- [x] Change `task_editor` from disabled guardrail to enabled `edited_task`
  output role with bounded remote JSON retry policy.
- [x] Preserve disabled-role tests for roles that remain future work:
  environment generation, verifier generation, and judge verification.
- [x] Add remote schema-failure tests that classify malformed suggestion or
  edited-task responses before execution.

### Task 4: Integrate the Expansion Loop

- [x] Add an optional pipeline path that runs transformation -> suggestion ->
  editor before candidate execution.
- [x] Route edited candidates through the existing validation, execution,
  verification, refinement, tool-expansion, branch, duplicate, and review gates.
- [x] Ensure suggestion/editor failures become inspectable rejections rather
  than infrastructure crashes.
- [x] Ensure accepted samples keep task-generation lineage separate from
  suggestion and editor lineage.

### Task 5: Persist Lineage and Report Quality

- [x] Persist `lineage.seed_transformation`, `lineage.task_suggester`, and
  `lineage.task_editor` when edited candidates are accepted.
- [x] Persist rejected suggestion or editor details under sanitized rejection
  details.
- [x] Extend quality reports with transformation counts, taxonomy-node counts,
  suggestion outcomes, editor actions, and edit rejection causes.
- [x] Add parent-comparison behavior for new slice keys.

### Task 6: Docs and Validation

- [x] Update backend and data docs after implementation defines the final
  artifact shape.
- [x] Update roadmap wording once the foundation is complete.
- [x] Run `uv run python scripts/validate_docs.py`.
- [x] Run `uv run python -m unittest`.
- [x] Run a deterministic foundation command that exercises task expansion.

## Validation

- `uv run python scripts/validate_docs.py`
- `uv run python -m unittest`
- `uv run python main.py --enable-task-expansion --output-dir /tmp/agent-data-synthesis-task-expansion-check`

## Acceptance Criteria

- The pipeline can represent seed transformations, task suggestions, and edited
  task records with executable validation.
- Deterministic task expansion produces at least one accepted edited candidate
  and one inspectable suggestion/editor rejection.
- `task_suggester` and `task_editor` are enabled only with output-contract tests
  and sanitized role lineage.
- Edited candidates use the existing execution, verification, refinement,
  branch, duplicate, and quality gates.
- Accepted samples preserve seed-transformation, suggester, and editor lineage
  separately from task-generation and solution-policy lineage.
- Quality reports include transformation, taxonomy-node, suggestion-outcome,
  editor-action, and edit-rejection slices without breaking existing report
  fields.
- Existing deterministic serial and branching runs remain stable unless task
  expansion is enabled.
- Documentation validation and the unit suite pass.

## Risks

- Task expansion can inflate candidate count without improving verified yield.
  Keep accepted trajectory yield per seed and coverage slices visible.
- Suggester/editor roles can duplicate task-generation responsibilities. Keep
  suggestions as intent-level records and require the editor to produce the
  executable candidate contract.
- Remote editor output can smuggle unsupported tools or unverifiable tasks.
  Validate edited candidates before execution and route unsupported capabilities
  through the existing tool-expansion or rejection paths.
- Lineage can become confusing if every role overwrites generator metadata.
  Store suggester, editor, task generator, solution policy, verifier, and
  refinement lineage in separate fields.

## Notes

This is the smallest useful step from manually curated fixtures toward
AgentInstruct-style task diversity. It should improve seed leverage and
curriculum coverage while preserving the repository's current bias toward local,
executable, auditable contracts.
