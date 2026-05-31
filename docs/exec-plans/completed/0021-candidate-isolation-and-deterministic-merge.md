# Plan 0021: Candidate Isolation and Deterministic Merge

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status

Planned on 2026-05-31. Completed on 2026-05-31.

## Goal

Make candidate processing safe to reuse from a future local async runner by
separating per-candidate provisional execution from ordered dataset admission,
while preserving the current synchronous CLI behavior and artifact output.

This plan does not activate async orchestration. It closes the remaining
concurrency-safety gap identified after plans 0016-0020: candidates can already
return structured outcomes, but they still execute against shared environment
and registry objects and they still depend on live ordered duplicate admission
state during processing.

## Architecture

The synchronous pipeline remains the only runtime path. This plan introduces an
explicit candidate isolation and merge boundary inside that synchronous path:

- candidate execution produces provisional outcomes without mutating global
  sample, rejection, review, proposal, or duplicate-admission collections;
- environment and adapter state are reset or rebuilt per candidate so a future
  worker cannot leak state across candidates;
- curated tool admission produced by tool-expansion reruns is scoped and
  serialized so registry mutations cannot depend on candidate completion order;
- dataset admission merges provisional outcomes by stable candidate sequence,
  then applies duplicate and logical-quality gates deterministically;
- artifact writing stays in `synthesis.datasets`.

The end state should still run candidates serially, but the serial path should
exercise the same isolation and merge contracts that a later durable queue would
use.

## Tech Stack

- Python standard library dataclasses, path handling, JSON-compatible mappings,
  and `unittest`.
- Existing modules: `synthesis.pipeline`, `synthesis.candidate_processing`,
  `synthesis.environments`, `synthesis.tools`, `synthesis.mcp`,
  `synthesis.quality`, and `synthesis.datasets`.
- Existing validation through `scripts/validate_docs.py` and
  `uv run python -m unittest`.

---

## Basis

- [../../PLANS.md](../../PLANS.md) has no active implementation plan before this
  plan and keeps
  [../deferred/0014-async-local-orchestration-with-durable-queues.md](../deferred/0014-async-local-orchestration-with-durable-queues.md)
  deferred until single runs exceed about 10 minutes or 100+ candidates.
- [../completed/0016-candidate-execution-boundary-and-orchestration-readiness.md](../completed/0016-candidate-execution-boundary-and-orchestration-readiness.md)
  extracted a structured candidate-processing boundary but intentionally kept
  ordered duplicate admission in the synchronous pipeline.
- [../completed/0020-profile-decision-gates-and-benchmark-reporting.md](../completed/0020-profile-decision-gates-and-benchmark-reporting.md)
  added decision reports that currently keep async orchestration and semantic
  duplicate detection deferred for the deterministic 25-candidate scale probe.
- [../../BACKEND.md](../../BACKEND.md) records that the candidate-processing
  boundary is orchestration-ready but not concurrency-safe yet. It specifically
  calls out per-candidate environment isolation, curated tool registry mutation
  rules, deterministic duplicate admission when candidates complete out of
  order, and manifest/quality-report merge ordering.
- The current synchronous pipeline creates one environment, registry, adapter
  shim, verifier, and duplicate-signature set, then processes raw candidates in
  order. That is acceptable for serial execution but is not a sufficient contract
  for a future durable queue or async runner.

## Scope

- Add tests that characterize current deterministic artifact output for default,
  scale-probe, branching, task-expansion, MCP-adapter, source-governance, and
  sandbox-fixture paths before changing merge mechanics.
- Define a provisional candidate outcome contract that carries:
  - stable candidate sequence/index;
  - candidate id where available;
  - candidate-stage sample or rejection;
  - review records;
  - tool proposal records;
  - duplicate signature candidate;
  - environment isolation metadata;
  - optional registry/tool-expansion metadata.
- Move duplicate admission out of the candidate attempt body and into a stable
  merge/admission phase. The merge phase should process provisional outcomes in
  candidate sequence order, update accepted signatures deterministically, and
  convert later duplicates into `quality_duplicate` rejections without depending
  on candidate completion order.
- Define and implement per-candidate environment isolation for the contacts
  fixture path. Prefer rebuilding/resetting from the existing environment input
  or reset recipe over sharing mutable runtime state across candidates.
- Define registry mutation rules for curated tool admission:
  - candidate-local reruns may use an admitted curated tool for that candidate;
  - global registry state must not depend on provisional completion order;
  - exported tool proposal records must remain ordered by candidate sequence.
- Add a merge boundary that combines samples, rejections, review records, tool
  proposals, and accepted signatures into the same ordered lists currently sent
  to `write_dataset_artifacts()`.
- Keep default CLI flags, output paths, schema versions, manifest fields,
  quality report shape, and accepted/rejected counts stable.
- Update canonical docs to describe the isolation and deterministic merge
  contracts once implemented.

## Out of Scope

- Implementing the async runner, durable queue, cancellation, resumption, or
  per-role async cost tracking from plan 0014.
- Adding `synthesis.orchestration` runtime behavior.
- Implementing semantic duplicate detection from `TD-0002`.
- Adding embeddings, vector stores, local models, dashboards, REST APIs,
  external queues, distributed workers, or monitoring exporters.
- Enabling external MCP servers, generated environment/tool/verifier handlers,
  browser automation, arbitrary file ingestion, or user-provided executable
  packages.
- Changing sample schema versions, quality report schema versions, verifier
  semantics, source governance policy, sandbox admission policy, or disabled role
  guardrails.

## Contract Sketch

The exact record names can change during implementation, but the contract should
preserve these responsibilities:

```python
@dataclass(frozen=True)
class CandidateExecutionRequest:
    sequence_index: int
    raw_task: CandidateTask


@dataclass(frozen=True)
class ProvisionalCandidateOutcome:
    sequence_index: int
    candidate_id: str
    sample: dict[str, object] | None
    rejection: dict[str, object] | None
    review_records: tuple[dict[str, object], ...]
    tool_proposal_records: tuple[dict[str, object], ...]
    duplicate_signature: tuple[str, tuple[str, ...]] | None
    environment_isolation: dict[str, object]
    registry_mutations: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class CandidateMergeResult:
    samples: tuple[dict[str, object], ...]
    rejections: tuple[dict[str, object], ...]
    review_records: tuple[dict[str, object], ...]
    tool_proposal_records: tuple[dict[str, object], ...]
    accepted_signatures: frozenset[tuple[str, tuple[str, ...]]]
```

The merge operation must be deterministic:

1. Sort provisional outcomes by `sequence_index`.
2. For each outcome with a sample and duplicate signature, admit it only if the
   signature has not already been accepted.
3. If the signature was already accepted, convert the outcome to a
   `quality_duplicate` rejection that preserves candidate id, task, policy
   details where available, and the duplicate signature.
4. Append review records and tool proposal records in candidate sequence order.
5. Emit the same artifact content as the current synchronous path for all
   deterministic fixtures.

## File Map

- Modify `synthesis/candidate_processing.py`:
  - separate provisional candidate execution from duplicate admission;
  - return duplicate-signature candidates without consulting global accepted
    signatures where possible;
  - preserve existing rejection handling, review routing, tool proposal reruns,
    refinement reruns, adapter rejections, and logical-support checks.
- Modify `synthesis/pipeline.py`:
  - build candidate execution requests with stable sequence indexes;
  - create isolated per-candidate execution contexts;
  - merge provisional outcomes through the deterministic admission boundary;
  - keep run setup, source governance, task expansion, sandbox fixtures, and
    artifact writing in the pipeline.
- Modify `synthesis/environments.py` if needed:
  - expose a reset/rebuild helper that can create a candidate-isolated contacts
    environment from existing fixture or admitted source input metadata.
- Modify `synthesis/tools.py` if needed:
  - expose a copy/rebuild path for registry state or a candidate-local admission
    helper for curated tool-expansion reruns.
- Modify `synthesis/mcp.py` if needed:
  - ensure the local contacts adapter shim is rebuilt against each isolated
    environment/registry pair.
- Add or modify tests:
  - `tests/test_candidate_processing.py`;
  - `tests/test_foundation_pipeline.py`;
  - `tests/test_cli.py` only if CLI-facing artifact behavior needs coverage;
  - a new `tests/test_candidate_merge.py` if the merge boundary warrants its own
    module.
- Update docs after implementation:
  - [../../BACKEND.md](../../BACKEND.md) with the implemented isolation and
    merge boundary;
  - [../../DATA.md](../../DATA.md) only if exported artifact contracts change or
    new internal merge records are documented;
  - [../../ROADMAP.md](../../ROADMAP.md) when this active plan is completed;
  - [../../PLANS.md](../../PLANS.md) and this active plan's status.

## Implementation Tasks

### Task 1: Characterize Current Artifact Behavior

- [ ] Add or strengthen tests that capture normalized artifact content for:
  - default foundation run;
  - deterministic 25-candidate scale probe;
  - `enable_branching=True`;
  - `enable_task_expansion=True`;
  - `enable_mcp_adapter=True`;
  - `enable_source_governance_fixture=True`;
  - `enable_sandbox_fixture=True`;
  - profile-local contacts source if existing fixtures make this cheap.
- [ ] Assert stable accepted/rejected counts and key quality-report slices,
  especially `quality_duplicate`, profile slices, adapter slices, source slices,
  sandbox slices, and tool proposal slices where relevant.
- [ ] Normalize volatile output paths, config hashes only when necessary, and
  timestamps before comparing artifacts.
- [ ] Run:

  ```bash
  uv run python -m unittest tests.test_foundation_pipeline tests.test_candidate_processing tests.test_cli
  ```

  Expected result before implementation: all selected characterization tests
  pass.

### Task 2: Define Provisional Outcome and Merge Records

- [ ] Add immutable request/outcome/merge records in the narrowest appropriate
  module, preferring `synthesis.candidate_processing` unless a separate
  `synthesis.candidate_merge` module is clearer.
- [ ] Add tests that prove the merge boundary:
  - sorts by sequence index;
  - admits the first duplicate signature and rejects later duplicates;
  - handles outcomes arriving out of order;
  - preserves review and tool proposal ordering by candidate sequence;
  - rejects malformed outcomes with exactly-one-sample-or-rejection violations.
- [ ] Keep record fields JSON-compatible where they may be serialized later by a
  durable queue, but do not add queue persistence in this plan.

### Task 3: Move Duplicate Admission into the Merge Boundary

- [ ] Refactor `_run_candidate_attempt` or its surrounding boundary so successful
  execution returns a sample plus duplicate-signature candidate without checking
  a shared accepted-signature set.
- [ ] Implement duplicate rejection creation in the merge boundary with the same
  `quality_duplicate` cause and equivalent details to the current synchronous
  path.
- [ ] Preserve logical-support validation semantics. Logical failures should
  still be rejected before duplicate admission.
- [ ] Update focused tests for valid sample, duplicate sample, invalid schema,
  review routing, refinement, and tool proposal rerun behavior.

### Task 4: Add Per-Candidate Environment and Adapter Isolation

- [ ] Identify the minimal reset/rebuild contract for `ContactEnvironment` that
  supports both fixture-backed and profile/source-admitted contacts inputs.
- [ ] Ensure each candidate execution context receives isolated environment
  state and a registry bound to that environment.
- [ ] Rebuild the local MCP adapter shim per isolated context when
  `enable_mcp_adapter=True`.
- [ ] Add tests proving state changes from one candidate cannot affect a later
  candidate except through deterministic merge/admission state.

### Task 5: Define Tool Registry Mutation Rules

- [ ] Audit curated tool admission in tool-expansion reruns and document whether
  admitted tools are candidate-local, staged run-global, or rebuildable from a
  deterministic registry mutation record.
- [ ] Implement the smallest rule that preserves current behavior while avoiding
  completion-order-dependent global registry state.
- [ ] Add tests for accepted and rejected tool proposal reruns under isolated
  candidate contexts.

### Task 6: Wire the Synchronous Pipeline Through the New Boundary

- [ ] Build stable `CandidateExecutionRequest` values for base candidates and
  expanded candidates.
- [ ] Execute requests serially for now, but collect provisional outcomes and
  merge them through the deterministic admission boundary.
- [ ] Keep task suggestion/editor rejections ordered before expanded candidate
  outcomes as they are today unless characterization tests prove a different
  existing order.
- [ ] Verify artifact output remains stable for all characterized paths.

### Task 7: Documentation and Validation

- [ ] Update [../../BACKEND.md](../../BACKEND.md) with the implemented isolation
  and deterministic merge contract.
- [ ] Update [../../DATA.md](../../DATA.md) only if exported artifact contracts
  or documented internal records change.
- [ ] Update [../../ROADMAP.md](../../ROADMAP.md), [../../PLANS.md](../../PLANS.md),
  and plan bucket indexes when this plan is completed.
- [ ] Run:

  ```bash
  uv run python scripts/validate_docs.py
  uv run python -m unittest
  uv run python main.py --run-profile tests/fixtures/run_profiles/foundation-scale-probe-25.json --write-profile-decision-report --output-dir artifacts/foundation-scale-probe
  ```

## Validation

- `uv run python scripts/validate_docs.py`
- `uv run python -m unittest`
- `uv run python main.py --run-profile tests/fixtures/run_profiles/foundation-scale-probe-25.json --write-profile-decision-report --output-dir artifacts/foundation-scale-probe`

Expected scale-probe decision after this plan: `async_orchestration` remains
`defer`, `semantic_duplicate_detection` remains `defer`, and
`mvp_quality_floor` remains `passed` unless the user explicitly changes
thresholds or fixtures.

Completed validation on 2026-05-31:

- `uv run python scripts/validate_docs.py`: passed.
- `uv run python -m unittest`: 191 tests passed.
- Scale-probe run: accepted 14, rejected 11.
- Profile decision report: `async_orchestration=defer`,
  `semantic_duplicate_detection=defer`, and `mvp_quality_floor=passed`.

## Acceptance Criteria

- Default synchronous pipeline behavior is preserved.
- The deterministic 25-candidate scale probe still reports 14 accepted and 11
  rejected candidates.
- Candidate outcomes can be merged deterministically even when provisional
  outcomes arrive out of order.
- Duplicate admission depends on stable candidate sequence, not runtime
  completion order.
- Candidate execution uses isolated environment/adapter state.
- Tool-expansion registry behavior is documented and cannot depend on candidate
  completion order.
- Artifact writing remains centralized in `synthesis.datasets`.
- No async runner, durable queue, cancellation, resumption, or external worker
  behavior is introduced.
- Documentation validation and the full unit suite pass.

## Risks

- Moving duplicate admission can subtly change which duplicate is accepted. Keep
  sequence-index ordering explicit and lock it with tests.
- Environment rebuilding can change lineage or source-provenance metadata. Reuse
  existing environment metadata and source-policy hashes rather than inventing
  new values.
- Tool-expansion reruns may currently rely on registry mutation side effects.
  Make the mutation scope explicit before changing code.
- Task-expansion ordering combines rejected suggestions, rejected edits, and
  expanded candidates. Preserve current artifact order unless tests show it is
  already unstable.
- Overbuilding the isolation layer could drift into plan 0014. Stop at in-memory
  records and synchronous merge.

## Notes

This plan is the final local-contract hardening step before plan 0014 can be
reactivated on evidence. It should make future durable queue work smaller and
safer, but it should not add queue files, workers, signal handling, or job
lifecycle records yet.
