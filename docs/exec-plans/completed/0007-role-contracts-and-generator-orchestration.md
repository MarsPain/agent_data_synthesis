# Plan 0007: Role Contracts and Generator Orchestration Foundation

## Status

Completed on 2026-05-16.

## Goal

Make Stage 3 generator roles first-class before expanding tools, branching
trajectories, or generated environments. The framework should have one explicit
role contract and routing layer for task generation, solution-policy generation,
critic/refinement, and future environment, tool, verifier, judge, suggester, and
editor roles.

## Basis

This plan follows
[0006-critic-refinement-and-regeneration-loop](../completed/0006-critic-refinement-and-regeneration-loop.md).
The repository now has executable fixture trajectories, quality reporting,
remote task generation, remote solution-policy generation, and bounded
critic/refinement. The next blocker is that role behavior is still distributed
across `synthesis.tasks`, `synthesis.execution`, `synthesis.refinement`, and
`synthesis.llm` as string literals and local conventions:

- [../../ROADMAP.md](../../ROADMAP.md) Stage 3 calls for generator roles for
  environment, tool, task, solution, verifier, and critic before broader tool
  expansion and branching trajectories.
- [../../DESIGN.md](../../DESIGN.md) requires generation and verification to
  remain separate, with mandatory lineage for every accepted sample.
- [../../DATA.md](../../DATA.md) requires LLM-backed generation, solution,
  refinement, and judge steps to preserve role-specific provider lineage without
  leaking secrets.
- [../../BACKEND.md](../../BACKEND.md) keeps the remote LLM provider behind
  `synthesis.llm`, while role-specific modules own validation and parsing.
- [../../design-docs/agent-data-synthesis-framework.md](../../design-docs/agent-data-synthesis-framework.md)
  describes multiple generator roles, suggester/editor refinement contracts, and
  later role-aware orchestration.

## Scope

- Add a small role contract that names the role, owner module, output type,
  parser, validation boundary, default enabled state, and retry/cost policy.
- Add a role registry for the roles currently used by the system:
  `task_generation`, `solution_policy`, and `critic_refinement`.
- Add explicit disabled definitions for future roles:
  `environment_generation`, `tool_generation`, `verifier_generation`,
  `judge_verification`, `task_suggester`, and `task_editor`.
- Route existing remote task, solution-policy, and critic/refinement LLM calls
  through the role contract rather than ad hoc role strings.
- Preserve existing local deterministic paths and CLI behavior.
- Extend lineage and quality reporting so role name, role version, output type,
  retry policy, provider host, model, token/cost metadata, and error class remain
  visible by role.
- Add tests proving disabled future roles cannot be accidentally invoked.
- Keep implementation local and synchronous; do not introduce queue workers or a
  distributed orchestrator in this slice.

## Out of Scope

- Generated tools or generated code execution.
- Generated environments beyond disabled role definitions.
- LLM-generated verifier acceptance.
- LLM-as-judge acceptance for training samples.
- Branching behavior-tree execution or multi-path rollouts.
- AgentInstruct-style taxonomy expansion beyond reserving role names for
  suggester/editor flows.
- MCP adapters, durable queues, dashboards, or distributed workers.
- New provider SDKs or model-specific routing logic.

## Architecture

Keep roles as orchestration metadata, not as owners of domain logic:

- `synthesis.roles`: role definitions, registry lookup, role invocation helpers,
  output-type names, and disabled-role guardrails.
- `synthesis.llm`: remains the only HTTP boundary. It should accept a role
  definition or validated role name and return sanitized provider lineage.
- `synthesis.tasks`: owns candidate task parsing and validation. It should ask
  the role registry for `task_generation` and parse the result into normal
  `CandidateTask` values.
- `synthesis.execution`: owns solution-policy parsing, validation, and
  execution. It should ask the role registry for `solution_policy`.
- `synthesis.refinement`: owns repairability decisions and refinement parsing.
  It should ask the role registry for `critic_refinement`.
- `synthesis.datasets`: serializes role lineage without changing accepted sample
  semantics.
- `synthesis.quality`: adds role-level quality, retry, and cost visibility
  without becoming a provider analytics system.
- `synthesis.pipeline`: composes the registry into the foundation run while
  preserving deterministic local defaults.

## File Map

- Create `synthesis/roles.py` for role definitions, registry construction,
  disabled-role errors, and role invocation metadata.
- Modify `synthesis/llm.py` only as needed to accept validated role metadata
  while preserving current `OpenAICompatibleClient.generate_json(...)` behavior.
- Modify `synthesis/tasks.py` to use the registry for remote task generation.
- Modify `synthesis/execution.py` to use the registry for remote solution-policy
  generation.
- Modify `synthesis/refinement.py` to use the registry for remote
  critic/refinement.
- Modify `synthesis/pipeline.py` to build or accept a registry without requiring
  callers to configure one.
- Modify `synthesis/quality.py` to expose role-level counts, failure counts,
  retry counts, and token/cost metadata when present.
- Modify `synthesis/contracts.py` only if role lineage needs additional required
  fields such as `role_version` or `output_type`.
- Add `tests/test_roles.py` for registry, disabled-role guardrails, lineage
  metadata, and invocation behavior.
- Extend `tests/test_llm_provider.py`, `tests/test_foundation_pipeline.py`,
  `tests/test_quality_reporting.py`, and `tests/test_refinement.py` only where
  the new role plumbing changes observable behavior.
- Update [../../BACKEND.md](../../BACKEND.md), [../../DATA.md](../../DATA.md),
  and [../../ROADMAP.md](../../ROADMAP.md) if implementation changes canonical
  role boundaries or stage status.

## Implementation Tasks

### Task 1: Define Role Contract and Registry

- [x] Add a `RoleDefinition` value with `name`, `version`, `owner_module`,
  `output_type`, `enabled`, `retry_policy`, and `lineage_fields`.
- [x] Add a default registry containing enabled definitions for existing remote
  roles and disabled definitions for future roles.
- [x] Add a specific disabled-role exception that names the role and required
  enabling decision.
- [x] Add tests for lookup, duplicate names, invalid names, disabled roles, and
  deterministic registry ordering.

### Task 2: Route Existing LLM Calls Through Roles

- [x] Update task generation to use the `task_generation` role definition.
- [x] Update remote solution-policy generation to use the `solution_policy` role
  definition.
- [x] Update remote critic/refinement to use the `critic_refinement` role
  definition.
- [x] Preserve current prompt hashes, provider lineage, retry behavior, and
  schema-error classification.
- [x] Add regression tests proving existing remote LLM tests still see the same
  role names and sanitized lineage.

### Task 3: Standardize Role Lineage

- [x] Extend sanitized lineage with `role_version` and `output_type` when the
  role registry is used.
- [x] Ensure accepted samples can preserve generator, solution-policy,
  refinement, and verifier lineage without mixing ownership fields.
- [x] Ensure rejected candidates preserve role lineage for generation,
  solution-policy, and refinement failures.
- [x] Preserve backward-compatible contract validation; new role fields are
  asserted through lineage and quality tests rather than made required for older
  artifacts.

### Task 4: Add Role-Level Quality Visibility

- [x] Extend `quality_report.json` with role-level attempted, accepted, rejected,
  retry, token, and cost summaries where data exists.
- [x] Add deterministic slices for role name and role output type.
- [x] Keep existing aggregate success and executable rates backward compatible.
- [x] Add tests for reports with local lineage, remote lineage, provider errors,
  and refined outcomes.

### Task 5: Guard Future Roles

- [x] Add disabled definitions for environment, tool, verifier, judge,
  suggester, and editor roles.
- [x] Make accidental invocation of a disabled role fail before any provider
  call is made.
- [x] Document what each disabled role is allowed to produce when a later plan
  enables it.
- [x] Add tests with a fake client proving disabled roles do not call the client.

### Task 6: Refresh Docs and Validation

- [x] Update [../../BACKEND.md](../../BACKEND.md) with the `synthesis.roles`
  boundary and role invocation lifecycle.
- [x] Update [../../DATA.md](../../DATA.md) with role lineage and role-level
  quality report fields.
- [x] Update [../../ROADMAP.md](../../ROADMAP.md) after implementation to mark
  the role-contract slice done and identify the next Stage 3 target.
- [x] Run `uv run python scripts/validate_docs.py`.
- [x] Run `uv run python -m unittest`.

## Acceptance Criteria

- Existing deterministic `uv run python main.py` behavior remains stable.
- Existing remote task generation, remote solution-policy generation, and remote
  critic/refinement still work through the OpenAI-compatible boundary.
- Role names are no longer ad hoc call-site strings in task, execution, and
  refinement modules.
- Disabled future roles cannot be invoked accidentally and fail before any remote
  provider request.
- Accepted samples and rejections preserve role lineage with role name, role
  version, output type, provider host, model, prompt/config hash, retry count,
  token/cost metadata when available, and error class when present.
- Quality reports expose role-level outcome visibility without breaking existing
  count, rate, rejection-cause, and refinement-status fields.
- Tests cover registry behavior, disabled-role guardrails, migrated remote calls,
  role lineage contracts, quality report compatibility, and the default pipeline.
- `uv run python scripts/validate_docs.py` passes.
- `uv run python -m unittest` passes.

## Risks

- A role registry can become premature framework ceremony if it does not remove
  duplicated role conventions from existing modules. Keep it small and tied to
  current call paths.
- Centralized invocation can blur module ownership. Role definitions should route
  calls, while domain modules still parse and validate their own outputs.
- Adding required lineage fields can break older artifacts. Preserve backward
  compatibility in readers and make new fields required only for newly generated
  role-backed records.
- Disabled future roles can create a false sense of implementation progress.
  Treat them as guardrails and documentation, not as completed capabilities.

## Notes

This plan deliberately prepares the system for tool expansion, verifier
generation, branching trajectories, and AgentInstruct-style suggester/editor
flows without implementing those capabilities yet. The expected result is a
small role-aware spine that makes later Stage 3 plans easier to execute and
review.
