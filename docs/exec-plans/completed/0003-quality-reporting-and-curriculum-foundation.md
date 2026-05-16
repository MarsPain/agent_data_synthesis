# Plan 0003: Quality Reporting and Curriculum Foundation

## Status

Completed on 2026-05-16.

## Goal

Turn the contract-validated foundation runner into a measurable Stage 2 quality loop by adding structured quality reports, metric slicing, exact duplicate gates, parent-version comparison, and first-pass curriculum metadata.

## Basis

This plan follows [0002-data-contracts-and-quality-gates](../completed/0002-data-contracts-and-quality-gates.md). The foundation runner now validates accepted samples, rejections, and manifests, but Stage 2 still needs dataset-level visibility and curriculum controls before the framework can safely expand beyond a single deterministic fixture:

- [../../ROADMAP.md](../../ROADMAP.md) Stage 2 calls for difficulty scoring, curriculum policies, logical validators, diversity metrics, failure classification and retry loops, human review queue format, metric slicing, and parent-version comparison reports.
- [../../DATA.md](../../DATA.md) requires metrics to be sliceable by domain, task type, difficulty level, tool combination, generator role, verifier type, and dataset version.
- [../../DESIGN.md](../../DESIGN.md) treats lineage, quality, and versioned training trajectories as mandatory output properties.
- [../../design-docs/agent-data-synthesis-framework.md](../../design-docs/agent-data-synthesis-framework.md) lists duplicate checks, diversity checks, quality trend monitoring, curriculum effectiveness, and parent-version comparison as quality-layer responsibilities.
- [../../BACKEND.md](../../BACKEND.md) assigns task generation and curriculum policy to `synthesis.tasks`, execution retry behavior to `synthesis.execution`, verification checks to `synthesis.verification`, and manifests/version comparison to `synthesis.datasets`.

## Scope

- Add a structured `quality_report.json` artifact beside `samples.jsonl`, `rejections.jsonl`, and `manifest.json`.
- Add deterministic metric slicing for dataset version, domain, difficulty level, tool combination, generator role, verifier type, and rejection cause.
- Add exact duplicate detection for accepted samples using task instruction plus ordered tool sequence.
- Add logical consistency validation for the current foundation trajectory shape: final answers must be supported by observations and verifier expectations.
- Add first-pass curriculum metadata and ordering for local fixture tasks without introducing a multi-domain generator.
- Add parent-version comparison support by reading a prior manifest or quality report from a configured local path and reporting count, quality, coverage, and rejection-cause deltas.
- Add a human-review queue record format for uncertain or policy-routed samples, but do not build an interactive review UI.
- Keep retry-loop design local and bounded: classify retryable failure causes and record retry eligibility, but do not add distributed orchestration.

## Out of Scope

- Semantic duplicate detection beyond exact task and tool-sequence identity.
- LLM-as-judge quality scoring.
- Interactive human review UI.
- Multi-domain environment generation.
- Generated-code execution or sandbox implementation.
- Distributed queues, workers, or MCP adapters.

## Architecture

The next slice should keep Stage 2 concerns explicit without turning `synthesis.datasets` into a catch-all:

- `synthesis.quality`: quality metrics, slices, duplicate signatures, logical consistency checks, human-review records, and parent comparison report assembly.
- `synthesis.tasks`: curriculum metadata and deterministic task ordering.
- `synthesis.datasets`: artifact writing, manifest references, and quality report path plumbing.
- `synthesis.pipeline`: orchestration of gates, report generation, retry eligibility, and optional parent comparison inputs.
- `tests/`: focused coverage for quality report shape, slice aggregation, duplicate gates, logical consistency failures, parent comparison deltas, and unchanged foundation behavior.

## File Map

- Create `synthesis/quality.py` for quality report models and pure report-building functions.
- Modify `synthesis/tasks.py` to expose curriculum metadata for generated fixture candidates.
- Modify `synthesis/datasets.py` to write `quality_report.json`, include it in manifest artifacts, and optionally write `parent_comparison.json`.
- Modify `synthesis/pipeline.py` to invoke duplicate and logical gates before accepting samples and to pass quality artifacts through the result object.
- Modify `main.py` to accept optional parent dataset artifact inputs only if the implementation needs a CLI entrypoint for comparison.
- Add `tests/test_quality_reporting.py` for report, slicing, duplicate, logical validation, and parent comparison tests.
- Extend `tests/test_foundation_pipeline.py` only for end-to-end artifact assertions.
- Update `docs/DATA.md` if the quality report artifact becomes part of the canonical output contract.

## Implementation Tasks

### Task 1: Add Quality Report Builder

- [x] Create `synthesis/quality.py` with pure functions for dataset-level metrics and slices.
- [x] Add tests that build a report from one valid sample and one verification rejection.
- [x] Assert the report includes total counts, success rate, executable rate, slice dimensions, and rejection cause counts.
- [x] Keep the report deterministic by sorting slice keys and artifact lists.

### Task 2: Wire Quality Report Artifact

- [x] Extend `DatasetArtifacts` with `quality_report_path`.
- [x] Write `quality_report.json` after sample and rejection validation.
- [x] Add the quality report filename to `manifest["artifacts"]`.
- [x] Validate that `uv run python main.py` still produces one accepted sample, one rejection, a manifest, and the new quality report.

### Task 3: Add Exact Duplicate Gate

- [x] Define a duplicate signature from normalized task instruction plus ordered action tool names.
- [x] Reject later accepted candidates with cause `quality_duplicate` when the exact signature already exists in the current batch.
- [x] Extend the rejection contract cause allowlist for `quality_duplicate`.
- [x] Add tests for duplicate acceptance prevention and manifest rejection-cause counts.

### Task 4: Add Logical Consistency Gate

- [x] Validate that each accepted final response is supported by at least one observation and by the verifier expected answer.
- [x] Reject unsupported trajectories with cause `solution_logic_error`.
- [x] Extend the rejection contract cause allowlist for `solution_logic_error`.
- [x] Add tests for unsupported final answers and for the existing accepted foundation sample.

### Task 5: Add Curriculum Metadata

- [x] Normalize task difficulty metadata into stable fields: `level`, `tool_count`, `constraint_count`, `state_changes`, `ambiguity`, and `recovery_paths`.
- [x] Add a deterministic curriculum order for fixture candidates from easiest to hardest.
- [x] Include curriculum fields in quality report slices.
- [x] Add tests that confirm fixture task ordering and slice output.

### Task 6: Add Parent-Version Comparison

- [x] Add a parent comparison builder that accepts current and parent manifest or quality report dictionaries.
- [x] Report accepted-count delta, rejected-count delta, success-rate delta, executable-rate delta, new and removed slice keys, and rejection-cause deltas.
- [x] Write `parent_comparison.json` when a parent artifact path is provided.
- [x] Add unit tests using small in-memory parent/current reports.

### Task 7: Add Human Review Queue Format

- [x] Define a JSONL review record shape with candidate id, cause, task, uncertainty reason, source artifact, and created timestamp.
- [x] Route duplicate and logical-consistency failures into review records only when a policy flag says they are reviewable.
- [x] Keep the default foundation run non-interactive and deterministic.
- [x] Add tests for review record validation and disabled-by-default behavior.

### Task 8: Refresh Docs and Validation

- [x] Update `docs/DATA.md` with the quality report, parent comparison, and review queue artifact contracts.
- [x] Update `docs/BACKEND.md` if module boundaries change after implementation.
- [x] Run `uv run python scripts/validate_docs.py`.
- [x] Run `uv run python -m unittest`.

## Acceptance Criteria

- `uv run python main.py` writes `samples.jsonl`, `rejections.jsonl`, `manifest.json`, and `quality_report.json`.
- The manifest references the quality report artifact.
- Quality reports include dataset-level counts, success and executable rates, rejection cause counts, and slices by the Stage 2 dimensions currently available in the foundation records.
- Exact duplicate accepted samples are rejected with classified cause `quality_duplicate`.
- Logical consistency failures are rejected with classified cause `solution_logic_error`.
- Fixture candidates include normalized curriculum metadata and deterministic ordering.
- Parent comparison logic reports count, rate, slice, and rejection-cause deltas for local parent/current artifacts.
- Human review queue records have a documented and tested JSONL shape, even if default routing is disabled.
- Tests cover report generation, slices, duplicate gates, logical gates, parent comparison, review record shape, and the default foundation run.
- `uv run python scripts/validate_docs.py` passes.
- `uv run python -m unittest` passes.

## Risks

- Quality report scope can sprawl into analytics before the dataset surface is stable.
- Duplicate checks can become misleading if exact matching is confused with semantic deduplication.
- Parent comparison can overstate improvement if slice coverage and rejection cause changes are not reported next to aggregate success rates.
- Human review records can become stale if they are not tied back to source artifact paths and candidate ids.

## Notes

Prefer pure report-building functions with small dictionaries over a heavy analytics dependency. This stage should create stable quality artifacts and gates that later generator, refinement, and orchestration work can consume.
