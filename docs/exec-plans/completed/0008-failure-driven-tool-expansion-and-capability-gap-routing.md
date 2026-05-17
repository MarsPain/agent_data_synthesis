# Plan 0008: Failure-Driven Tool Expansion and Capability Gap Routing

## Status

Completed on 2026-05-17.

## Goal

Make tool expansion an explicit, auditable Stage 3 loop: when generated tasks or
solution policies require a missing capability, the pipeline should classify the
gap, preserve lineage, optionally request a bounded tool proposal, and only
enable executable tools through a local curated implementation path.

## Basis

This plan follows
[0007-role-contracts-and-generator-orchestration](0007-role-contracts-and-generator-orchestration.md).
The repository now has role contracts, disabled future-role guardrails, remote
task generation, solution-policy execution, critic/refinement, and role-level
quality reporting. The next blocker in [../../ROADMAP.md](../../ROADMAP.md)
Stage 3 is tool expansion when failures indicate missing capability.

Relevant current constraints:

- [../../DESIGN.md](../../DESIGN.md) requires environment-tool-task consistency:
  tasks must only require tools that exist or are explicitly synthesized.
- [../../BACKEND.md](../../BACKEND.md) keeps provider calls behind
  `synthesis.llm` and role-specific modules behind validation boundaries.
- [../../DATA.md](../../DATA.md) requires lineage for LLM-backed generation,
  solution, refinement, and future generated tool steps without leaking secrets.
- [../../SECURITY.md](../../SECURITY.md) requires generated code and external
  surfaces to stay behind explicit sandbox and provenance rules.

## Scope

- Add first-class capability-gap diagnostics for `tool_missing`,
  `tool_schema_error`, and task/tool contract mismatches.
- Add a `ToolProposal` or equivalent data contract for requested capability,
  proposed tool name, schema, side-effect class, environment dependencies,
  verifier implications, and role lineage.
- Enable a narrow `tool_generation` role only for structured tool proposals, not
  executable Python code.
- Add a local curated tool catalog path that can turn approved proposals into
  known implementations in `synthesis.tools`.
- Extend the contacts fixture with one small missing-capability scenario that
  proves the loop: detect a gap, record the proposal, then satisfy it through a
  curated implementation.
- Add quality/reporting visibility for capability gaps and tool proposal
  outcomes.
- Keep generated code execution disabled.

## Out of Scope

- Arbitrary LLM-generated Python, shell commands, SQL migrations, or package
  installation.
- Network-backed tools, browser tools, MCP adapters, or external API calls.
- Generated environments or verifier generation beyond recording verifier impact.
- Branching behavior-tree trajectories or multi-path rollout.
- Human UI for proposal approval.
- Distributed workers or durable queues.

## Architecture

Tool expansion should remain a contract-and-registry flow:

- `synthesis.tools` owns executable tool definitions, schema validation, curated
  implementations, and proposal-to-tool admission checks.
- `synthesis.execution` and `synthesis.pipeline` classify missing-capability
  failures and decide whether to request a proposal.
- `synthesis.roles` enables `tool_generation` only after its output is narrowed
  to tool proposals and guarded by validation.
- `synthesis.llm` remains the only remote provider boundary.
- `synthesis.contracts` validates proposal records and keeps rejection causes
  explicit.
- `synthesis.datasets` serializes proposal artifacts, rejection details, and
  manifest references.
- `synthesis.quality` reports capability-gap and tool-proposal metrics without
  treating proposals as accepted samples.

## File Map

- Modify `synthesis/roles.py` to enable `tool_generation` with an explicit
  proposal-oriented version and output type.
- Modify `synthesis/tools.py` with proposal contracts, validation helpers,
  curated catalog registration, and one new contacts-domain tool.
- Modify `synthesis/execution.py` only as needed to expose missing tool names and
  schema details without broad exception parsing.
- Modify `synthesis/pipeline.py` to route eligible tool gaps through proposal
  generation and curated admission.
- Modify `synthesis/contracts.py` for proposal validation and any new rejection
  causes.
- Modify `synthesis/datasets.py` to write proposal artifacts and manifest paths.
- Modify `synthesis/quality.py` to add capability-gap and tool-proposal slices.
- Add or extend tests in `tests/test_tools.py`, `tests/test_roles.py`,
  `tests/test_foundation_pipeline.py`, `tests/test_quality_reporting.py`, and
  `tests/test_contracts.py`.
- Update [../../BACKEND.md](../../BACKEND.md), [../../DATA.md](../../DATA.md),
  [../../SECURITY.md](../../SECURITY.md), and
  [../../ROADMAP.md](../../ROADMAP.md) when implementation lands.

## Implementation Tasks

### Task 1: Define Capability-Gap Records

- [x] Add a stable record shape for missing capability diagnostics.
- [x] Distinguish unknown tool, incompatible arguments, unavailable side effect,
  and environment dependency mismatch.
- [x] Preserve candidate id, policy id, tool name, schema details, rejection
  cause, retry eligibility, and source role lineage.
- [x] Add contract tests for valid and invalid gap records.

### Task 2: Add Tool Proposal Contract

- [x] Add a structured proposal value with name, description, JSON schema,
  side-effect class, required environment state, verifier impact, safety notes,
  and lineage.
- [x] Add strict parser and validator for remote `tool_generation` output.
- [x] Reject malformed proposals with `llm_response_schema_error`.
- [x] Keep proposal records separate from executable tool definitions.

### Task 3: Enable Bounded Tool Generation Role

- [x] Change `tool_generation` from disabled guardrail to enabled proposal role.
- [x] Update role version, output type, retry policy, and owner module metadata.
- [x] Prove disabled roles that remain future-only still fail before provider
  calls.
- [x] Add tests proving tool-generation provider failures are classified and
  serialized without secrets.

### Task 4: Add Curated Tool Admission

- [x] Add a local curated catalog that maps approved proposal names to known
  Python handlers.
- [x] Add one contacts-domain tool that satisfies a real gap without dynamic
  code execution.
- [x] Require schema, side-effect, and environment compatibility checks before a
  curated tool can enter the active registry.
- [x] Ensure rejected proposals remain inspectable artifacts.

### Task 5: Integrate Pipeline Loop

- [x] Detect eligible tool gaps during candidate validation or execution.
- [x] Request at most one tool proposal per candidate in the foundation runner.
- [x] Admit a curated tool only when the proposal matches a local catalog entry.
- [x] Rerun the candidate through normal policy, execution, verification, and
  quality gates after successful admission.
- [x] Preserve original gap and proposal lineage on accepted reruns and
  rejections.

### Task 6: Reporting, Docs, and Validation

- [x] Extend `quality_report.json` with capability-gap counts, proposal outcome
  counts, and slices by proposed tool and side-effect class.
- [x] Update manifest artifact references for proposal outputs.
- [x] Refresh backend, data, security, and roadmap docs after implementation.
- [x] Run `uv run python scripts/validate_docs.py`.
- [x] Run `uv run python -m unittest`.

## Validation

- `uv run python scripts/validate_docs.py`
- `uv run python -m unittest`
- `uv run python main.py --output-dir /tmp/agent-data-synthesis-foundation-check`

## Acceptance Criteria

- Missing tool and incompatible schema failures are classified as capability
  gaps with structured diagnostics.
- `tool_generation` can only produce validated tool proposals and cannot execute
  generated code.
- A curated local contacts-domain tool can be admitted from a matching proposal
  and used in a rerun through the normal execution and verification path.
- Proposal artifacts and manifest references are written even when admission
  fails.
- Accepted samples and rejections preserve original gap lineage, proposal
  lineage, admitted tool version, and verifier result.
- Quality reports expose capability-gap and proposal outcome metrics without
  breaking existing fields.
- Existing deterministic `uv run python main.py` behavior remains stable when
  tool expansion is disabled.
- `uv run python scripts/validate_docs.py` passes.
- `uv run python -m unittest` passes.

## Risks

- Tool expansion can silently become arbitrary code generation. Keep proposals
  separate from executable tools and require curated local admission.
- Enabling `tool_generation` too broadly could blur security boundaries. The
  role should produce proposal records only, with generated code still out of
  scope.
- Rerunning candidates after tool admission can hide the original failure. Always
  preserve gap diagnostics and proposal lineage.
- Adding new tool and proposal artifacts can create reporting churn. Keep the
  first artifact schema small and versioned.

## Notes

This plan is the smallest useful step toward adaptive tool expansion. It gives
the framework a feedback loop from failures to proposed capabilities while
keeping execution deterministic, local, and auditable.
