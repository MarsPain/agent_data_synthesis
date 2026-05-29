# Plan 0016: Candidate Execution Boundary and Orchestration Readiness

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status

Planned on 2026-05-29. Completed on 2026-05-29. **Completed.**

## Goal

Turn the current candidate-level pipeline logic into an explicit, tested,
programmatic boundary that returns structured per-candidate outcomes without
changing default synchronous behavior or activating deferred async
orchestration.

## Architecture

The plan extracts candidate processing from `synthesis.pipeline` into a narrow
boundary that can later be called by a durable local runner. The synchronous
pipeline remains the only active runtime path and continues to own run setup,
artifact writing, manifest assembly, and ordered duplicate admission. The new
candidate boundary should be deterministic, side-effect-minimized, and explicit
about the shared state it still requires, especially accepted duplicate
signatures and curated tool admission.

## Tech Stack

- Python standard library dataclasses and unittest.
- Existing local pipeline modules under `synthesis/`.
- Existing artifact validation through `scripts/validate_docs.py` and
  `uv run python -m unittest`.

---

## Basis

This plan is derived from the current roadmap and deferred orchestration plan,
not from `TD-0001`.

- [../../PLANS.md](../../PLANS.md) had no active plans before this plan, keeps
  [../deferred/0014-async-local-orchestration-with-durable-queues.md](../deferred/0014-async-local-orchestration-with-durable-queues.md)
  deferred, and records `TD-0001` as resolved by
  [../completed/0015-generated-code-sandboxing-and-executable-admission-controls.md](../completed/0015-generated-code-sandboxing-and-executable-admission-controls.md).
- [../../BACKEND.md](../../BACKEND.md) declares `synthesis.orchestration` as the
  future owner of jobs, queues, cancellation, and metrics, while preserving a
  synchronous local pipeline today.
- [../../DESIGN.md](../../DESIGN.md) treats orchestration as a bounded context
  and calls for local, deterministic implementation before distributed workers.
- Plan 0014 expects an async runner to call a clean candidate-level pipeline
  boundary, but the current implementation still performs candidate processing
  through private functions that mutate shared sample, rejection, review,
  proposal, and duplicate-signature collections.
- Plan 0015 removed the generated-code admission blocker, but it did not change
  the synchronous pipeline shape or enable executable future roles.

## Scope

- Add characterization tests that lock the current default, branching,
  task-expansion, MCP-adapter, source-governance, network-source fixture, and
  sandbox fixture artifact behavior before refactoring.
- Add a candidate-processing boundary with typed context, options, and outcome
  records.
- Move the current single-candidate gate sequence behind that boundary:
  candidate schema validation, generation lineage attachment, policy generation,
  execution, adapter rejection handling, verification, duplicate gate, logical
  support gate, optional tool proposal rerun, and optional critic refinement.
- Make per-candidate outcomes return samples, rejections, review records, tool
  proposal records, and accepted duplicate signatures instead of mutating the
  pipeline's artifact lists directly.
- Keep ordered duplicate admission in the synchronous pipeline so current sample
  order and rejection counts remain stable.
- Document the remaining orchestration constraints that still block direct
  implementation of plan 0014, especially environment isolation, curated tool
  registry mutation, and artifact merge ordering.
- Preserve all existing CLI flags, default output paths, artifact schemas,
  manifest fields, quality report slices, and disabled future-role guardrails.

## Out of Scope

- Implementing plan 0014's async runner, durable queue, cancellation, or
  resumption.
- Adding `synthesis.orchestration` runtime behavior.
- Enabling `environment_generation`, `verifier_generation`, arbitrary generated
  tool handlers, external MCP servers, browser automation, or user-provided
  executable packages.
- Implementing semantic duplicate detection (`TD-0002`).
- Changing artifact schema versions, accepted sample counts, or rejection
  semantics.
- Replacing the local generated-code sandbox helper with container, VM, seccomp,
  or OS sandboxing.

## File Map

- Create `synthesis/candidate_processing.py` for the extracted candidate
  boundary, candidate context/options/outcome records, and the private helpers
  that currently live in `synthesis.pipeline`.
- Modify `synthesis/pipeline.py` to keep run setup and artifact writing while
  delegating each raw candidate to `process_candidate_through_gates`.
- Modify `tests/test_foundation_pipeline.py` with characterization coverage for
  artifact equivalence and unchanged fixture behavior.
- Add `tests/test_candidate_processing.py` for the new candidate boundary,
  including pure outcome records, review routing, tool proposal records, and
  duplicate-signature handling.
- Modify `docs/BACKEND.md` only if implementation reveals a more precise
  candidate boundary description that should become canonical backend context.
- Update this plan as tasks complete. When accepted, move it to
  `docs/exec-plans/completed/` and update [../../PLANS.md](../../PLANS.md).

## Implementation Tasks

### Task 1: Lock Current Pipeline Behavior with Characterization Tests

- [x] Add tests in `tests/test_foundation_pipeline.py` that compare direct and
  refactored-sensitive fixture paths by stable artifact content rather than only
  accepted/rejected counts.
- [x] Cover these deterministic paths:
  - default foundation run;
  - `enable_branching=True`;
  - `enable_task_expansion=True`;
  - `enable_mcp_adapter=True`;
  - `enable_source_governance_fixture=True`;
  - `enable_sandbox_fixture=True`;
  - controlled network source with a fixture-backed HTTP client through the CLI
    or existing helper path.
- [x] Normalize volatile paths and dataset ids in test helpers before comparing
  artifacts. Do not weaken assertions by comparing only file existence.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_foundation_pipeline tests.test_cli
  ```

  Expected result: all selected tests pass before refactoring begins.

### Task 2: Define Candidate Boundary Records

- [x] Create `synthesis/candidate_processing.py`.
- [x] Move or define these aliases in the new module without changing their
  callable signatures:

  ```python
  PolicyGenerator = Callable[[CandidateTask], SolutionPolicy]
  ToolProposalGenerator = Callable[[CapabilityGap], ToolProposal]
  ```

- [x] Add immutable records:

  ```python
  @dataclass(frozen=True)
  class CandidateProcessingContext:
      dataset_version: str
      environment: ContactEnvironment
      registry: ToolRegistry
      adapter_shim: LocalContactsAdapterShim | None
      verifier: ExactAnswerVerifier
      llm_config: LLMConfig
      generate_policy: PolicyGenerator


  @dataclass(frozen=True)
  class CandidateProcessingOptions:
      route_reviewable_failures: bool = False
      refiner: Refiner | None = None
      tool_proposal_generator: ToolProposalGenerator | None = None


  @dataclass(frozen=True)
  class CandidateProcessingOutcome:
      sample: dict[str, object] | None
      rejection: dict[str, object] | None
      review_records: tuple[dict[str, object], ...] = ()
      tool_proposal_records: tuple[dict[str, object], ...] = ()
      accepted_signature: tuple[str, tuple[str, ...]] | None = None
  ```

- [x] Keep `CandidateAttemptResult` private to the new module unless tests need
  to assert its behavior directly.
- [x] Add unit tests in `tests/test_candidate_processing.py` that instantiate
  the records and verify tuple defaults are immutable, explicit, and empty.

### Task 3: Extract Single-Candidate Processing Without Behavior Changes

- [x] Move `_process_candidate_through_gates`, `_run_candidate_attempt`,
  `_maybe_expand_tool_and_rerun`, `_attach_tool_proposal_to_rejection`,
  `_adapter_rejection_record`, `_maybe_refine`, `_ensure_generation_lineage`,
  and `_maybe_route_review` from `synthesis.pipeline` into
  `synthesis.candidate_processing`.
- [x] Rename `_process_candidate_through_gates` to
  `process_candidate_through_gates` and make it return
  `CandidateProcessingOutcome`.
- [x] Keep `_run_candidate_attempt` private and unchanged except for imports and
  the call boundary.
- [x] Ensure `process_candidate_through_gates` accepts:

  ```python
  def process_candidate_through_gates(
      *,
      raw_task: CandidateTask,
      context: CandidateProcessingContext,
      accepted_signatures: set[tuple[str, tuple[str, ...]]],
      options: CandidateProcessingOptions,
  ) -> CandidateProcessingOutcome:
      ...
  ```

- [x] Make the function accumulate local `review_records` and
  `tool_proposal_records`, then return them in the outcome. It must not append
  directly to the pipeline-level `samples`, `rejections`, `review_records`, or
  `tool_proposal_records` lists.
- [x] Add focused tests for:
  - valid candidate returns a sample and accepted signature;
  - invalid candidate schema returns one rejection and no sample;
  - review routing returns review records only when
    `route_reviewable_failures=True`;
  - tool proposal rerun returns its proposal record with either the accepted
    sample or attached rejection details;
  - duplicate candidate returns `quality_duplicate` when the accepted signature
    already exists.

### Task 4: Refactor `run_foundation_pipeline` to Apply Outcomes

- [x] In `synthesis/pipeline.py`, build one `CandidateProcessingContext` after
  environment, registry, adapter, verifier, LLM config, and policy generator are
  initialized.
- [x] Build one `CandidateProcessingOptions` from the existing
  `route_reviewable_failures`, `refiner`, and `tool_proposal_generator`
  arguments.
- [x] Replace direct calls to `_process_candidate_through_gates` with
  `process_candidate_through_gates`.
- [x] Add a small pipeline-local helper such as:

  ```python
  def _apply_candidate_outcome(
      outcome: CandidateProcessingOutcome,
      *,
      samples: list[dict[str, object]],
      rejections: list[dict[str, object]],
      review_records: list[dict[str, object]],
      tool_proposal_records: list[dict[str, object]],
      accepted_signatures: set[tuple[str, tuple[str, ...]]],
  ) -> None:
      ...
  ```

- [x] The helper must:
  - append `outcome.sample` only when present;
  - append `outcome.rejection` only when present;
  - extend review and proposal records from the outcome tuples;
  - add `outcome.accepted_signature` only after appending the accepted sample;
  - raise `RuntimeError` if an outcome contains both a sample and a rejection or
    neither one.
- [x] Preserve candidate processing order for base candidates and expanded
  candidates exactly as today.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_candidate_processing tests.test_foundation_pipeline
  ```

  Expected result: all selected tests pass with unchanged artifact semantics.

### Task 5: Document Remaining Orchestration Constraints

- [x] Update [../../BACKEND.md](../../BACKEND.md) with a short paragraph under
  `Scaling Direction` or `Job Lifecycle` describing the new candidate boundary.
- [x] State explicitly that the boundary is orchestration-ready but not
  concurrency-safe until a future plan defines:
  - per-candidate environment checkpoint/reset isolation;
  - curated tool registry mutation rules for tool-expansion reruns;
  - deterministic duplicate admission when candidates complete out of order;
  - manifest and quality-report merge ordering for durable queues.
- [x] Keep [../../../AGENTS.md](../../../AGENTS.md) unchanged unless commands or
  operating rules change. This plan should not add volatile detail to the agent
  map.
- [x] Run:

  ```bash
  uv run python scripts/validate_docs.py
  ```

  Expected result: `Documentation validation passed.`

### Task 6: Full Validation and Completion Handoff

- [x] Run the full unit suite:

  ```bash
  uv run python -m unittest
  ```

  Expected result: all tests pass.

- [x] Run deterministic fixture commands:

  ```bash
  uv run python main.py --output-dir artifacts/foundation
  uv run python main.py --enable-branching --output-dir artifacts/foundation-branching
  uv run python main.py --enable-task-expansion --output-dir artifacts/foundation-task-expansion
  uv run python main.py --enable-mcp-adapter --output-dir artifacts/foundation-mcp-adapter
  uv run python main.py --enable-sandbox-fixture --output-dir artifacts/foundation-sandbox
  ```

  Expected result: each command completes with stable accepted/rejected counts
  matching the current deterministic fixture behavior.

- [x] Update this plan's task checkboxes during implementation.
- [x] When accepted as complete, move this file to `../completed/`, change
  status to completed with the completion date, and update
  [../../PLANS.md](../../PLANS.md), [../../../README.md](../../../README.md),
  and any affected roadmap wording.

## Acceptance Criteria

- `run_foundation_pipeline` still exposes the same public API and produces the
  same deterministic artifacts for all existing fixture paths.
- Candidate processing is callable through a named boundary with typed context,
  options, and outcome records.
- Per-candidate processing no longer mutates pipeline-level sample, rejection,
  review, or tool-proposal collections directly.
- Duplicate admission remains ordered and deterministic in the synchronous
  pipeline.
- Tool-expansion, refinement, adapter, source-governance, sandbox fixture, and
  task-expansion behaviors remain unchanged.
- Disabled executable roles remain disabled, and generated-code sandbox
  admission remains opt-in fixture behavior only.
- Remaining blockers for plan 0014 are explicitly documented rather than hidden
  behind the refactor.
- `uv run python scripts/validate_docs.py` and `uv run python -m unittest` pass.

## Risks

- Moving private helpers can accidentally change rejection details or lineage
  fields. Characterization tests should compare artifact content, not only
  counts.
- Tool proposal reruns can mutate the curated registry. This plan preserves
  current behavior but documents that async execution needs stricter isolation.
- Duplicate detection is order-dependent. This plan keeps synchronous ordering
  stable and defers concurrent duplicate admission rules to a future
  orchestration plan.
- Splitting code may create import cycles if `synthesis.pipeline` and
  `synthesis.candidate_processing` import each other. The new module should
  import concrete dependencies directly and avoid importing pipeline internals.

## Notes

This plan is an orchestration-readiness refactor. It does not reopen `TD-0001`,
does not implement `TD-0002`, and does not activate deferred plan 0014.
