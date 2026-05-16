# Plan 0005: Solution Policy and Multi-Step Stateful Trajectories

## Status

Completed on 2026-05-16.

## Goal

Move the foundation runner from single-tool scripted answers toward verifiable
Agent trajectories by separating task generation from solution-policy execution
and adding a small multi-tool, state-changing fixture path.

## Basis

This plan follows
[0004-remote-llm-generation-lineage-and-retry-loop](0004-remote-llm-generation-lineage-and-retry-loop.md).
The repository now has contract-validated artifacts, quality reports, metric
slicing, review queue records, parent comparison, remote LLM lineage, and
generation-stage retry/failure handling. The remaining blocker before broader
Stage 3 work is that execution still treats a `CandidateTask` as a direct tool
call recipe:

- [../../ROADMAP.md](../../ROADMAP.md) Stage 3 calls for generator roles,
  multi-path trajectory generation, branching behavior, and refinement.
- [../../DESIGN.md](../../DESIGN.md) defines the central output as a complete
  trajectory, not only a task and final answer.
- [../../design-docs/agent-data-synthesis-framework.md](../../design-docs/agent-data-synthesis-framework.md)
  says candidate solution policy should be generated or selected separately from
  task generation, then executed and independently verified.
- [../../DATA.md](../../DATA.md) requires trajectories to preserve ordered action,
  observation, final-response, verification, quality, and lineage metadata.
- [../../BACKEND.md](../../BACKEND.md) already separates `synthesis.tasks`,
  `synthesis.execution`, `synthesis.verification`, `synthesis.quality`, and
  `synthesis.llm`; the next slice should make that boundary real in code.

## Scope

- Introduce a small solution-policy representation that is distinct from
  `CandidateTask`.
- Keep scripted solution policies for deterministic fixture runs and smoke tests.
- Add an optional remote LLM-backed solution-policy generator that uses the
  existing OpenAI-compatible provider boundary and sanitized lineage model.
- Extend the contact fixture into one multi-step, state-changing task that
  requires at least two tool calls and produces verifiable state change.
- Record policy-role lineage separately from task-generation lineage when remote
  policy generation is used.
- Extend trajectory event capture so multi-step actions, observations, errors,
  and state changes remain contract-validated.
- Extend verification so the new state-changing sample is accepted only when the
  final answer and environment state both satisfy the task.
- Preserve existing deterministic foundation behavior and artifact names.

## Out of Scope

- Full multi-agent orchestration or distributed workers.
- Branching behavior-tree execution beyond a minimal serial multi-step policy.
- Tool synthesis or automatic tool expansion.
- Generated Python code execution.
- LLM-as-judge acceptance.
- Interactive human review UI.
- Semantic duplicate detection.
- Network-backed environment synthesis.

## Architecture

Keep this as a narrow bridge between Stage 2 quality infrastructure and Stage 3
agentic generation:

- `synthesis.tasks`: owns task intent, constraints, expected capabilities, and
  task-generation lineage. It should stop being the only place that knows the
  exact action sequence.
- `synthesis.execution`: owns a `SolutionPolicy` or equivalent value, executes
  ordered tool steps against a registry, and records complete trajectory events.
- `synthesis.llm`: owns remote solution-policy calls, retry policy, sanitized
  failures, role names, prompt/config hashes, token usage, and cost metadata.
- `synthesis.verification`: owns independent checks for final answer support and
  state mutation correctness.
- `synthesis.environments` and `synthesis.tools`: own the new fixture state and
  typed tools needed for a multi-step state-changing task.
- `synthesis.datasets`: owns sample assembly and should include task-generation
  lineage and solution-policy lineage without reconstructing provider details
  from environment variables.
- `synthesis.quality`: should keep duplicate and logical gates working over
  multi-step trajectories.

## File Map

- Modify `synthesis/tasks.py` to remove hard coupling between candidate tasks and
  the exact executable tool recipe where feasible, while preserving compatibility
  for existing fixture candidates.
- Modify `synthesis/execution.py` to execute an explicit multi-step solution
  policy and emit ordered action, observation, state-change, error, and
  final-response events.
- Modify `synthesis/llm.py` only if a shared helper is needed for the new
  `solution_policy` provider role.
- Modify `synthesis/environments.py` and `synthesis/tools.py` to add a small
  state-changing contact-domain capability, such as recording a follow-up note
  after resolving a contact.
- Modify `synthesis/verification.py` to verify both final response content and
  fixture state after the multi-step task.
- Modify `synthesis/datasets.py` to preserve separate task and policy lineage in
  accepted samples when available.
- Modify `synthesis/pipeline.py` to generate or select solution policies after
  task generation and before execution.
- Extend `tests/test_foundation_pipeline.py` for the deterministic multi-step
  accepted sample.
- Extend `tests/test_contracts.py` for new trajectory event fields if the
  contract changes.
- Extend `tests/test_llm_provider.py` for remote policy lineage and schema
  failure classification if the optional provider path is added in this slice.
- Extend `tests/test_quality_reporting.py` to prove duplicate and logical gates
  still work with multi-step trajectories.
- Update [../../DATA.md](../../DATA.md) and [../../BACKEND.md](../../BACKEND.md)
  if the accepted sample lineage or execution module contract changes.

## Implementation Tasks

### Task 1: Define the Solution Policy Contract

- [x] Add a small `SolutionPolicy` shape with policy id, role, ordered tool steps,
  final response template or response instruction, and optional lineage.
- [x] Add contract validation for policy-derived trajectory events if existing
  trajectory validation is too narrow.
- [x] Preserve compatibility for existing `CandidateTask` fixture fields until
  the deterministic foundation path has been migrated.
- [x] Add tests proving malformed policy steps are rejected before execution.

### Task 2: Add a Multi-Step Stateful Fixture

- [x] Extend the contact environment with deterministic state that can be changed
  and reset, such as a follow-up note or outreach log.
- [x] Add typed tools for reading contact data and recording the state change.
- [x] Add one fixture candidate that requires lookup plus state mutation.
- [x] Ensure environment metadata and reset recipes still reproduce the run.

### Task 3: Execute Policies Instead of Direct Task Recipes

- [x] Update execution so it receives a task plus a solution policy.
- [x] Record each tool action and observation in order.
- [x] Record state-change events for mutating tools without exposing unrelated
  environment internals.
- [x] Classify missing-tool, schema, runtime, and policy-shape failures with the
  existing rejection taxonomy where possible.

### Task 4: Verify Stateful Trajectories Independently

- [x] Extend verification to check final answer support from observations.
- [x] Add a state verifier for the new mutating fixture task.
- [x] Ensure a policy that returns the right final answer but skips the mutation
  is rejected as `solution_logic_error` or a more specific documented cause.
- [x] Keep exact-answer verification available for simple fixture tasks.

### Task 5: Preserve Lineage Across Task and Policy Roles

- [x] Preserve task-generation lineage on task candidates.
- [x] Preserve solution-policy lineage on policy outputs.
- [x] Ensure accepted samples identify both roles when both were involved.
- [x] Ensure deterministic fixture policies keep stable local lineage.
- [x] Add tests proving provider secrets and raw prompts are not written to
  samples, manifests, rejections, or quality reports.

### Task 6: Keep Quality Artifacts Stable

- [x] Update quality duplicate signatures to handle multi-step action sequences.
- [x] Confirm logical support checks inspect all relevant observations.
- [x] Confirm quality report slices still include dataset version, difficulty,
  tool combination, generator role, verifier type, curriculum level, and
  rejection cause.
- [x] Confirm parent comparison and review queue artifacts still write when
  enabled.

### Task 7: Refresh Docs and Validation

- [x] Update [../../DATA.md](../../DATA.md) if sample lineage, trajectory events,
  or rejection causes change.
- [x] Update [../../BACKEND.md](../../BACKEND.md) if ownership boundaries change.
- [x] Update [../../ROADMAP.md](../../ROADMAP.md) if this slice completes the
  Stage 3 bridge and changes the next recommended milestone.
- [x] Run `uv run python scripts/validate_docs.py`.
- [x] Run `uv run python -m unittest`.

## Acceptance Criteria

- `uv run python main.py` still writes `samples.jsonl`, `rejections.jsonl`,
  `manifest.json`, and `quality_report.json`.
- The deterministic run includes at least one accepted multi-step trajectory with
  two or more tool actions.
- The multi-step sample includes a verifiable state change and a resettable
  environment version.
- Execution no longer requires every task to embed the exact tool action recipe
  as its only solution path.
- Accepted samples can preserve separate task-generation and solution-policy
  lineage.
- Remote solution-policy failures, if implemented in this slice, are classified
  without leaking provider secrets, raw prompts, headers, or credentials.
- Duplicate and logical quality gates still work for multi-step trajectories.
- Existing remote task-generation lineage and retry behavior remain unchanged.
- `uv run python scripts/validate_docs.py` passes.
- `uv run python -m unittest` passes.

## Risks

- The policy abstraction can grow too large before the repository has enough
  domains. Keep it limited to ordered tool steps and lineage.
- A state-changing fixture can make deterministic tests flaky if reset behavior
  is incomplete. Add reset verification before accepting samples.
- Combining task-generation and policy-generation lineage can make samples hard
  to inspect. Store roles explicitly and keep provider metadata sanitized.
- Adding a remote solution-policy path too early can obscure the deterministic
  execution migration. Keep scripted policies as the required baseline.

## Notes

This plan should create the smallest useful Stage 3 bridge: complete executable
trajectories with more than one action and real state change. Do not add
distributed orchestration, tool synthesis, or generated-code execution until this
policy boundary is stable and covered by tests.
