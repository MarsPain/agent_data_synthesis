# Plan 0002: Data Contracts and Quality Gates

## Status

Active.

## Goal

Turn the foundation runner's implicit JSON records into enforceable data contracts and quality gates so generated samples, rejections, and manifests can be validated before they are treated as dataset artifacts.

## Basis

This plan is the next step after [0001-foundation](../completed/0001-foundation.md) because the current code proves the local executable loop, while the repository docs already define contract and quality expectations that are not yet enforced in code:

- [../../ROADMAP.md](../../ROADMAP.md) Stage 2 calls for quality and curriculum work, including logical validators, diversity metrics, failure classification, metric slicing, and parent-version comparison reports.
- [../../DATA.md](../../DATA.md) defines canonical entities, the dataset output contract, quality metrics, versioning rules, incremental regeneration rules, and LLM lineage requirements.
- [../../DESIGN.md](../../DESIGN.md) requires executable, verifiable, versioned training trajectories with environment-tool-task consistency, multidimensional quality, and mandatory lineage.
- [../../design-docs/agent-data-synthesis-framework.md](../../design-docs/agent-data-synthesis-framework.md) makes data contracts mandatory for accepted samples and lists MVP quality gates such as schema validation, environment reset, tool smoke tests, classified execution failures, verifier pass, lineage completeness, and duplicate checks.
- [../../BACKEND.md](../../BACKEND.md) assigns sample assembly, manifests, exports, and version comparison to `synthesis.datasets`, and records candidate failure routing as part of the backend job lifecycle.

## Scope

- Define typed contract models or schema validators for samples, manifests, rejections, and core trajectory events.
- Validate accepted samples before writing them to JSONL.
- Validate rejection records before writing them to JSONL.
- Validate manifests before writing them to disk.
- Add lineage completeness checks for accepted samples.
- Add environment reset and registered-tool smoke checks to the foundation pipeline.
- Expand failure classification to distinguish schema errors from tool runtime errors and verifier failures.
- Add quality-gate tests that fail on malformed samples, malformed rejections, missing lineage fields, and unclassified execution errors.
- Keep the implementation local and fixture-backed; do not add distributed orchestration, MCP adapters, generated-code execution, or LLM-as-judge in this plan.

## Acceptance Criteria

- `uv run python main.py` still generates at least one accepted sample and one classified rejection from the foundation fixture.
- Accepted sample JSONL records are validated against the implemented contract before writing.
- Rejection JSONL records are validated against the implemented contract before writing.
- `manifest.json` is validated before writing and includes enough fields to support parent-version comparison later.
- Pipeline failures caused by candidate shape, tool schema, tool runtime, and verification failures are classified by cause.
- Tests cover both valid foundation outputs and representative invalid contract records.
- `uv run python scripts/validate_docs.py` passes.
- `uv run python -m unittest` passes.

## Out of Scope

- Semantic duplicate detection beyond exact or fixture-level checks.
- LLM-as-judge scoring.
- Human review queue implementation.
- Generated code sandboxing.
- Multi-domain or distributed execution.

## Risks

- Over-specified schemas could churn while the framework is still learning its data shape.
- Loose schemas could preserve today’s flexibility but fail to catch broken training records.
- Quality metrics can become misleading if they are reported without slice dimensions such as domain, difficulty, tool combination, generator role, and verifier type.

## Notes

Prefer a small contract layer that validates the records the foundation runner already produces. Expand toward full schema generation and version comparison only after the first validation gates are stable.
