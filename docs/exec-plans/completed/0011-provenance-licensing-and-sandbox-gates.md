# Plan 0011: Provenance, Licensing, and Sandbox Gates

## Status

Completed on 2026-05-17.

## Goal

Add the governance foundation required before controlled network-backed
environment synthesis can be enabled. The next implementation step should make
source provenance, license eligibility, network access policy, sandbox policy,
and source-event audit artifacts explicit contracts in the local pipeline while
keeping external network ingestion disabled by default.

## Basis

This plan follows
[0010-agentinstruct-seed-transformation-and-editor-loop](0010-agentinstruct-seed-transformation-and-editor-loop.md).
The repository now has deterministic and remote task generation, solution-policy
execution, stateful trajectories, critic/refinement, role contracts,
failure-driven tool expansion, bounded branch execution, and AgentInstruct-style
seed transformation with suggester/editor roles.

The remaining Stage 3 item in [../../ROADMAP.md](../../ROADMAP.md) is
controlled network-backed environment synthesis, but the roadmap explicitly
requires provenance, licensing, and sandbox rules first. This plan implements
those preconditions without adding general web crawling, browser tools,
generated executable environment code, or arbitrary external API use.

Relevant current constraints:

- [../../SECURITY.md](../../SECURITY.md) requires external network access to be
  explicit, logged, and isolated from secrets.
- [../../DATA.md](../../DATA.md) requires source provenance on every sample and
  separate marking for synthetic, transformed, and externally sourced records.
- [../../BACKEND.md](../../BACKEND.md) keeps the first backend local and
  reserves environment generation behind disabled role guardrails.
- [../../DESIGN.md](../../DESIGN.md) requires executable, verifiable,
  versioned trajectories with mandatory lineage.

## Scope

- Add source/provenance contracts that can represent fixture, synthetic,
  transformed, and externally sourced inputs with source identifiers, content
  hashes, retrieval metadata, license labels, and export eligibility.
- Add license policy checks that reject unknown, incompatible, or unreviewed
  external source material before it can affect environments, tasks, samples, or
  training exports.
- Add network and sandbox policy contracts that make external access opt-in,
  allowlisted, bounded by budget, and auditable.
- Add a source-event artifact such as `source_events.jsonl` when source
  auditing is enabled, with sanitized event records and no raw secrets.
- Add deterministic no-network fixtures that exercise the external-source gate
  using local test data.
- Thread accepted source provenance through environment versions, candidate
  lineage, manifests, rejections, and quality-report slices.
- Keep `environment_generation`, `verifier_generation`, and
  `judge_verification` disabled unless a later plan explicitly enables their
  output contracts.

## Out of Scope

- Real web crawling, browser automation, search API integration, or arbitrary
  network-backed data collection.
- Generated executable environment code.
- Enabling the `environment_generation` role.
- MCP environment adapters, distributed workers, dashboards, or durable queues.
- Human review UI for source or license decisions.
- Legal advice or automated license interpretation beyond conservative policy
  labels and explicit allow/deny outcomes.

## Architecture

The governance layer should sit before environment construction and dataset
assembly:

- `synthesis.sources` or a similarly scoped module owns source records, license
  policy decisions, source-event records, and source bundle validation.
- `synthesis.environments` consumes only validated source bundles and records the
  source-policy hash in environment metadata.
- `synthesis.contracts` validates source, license, sandbox, and source-event
  record shapes.
- `synthesis.pipeline` wires source-policy validation before any environment,
  task, solution, verification, or export step can consume external source
  material.
- `synthesis.datasets` persists sanitized source-event artifacts and manifest
  references when source auditing is enabled.
- `synthesis.quality` exposes slices for source kind, license policy outcome,
  external-source eligibility, and source rejection cause.
- `synthesis.roles` keeps future environment and verifier roles disabled and
  covered by regression tests.

## File Map

- Add `synthesis/sources.py` or equivalent focused source-governance module.
- Modify `synthesis/contracts.py` with source, license, sandbox, and source
  event validation.
- Modify `synthesis/environments.py` so environment metadata includes source
  provenance and source-policy hashes.
- Modify `synthesis/pipeline.py` to run source-policy gates before candidate
  execution and export.
- Modify `synthesis/datasets.py` to write source-event artifacts and manifest
  references when enabled.
- Modify `synthesis/quality.py` with source and license slices.
- Extend `tests/test_contracts.py`, `tests/test_foundation_pipeline.py`,
  `tests/test_quality_reporting.py`, and `tests/test_roles.py`.
- Add focused tests for the new source-governance module if introduced.
- Update [../../SECURITY.md](../../SECURITY.md),
  [../../DATA.md](../../DATA.md), [../../BACKEND.md](../../BACKEND.md),
  [../../ROADMAP.md](../../ROADMAP.md), and [../../PLANS.md](../../PLANS.md)
  as implementation details settle.

## Implementation Tasks

### Task 1: Define Source Governance Contracts

- [x] Add source records for fixture, synthetic, transformed, and external
  source kinds.
- [x] Add required provenance fields: source id, source kind, origin reference,
  retrieval timestamp when applicable, content hash, license label, and
  retention/export eligibility.
- [x] Add license policy decisions with allowed, rejected, and review-required
  outcomes plus rejection causes.
- [x] Add contract tests for missing hashes, unknown license labels, external
  sources without policy decisions, and raw-secret leakage.

### Task 2: Add Network and Sandbox Policy Gates

- [x] Add a default-deny network policy with explicit enablement, host
  allowlists, request budgets, and source-event logging requirements.
- [x] Add sandbox policy records for external-source handling, generated-code
  exclusion, filesystem isolation expectations, and secret redaction.
- [x] Reject external source material before environment construction unless
  network, license, and sandbox policy checks all pass.
- [x] Preserve disabled-role regression tests for environment generation,
  verifier generation, and judge verification.

### Task 3: Integrate Source Provenance Into Environments and Lineage

- [x] Attach validated source bundle identifiers and policy hashes to
  environment versions.
- [x] Thread source provenance into accepted samples and rejected-candidate
  details without storing raw external content.
- [x] Keep deterministic fixture behavior stable when external-source auditing
  is disabled.
- [x] Add no-network deterministic fixtures that simulate allowed and rejected
  external-source policy outcomes.

### Task 4: Persist Source Audit Artifacts

- [x] Write sanitized source-event records when source auditing is enabled.
- [x] Add manifest references for source-event artifacts.
- [x] Ensure source events contain event type, source id, policy outcome, host or
  origin alias, hashes, and rejection causes, but no credentials or raw provider
  payloads.
- [x] Add tests for manifest references and sanitized rejection details.

### Task 5: Report Quality and Coverage

- [x] Add quality-report slices for source kind, license policy outcome,
  external-source eligibility, and source rejection cause.
- [x] Include source-governance fields in parent comparison slice deltas.
- [x] Confirm source-gated rejections do not inflate executable-rate or
  trajectory-verification metrics.
- [x] Preserve existing task expansion, branching, refinement, and tool proposal
  metrics.

### Task 6: Docs and Validation

- [x] Update backend, data, and security docs with final source-governance
  contracts and artifact names.
- [x] Update roadmap wording once governance gates are complete.
- [x] Run `uv run python scripts/validate_docs.py`.
- [x] Run `uv run python -m unittest`.
- [x] Run a deterministic foundation command that exercises source-governance
  fixtures without real network access.

## Validation

- `uv run python scripts/validate_docs.py`
- `uv run python -m unittest`
- `uv run python main.py --enable-source-governance-fixture --output-dir /tmp/agent-data-synthesis-source-governance-check`

## Acceptance Criteria

- External source material is rejected by default before environment
  construction.
- Allowed external-source-like fixtures require explicit source, license,
  network, and sandbox policy records.
- Accepted samples and rejections preserve sanitized source provenance and source
  policy outcomes.
- Manifests reference source-event artifacts when source auditing is enabled.
- Quality reports expose source kind, license outcome, external-source
  eligibility, and source rejection slices.
- Future environment and verifier generation roles remain disabled and tested.
- No raw secrets, provider credentials, raw external payloads, or private user
  data are written to manifests, samples, trajectories, quality reports,
  rejections, or source-event artifacts.
- Existing deterministic serial, refinement, branching, and task-expansion runs
  remain stable unless the new source-governance fixture path is explicitly
  enabled.
- Documentation validation and the unit suite pass.

## Risks

- License metadata can create false confidence if labels are inferred too
  aggressively. Keep policy conservative and require explicit allow/reject
  decisions.
- Source audit artifacts can leak sensitive material if they store raw payloads.
  Store hashes, aliases, outcomes, and classified causes instead.
- Network controls can become a bypassable configuration flag. Gate external
  material at the contract and pipeline layers, not only at fetch time.
- Adding governance too broadly can slow local iteration. Keep default fixture
  runs no-network and deterministic.

## Notes

This plan deliberately separates governance gates from real network-backed
environment synthesis. A later plan can enable controlled ingestion once these
contracts, artifacts, and tests exist.
