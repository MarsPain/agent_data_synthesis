# Plan 0009: Multi-Path Branching Trajectory Foundation

## Status

Completed on 2026-05-17.

## Goal

Add the first executable foundation for multi-path trajectory generation and
branching behavior-tree tasks. The pipeline should be able to represent a
bounded branch plan, execute deterministic branches against resettable
environment state, verify the selected successful path, and report branch-level
quality without turning the local runner into a distributed orchestrator.

## Basis

This plan follows
[0008-failure-driven-tool-expansion-and-capability-gap-routing](0008-failure-driven-tool-expansion-and-capability-gap-routing.md).
The repository now has task generation, solution-policy execution, stateful
multi-step trajectories, critic/refinement, role contracts, and bounded
tool-expansion loops. The next Stage 3 item in
[../../ROADMAP.md](../../ROADMAP.md) is multi-path trajectory generation and
branching behavior-tree tasks.

Relevant current constraints:

- [../../DESIGN.md](../../DESIGN.md) requires curriculum-aware generation that
  reaches ambiguous, multi-step, branching tasks.
- [../../BACKEND.md](../../BACKEND.md) keeps trajectory execution local and
  provider calls behind role-backed boundaries.
- [../../DATA.md](../../DATA.md) requires output samples to preserve enough
  trajectory, verifier, quality, and lineage information to audit accepted data.
- [../../SECURITY.md](../../SECURITY.md) requires executable behavior to remain
  sandboxed and auditable, with secrets excluded from artifacts.

## Scope

- Add a bounded branch-plan contract for deterministic behavior-tree-like
  trajectory plans.
- Represent branch nodes, branch ids, parent-child relationships, selection
  conditions, terminal outcomes, and per-branch failure causes.
- Execute branches against reset or checkpointed local environment state so one
  failed branch does not corrupt another branch.
- Add one contacts-domain fixture that requires a fallback branch by trying an
  abbreviated-name lookup and falling back to the full contact name.
- Preserve the accepted sample's selected branch lineage while keeping rejected
  branch attempts inspectable.
- Add quality-report visibility for branch attempts, selected branches, branch
  outcomes, and branch-depth slices.
- Keep existing deterministic `uv run python main.py` behavior stable unless the
  new branching fixture or option is enabled.

## Out of Scope

- Distributed workers, durable queues, actor routing, or async orchestration
  beyond what the local runner already needs.
- Network-backed environments, browser tools, MCP adapters, or external API
  tools.
- Arbitrary LLM-generated behavior-tree code.
- Full AgentInstruct-style suggester/editor refinement.
- Semantic duplicate detection.
- Human UI for branch inspection.

## Architecture

Branching should extend the current execution and data contracts without
replacing serial trajectories:

- `synthesis.execution` owns branch-plan execution, environment reset/checkpoint
  boundaries, per-branch event capture, and selected-path assembly.
- `synthesis.tasks` owns deterministic branching fixture candidates and
  curriculum metadata that marks branch depth and fallback behavior.
- `synthesis.contracts` validates branch-plan records, branch outcome records,
  and any new trajectory event metadata.
- `synthesis.datasets` serializes selected branch lineage on accepted samples and
  rejected branch attempts on failed candidates.
- `synthesis.verification` verifies the selected terminal path and records why
  non-selected branches were not accepted.
- `synthesis.quality` reports branch counts, selected-path outcomes, branch
  failure causes, and branch-depth slices.
- `synthesis.roles` and `synthesis.llm` remain unchanged unless remote
  solution-policy parsing needs a structured branch-plan output type.

## File Map

- Modify `synthesis/execution.py` with branch-plan execution and per-branch
  trajectory capture.
- Modify `synthesis/tasks.py` with a deterministic branching contacts fixture
  and branch-depth curriculum metadata.
- Modify `synthesis/contracts.py` with branch-plan and branch-outcome
  validation.
- Modify `synthesis/datasets.py` to persist selected branch lineage and rejected
  branch details.
- Modify `synthesis/verification.py` if selected-path verification needs branch
  metadata.
- Modify `synthesis/quality.py` with branch outcome metrics and slices.
- Modify `synthesis/pipeline.py` to route branching candidates through the new
  execution path without disturbing serial candidates.
- Add or extend tests in `tests/test_foundation_pipeline.py`,
  `tests/test_contracts.py`, `tests/test_quality_reporting.py`, and
  `tests/test_refinement.py` if branch failures interact with refinement.
- Update [../../BACKEND.md](../../BACKEND.md), [../../DATA.md](../../DATA.md),
  and [../../ROADMAP.md](../../ROADMAP.md) when implementation lands.

## Implementation Tasks

### Task 1: Define Branch Contracts

- [x] Add a branch-plan record shape with branch ids, node type, ordered steps,
  fallback relationships, selection condition, and terminal outcome.
- [x] Add branch-outcome records with attempted, selected, rejected, failure
  cause, and retry/refinement eligibility fields.
- [x] Add contract tests for valid plans, unsupported node types, duplicate
  branch ids, and missing selected terminal branches.

### Task 2: Add Local Branch Execution

- [x] Add an execution path that can run each branch from a clean environment
  reset or checkpoint.
- [x] Preserve per-branch trajectories separately from the selected path.
- [x] Ensure failed branches do not leak state into later branch attempts.
- [x] Classify branch execution failures without broad exception parsing.

### Task 3: Add Deterministic Branching Fixture

- [x] Add one contacts-domain candidate that requires fallback behavior.
- [x] Keep the fixture small enough for the default unit suite.
- [x] Add curriculum metadata for branch depth, fallback count, and expected
  terminal path.
- [x] Preserve existing serial, multi-step, refinement, and tool-expansion
  fixtures.

### Task 4: Persist Branch Lineage

- [x] Store selected branch id, branch depth, branch outcomes, and selected-path
  trajectory metadata on accepted samples.
- [x] Store rejected branch outcomes under rejection details when no branch
  succeeds.
- [x] Keep artifact schemas versioned and backward compatible with existing
  samples.
- [x] Avoid storing secrets, raw prompts, or provider payloads in branch
  diagnostics.

### Task 5: Reporting and Quality Gates

- [x] Extend `quality_report.json` with branch-attempt counts, selected-branch
  counts, and branch failure causes.
- [x] Add deterministic slices by branch depth, branch outcome, selected branch,
  and fallback count.
- [x] Ensure duplicate detection and logical consistency checks still operate on
  the selected path.
- [x] Add parent-comparison behavior for new branch-related slice keys.

### Task 6: Docs and Validation

- [x] Update backend and data docs after the implementation defines the final
  branch artifact shape.
- [x] Update roadmap wording once the foundation is complete.
- [x] Run `uv run python scripts/validate_docs.py`.
- [x] Run `uv run python -m unittest`.
- [x] Run a deterministic foundation command that exercises the branching
  fixture.

## Validation

- `uv run python scripts/validate_docs.py`
- `uv run python -m unittest`
- `uv run python main.py --enable-branching --output-dir /tmp/agent-data-synthesis-branching-check`

## Acceptance Criteria

- The pipeline can represent and validate a bounded branch plan.
- A deterministic contacts-domain branching fixture executes at least two branch
  attempts and accepts the selected successful path.
- Environment state is reset or checkpointed between branch attempts.
- Accepted samples preserve selected branch lineage and enough branch outcome
  detail to audit why the path was accepted.
- Failed branching candidates preserve rejected branch outcomes with classified
  causes.
- Quality reports include branch attempt, selected-branch, branch-depth, and
  branch-outcome metrics without breaking existing report fields.
- Existing deterministic serial runs remain stable unless branching is enabled.
- Documentation validation and the unit suite pass.

## Risks

- Branching can blur the boundary between plan exploration and accepted
  trajectory data. Keep selected-path samples explicit and keep rejected branch
  attempts in diagnostics.
- Environment reset bugs can create false branch outcomes. Add tests that prove
  branch attempts do not share unintended state.
- Quality metrics can double-count candidates if every branch is treated like a
  sample. Count branch attempts separately from accepted samples.
- Remote branch-plan generation can expand scope quickly. Start with local
  deterministic branch plans and only add remote parsing after contracts are
  stable.

## Notes

This is the smallest useful step from serial stateful trajectories toward
behavior-tree-style data. It should create the data and execution foundation that
later AgentInstruct-style task expansion and distributed orchestration can build
on without changing the sample contract again.
