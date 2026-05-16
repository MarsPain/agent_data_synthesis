# Plan 0006: Critic Refinement and Regeneration Loop

## Status

Completed on 2026-05-16.

## Goal

Add a bounded critic/refinement loop that can diagnose failed executable
candidate trajectories, generate one corrected candidate or solution policy, rerun
it, and preserve the full lineage from original attempt to refined sample or
rejection.

## Basis

This plan follows
[0005-solution-policy-and-multi-step-stateful-trajectories](0005-solution-policy-and-multi-step-stateful-trajectories.md).
The repository now has contract-validated artifacts, deterministic quality
reports, remote task-generation lineage, remote solution-policy lineage, and a
multi-step stateful fixture. The next Stage 3 blocker is that failed samples are
classified but not yet repairable:

- [../../ROADMAP.md](../../ROADMAP.md) Stage 3 calls for generator roles,
  refinement, broader trajectory generation, and later tool expansion.
- [../../DESIGN.md](../../DESIGN.md) requires independent verification and
  lineage across generated samples.
- [../../DATA.md](../../DATA.md) requires rejected candidates, quality metrics,
  parent comparison, and LLM lineage to remain inspectable over time.
- [../../BACKEND.md](../../BACKEND.md) assigns retry policy, trajectory execution,
  validation, quality reporting, and role-specific LLM calls to separate modules.
- [../../product-specs/framework-mvp.md](../../product-specs/framework-mvp.md)
  frames the MVP around executable trajectories, independent verification, and
  inspectable failures.

## Scope

- Introduce a small `RefinementAttempt` or equivalent value that links an
  original candidate, failure cause, critic diagnosis, revised candidate or
  revised solution policy, and bounded attempt number.
- Add a deterministic local critic/refiner for fixture tests so the default
  pipeline remains runnable without provider credentials.
- Add an optional remote LLM-backed critic/refiner role using the existing
  OpenAI-compatible provider boundary and sanitized lineage format.
- Retry at most one refined attempt per failed candidate in this slice.
- Support repair of two concrete failure classes:
  - `verification_failed` caused by wrong expected answer or final response.
  - `solution_logic_error` caused by a stateful task policy that skipped a
    required mutation.
- Preserve the original failed attempt as a rejection when refinement is disabled
  or when the refined attempt still fails.
- Preserve refinement lineage in accepted samples and refined rejections without
  storing raw prompts, provider payloads, headers, or credentials.
- Extend quality reports with deterministic counts and slices that make refined
  successes and refined failures visible.
- Keep the default `uv run python main.py` behavior deterministic and stable.

## Out of Scope

- Multiple refinement rounds per candidate.
- Automatic tool synthesis or tool expansion.
- Branching behavior-tree execution.
- LLM-as-judge acceptance.
- Semantic duplicate detection.
- Interactive human review UI.
- Distributed orchestration, queue workers, MCP adapters, dashboards, or cost
  control services.
- Network-backed environment synthesis.

## Architecture

Keep refinement as a narrow Stage 3 loop around the existing pipeline:

- `synthesis.pipeline` owns the control flow: execute original candidate, classify
  failure, optionally request a refined candidate or policy, rerun once, then
  write one final accepted sample or rejection outcome.
- `synthesis.refinement` should be added as the owner of critic/refiner value
  types, deterministic fixture repair, remote refiner parsing, and repairability
  decisions. This avoids pushing critic logic into task generation, execution, or
  quality reporting.
- `synthesis.llm` remains the only HTTP boundary. Remote refinement should call
  `OpenAICompatibleClient.generate_json(..., role="critic_refinement")`.
- `synthesis.tasks` continues to own `CandidateTask` normalization. If refinement
  edits a candidate, it should produce a normal validated `CandidateTask`.
- `synthesis.execution` continues to own `SolutionPolicy` validation and tool-step
  execution. If refinement edits only the policy, it should produce a normal
  validated `SolutionPolicy`.
- `synthesis.datasets` owns serialization of refinement lineage and attempt
  metadata in samples and rejections.
- `synthesis.quality` owns refined outcome metrics, review routing, and parent
  comparison compatibility.
- `synthesis.contracts` owns any new schema fields and rejection causes.

## File Map

- Create `synthesis/refinement.py` for repairability checks, refinement value
  types, deterministic fixture refiner, and remote refiner parsing.
- Modify `synthesis/pipeline.py` to run one optional refinement attempt after
  eligible verification or logical-support failures.
- Modify `synthesis/datasets.py` to preserve refinement metadata in accepted
  samples and rejected records.
- Modify `synthesis/quality.py` to count and slice refined outcomes.
- Modify `synthesis/contracts.py` if sample lineage, rejection details, or quality
  report fields change.
- Modify `synthesis/tasks.py` only if refined candidate normalization needs a
  shared helper rather than duplicating LLM parsing logic.
- Modify `synthesis/execution.py` only if refined policy parsing needs shared
  validation hooks.
- Modify `synthesis/llm.py` only if shared role metadata or prompt hashing needs
  a small extension.
- Modify `main.py` only if a CLI flag is needed, for example
  `--enable-refinement`; keep refinement disabled by default unless tests prove
  the deterministic fixture path is stable enough to enable safely.
- Extend `tests/test_foundation_pipeline.py` for pipeline-level refined success
  and refined failure behavior.
- Extend `tests/test_llm_provider.py` for remote critic/refinement parsing,
  lineage, retry classification, and secret redaction.
- Extend `tests/test_contracts.py` for any new sample or rejection fields.
- Extend `tests/test_quality_reporting.py` for refined outcome counts and slices.
- Update [../../DATA.md](../../DATA.md), [../../BACKEND.md](../../BACKEND.md), and
  [../../ROADMAP.md](../../ROADMAP.md) if the implementation changes canonical
  contracts or stage status.

## Implementation Tasks

### Task 1: Define the Refinement Contract

- [x] Add a `RefinementAttempt` shape with original candidate id, attempt number,
  source failure cause, source failure details, critic diagnosis, revised
  candidate or policy payload, and optional lineage.
- [x] Add a `RefinementDecision` or equivalent enum-like result for
  `not_repairable`, `repair_candidate`, and `repair_policy`.
- [x] Add contract validation for refinement metadata before it can be serialized.
- [x] Add tests proving invalid attempt numbers, empty diagnoses, missing revised
  payloads, and unsupported repair decisions are rejected before rerun.

### Task 2: Add Deterministic Fixture Refinement

- [x] Add a local refiner that repairs the existing Ben Carter wrong-expectation
  fixture by replacing `ben@example.test` with `ben.carter@example.test`.
- [x] Add a local refiner path that repairs a stateful contact-followup policy
  that skipped `record_contact_followup`.
- [x] Keep deterministic refinement behind an explicit pipeline option so tests
  can compare refinement disabled and enabled behavior.
- [x] Add tests proving the default pipeline still accepts 2 and rejects 1 when
  refinement is disabled.
- [x] Add tests proving the deterministic refinement-enabled pipeline accepts the
  repaired Ben Carter sample and records it as refined.

### Task 3: Rerun One Refined Attempt Safely

- [x] Update `run_foundation_pipeline` to accept an optional refiner callable.
- [x] After a repairable verification or logical-support failure, request one
  refined candidate or policy and rerun validation, execution, verification, and
  quality gates from the normal code path.
- [x] Ensure duplicate detection compares refined accepted samples against prior
  accepted signatures.
- [x] Ensure the original failure remains visible in final rejection details if
  the refined attempt fails.
- [x] Add tests for refined attempt success, refined attempt duplicate rejection,
  and refined attempt still failing with a clear rejection cause.

### Task 4: Add Remote Critic/Refinement Role

- [x] Add `generate_llm_backed_refinement(...)` using
  `OpenAICompatibleClient.generate_json(..., role="critic_refinement")`.
- [x] Prompt the role with sanitized task, trajectory, verification checks, and
  failure cause only; do not include API keys, raw provider payloads, or unrelated
  environment internals.
- [x] Parse remote output into either a revised candidate or revised solution
  policy and validate it with the same local contracts used by deterministic
  refinement.
- [x] Classify malformed refinement output as `llm_response_schema_error`.
- [x] Add tests with `httpx.MockTransport` proving lineage includes role,
  provider host, model, prompt hash, retry count, token metadata, and no secrets.

### Task 5: Preserve Refinement Lineage and Quality Metrics

- [x] Extend accepted samples with sanitized `lineage.refinement` when a refined
  attempt succeeds.
- [x] Extend refined rejections with details that identify original failure cause,
  refinement attempt number, and sanitized critic lineage.
- [x] Extend `quality_report.json` with deterministic refined outcome visibility,
  such as `counts.refined_attempted`, `counts.refined_accepted`, and
  `counts.refined_rejected`.
- [x] Add a quality slice for refinement status: `unrefined`,
  `refined_accepted`, and `refined_rejected`.
- [x] Ensure parent comparison continues to work when the new counts or slices are
  present.

### Task 6: Refresh CLI, Docs, and Validation

- [x] Add a CLI flag only if needed to enable deterministic or remote refinement
  from `main.py`; document the flag in [../../../README.md](../../../README.md).
- [x] Update [../../DATA.md](../../DATA.md) with refinement metadata, quality
  counts, and lineage shape.
- [x] Update [../../BACKEND.md](../../BACKEND.md) with the new
  `synthesis.refinement` boundary and rerun lifecycle.
- [x] Update [../../ROADMAP.md](../../ROADMAP.md) after this plan is completed to
  mark the critic/refinement slice done and identify the next Stage 3 target.
- [x] Run `uv run python scripts/validate_docs.py`.
- [x] Run `uv run python -m unittest`.

## Acceptance Criteria

- `uv run python main.py` still writes deterministic foundation artifacts with
  the same default accepted/rejected counts unless refinement is explicitly
  enabled.
- With deterministic refinement enabled, a repairable wrong-answer fixture can be
  corrected, rerun, independently verified, and accepted.
- A stateful policy that skipped a required mutation can be repaired by replacing
  or extending the solution policy, then rerun and verified.
- Each candidate receives at most one refinement attempt in this slice.
- Original failures remain inspectable when refinement is disabled or when the
  refined attempt fails.
- Accepted refined samples preserve `lineage.generator`, optional
  `lineage.solution_policy`, `lineage.refinement`, and `lineage.verifier`.
- Refined rejections include attempt metadata and retry eligibility without
  leaking secrets, raw prompts, headers, or provider credentials.
- Quality reports expose refined attempted, accepted, and rejected counts plus a
  refinement-status slice.
- Existing duplicate gates, logical support checks, parent comparison, review
  queue behavior, remote task generation, and remote solution-policy generation
  remain compatible.
- `uv run python scripts/validate_docs.py` passes.
- `uv run python -m unittest` passes.

## Risks

- Refinement can hide generator quality problems if all failures are silently
  repaired. Keep original failure details and refined outcome counts visible.
- A refiner that edits both task and policy can blur ownership boundaries. Prefer
  one repair type per attempt and validate the revised value through existing
  contracts.
- Remote critic prompts can leak too much context. Prompt with sanitized task,
  trajectory, and verifier summaries only.
- Multi-round refinement can become an unbounded cost sink. This slice allows one
  attempt and records whether later work needs a larger policy.
- Quality metrics can overstate success if refined successes are mixed into
  unrefined successes without distinction. Add explicit refined outcome counts
  and slices.

## Notes

This plan should make failure repair explicit before larger Stage 3 features such
as tool expansion, branching trajectories, and AgentInstruct-style seed
transformation. Do not add new tools or distributed orchestration in this slice;
the goal is to close the local refine-rerun-report loop with lineage strong
enough to support later automation.
