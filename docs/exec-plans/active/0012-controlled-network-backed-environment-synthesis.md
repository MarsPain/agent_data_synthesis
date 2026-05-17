# Plan 0012: Controlled Network-Backed Environment Synthesis

## Status

Implemented in branch `plan-0012-network-env-synthesis` as of 2026-05-17.
Pending human review before moving to `completed/`.

## Goal

Enable the first opt-in network-backed environment synthesis path while
preserving the source provenance, license, network, sandbox, audit, and export
gates established in plan 0011.

## Basis

This plan follows
[../completed/0011-provenance-licensing-and-sandbox-gates.md](../completed/0011-provenance-licensing-and-sandbox-gates.md).
The local pipeline can already reject external source material by default,
validate source bundles, attach source provenance to environment metadata and
lineage, write sanitized `source_events.jsonl`, and report source-governance
quality slices.

The remaining Stage 3 roadmap item is controlled network-backed environment
synthesis. This plan should make a narrow, auditable ingestion path real without
adding crawling, browser automation, arbitrary API integrations, generated
environment code, or enabled environment-generation roles.

## Scope

- Add an explicit external-source fetch contract that accepts only allowlisted
  HTTPS origins, bounded request budgets, size limits, timeouts, and safe content
  types.
- Add a controlled environment-source adapter that converts one allowed source
  payload into a typed local environment input contract. The first target remains
  the contacts SQLite environment so the blast radius stays small.
- Preserve source provenance and source-policy hashes from fetch through
  environment metadata, accepted samples, rejected candidates, manifests, and
  quality reports.
- Persist sanitized source audit events for fetch attempts, policy decisions,
  and environment-source admission without writing raw external payloads or
  secrets to exported artifacts.
- Add deterministic tests using mocked HTTP clients or local fixtures. Unit and
  docs validation must not require real network access.
- Add a CLI entrypoint that is disabled by default and requires explicit
  opt-in, source URL, license label, allowlisted host, and audit output.

## Out of Scope

- General web crawling, search API use, browser automation, robots-policy
  handling, or multi-hop ingestion.
- Generated Python environment code or executable tool/verifier code.
- Enabling the `environment_generation`, `verifier_generation`, or
  `judge_verification` roles.
- MCP-compatible environment adapters, distributed workers, dashboards, or
  durable queues.
- Human review UI for source or license decisions.
- Automatic legal interpretation of licenses beyond conservative allow/reject
  policy labels.

## Architecture

The network-backed path should stay behind the source-governance boundary:

- `synthesis.sources` owns the fetch request contract, allowlist checks, budget
  accounting, payload hashing, content-type checks, source-event records, and
  source-bundle construction.
- `synthesis.environments` owns typed environment input records and a
  contacts-environment builder that can build SQLite state from validated
  records instead of only hard-coded fixture rows.
- `synthesis.contracts` validates fetched-source records, environment input
  records, and sanitized source-event shapes.
- `synthesis.pipeline` wires opt-in source loading before environment
  construction and preserves the existing default deterministic fixture path.
- `synthesis.datasets` continues to write only sanitized artifacts and manifest
  references. Raw fetched payloads must not be exported.
- `synthesis.quality` keeps source-governance slices and adds any needed
  environment-source admission slices without changing default aggregate
  semantics.

## File Map

- Modify `synthesis/sources.py` with network fetch contracts, request-budget
  enforcement, payload hashing, source-bundle construction, and sanitized fetch
  events.
- Modify `synthesis/environments.py` with a typed contact-record environment
  input contract and a builder path that creates SQLite state from validated
  input records.
- Modify `synthesis/contracts.py` with validators for fetched-source records and
  environment input records.
- Modify `synthesis/pipeline.py` to accept an optional source loader or
  network-backed environment input while preserving the default fixture path.
- Modify `synthesis/datasets.py` only if new source-event artifact references or
  manifest fields are needed.
- Modify `synthesis/quality.py` only if new deterministic source-admission
  slices are introduced.
- Modify `main.py` with explicit opt-in CLI flags for the controlled network
  path.
- Extend `tests/test_source_governance.py`,
  `tests/test_foundation_pipeline.py`, `tests/test_contracts.py`,
  `tests/test_quality_reporting.py`, and `tests/test_cli.py`.
- Update [../../BACKEND.md](../../BACKEND.md),
  [../../DATA.md](../../DATA.md), [../../SECURITY.md](../../SECURITY.md), and
  [../../ROADMAP.md](../../ROADMAP.md) as implementation details settle.

## Implementation Tasks

### Task 1: Define Fetch and Environment Input Contracts

- [x] Add a fetched-source request record with URL, allowlisted host, request
  budget, timeout, maximum bytes, expected content type, license label, and
  source audit requirement.
- [x] Add a fetched-source result record with source id, origin alias, retrieval
  timestamp, content hash, content type, byte count, and sanitized policy
  outcome.
- [x] Add a contacts environment input record with contact rows, optional
  follow-up rows, source bundle id, source policy hash, and validation errors.
- [x] Add contract tests for missing hashes, unsafe schemes, non-allowlisted
  hosts, over-budget fetches, oversize payloads, unsupported content types, and
  malformed contact records.

### Task 2: Add Controlled Source Fetching

- [x] Implement an HTTP client boundary that can be injected in tests and uses
  default timeouts and byte limits.
- [x] Enforce HTTPS-only URLs, exact host allowlists, redirect rejection or
  explicit redirect accounting, and request-budget decrementing before payload
  admission.
- [x] Convert successful payloads into source records and license policy
  decisions before environment construction.
- [x] Convert rejected fetches into source-policy rejections with sanitized
  details and source events.

### Task 3: Build Environments From Validated Source Inputs

- [x] Add a contacts-environment builder that accepts validated contact records
  rather than hard-coded fixture rows.
- [x] Preserve the existing deterministic fixture builder and default CLI
  behavior.
- [x] Attach source provenance and source-policy hash metadata to network-backed
  environment versions.
- [x] Add tests proving accepted samples and rejections carry the correct source
  lineage without raw payload content.

### Task 4: Persist Audit and Reporting Artifacts

- [x] Write sanitized source events for fetch attempt, fetch accepted, fetch
  rejected, environment-source admitted, and environment-source rejected cases.
- [x] Keep manifest references to `source_events.jsonl` when source auditing is
  enabled.
- [x] Add or preserve quality slices for source kind, license policy outcome,
  external-source eligibility, source rejection cause, and environment-source
  admission outcome.
- [x] Confirm fetch-stage and environment-source rejections do not inflate
  executable-rate or trajectory-verification metrics.

### Task 5: Add CLI and No-Network Tests

- [x] Add explicit CLI flags for controlled network-backed synthesis, including
  source URL, source license label, allowed host, and output directory.
- [x] Keep normal `uv run python main.py` no-network and deterministic.
- [x] Add mocked-client tests for successful source ingestion and each rejection
  class.
- [x] Add CLI tests for missing opt-in flags, missing allowlist, and successful
  mocked configuration where possible without real network access.

### Task 6: Docs and Validation

- [x] Update backend, data, and security docs with final network-backed
  environment synthesis contracts and artifact names.
- [x] Update roadmap wording once the controlled path exists.
- [x] Run `uv run python scripts/validate_docs.py`.
- [x] Run `uv run python -m unittest`.
- [x] Run a deterministic mocked or fixture-backed command that exercises the
  new path without real external network access.

## Validation

- `uv run python scripts/validate_docs.py`
- `uv run python -m unittest`
- Deterministic no-network fixture command for the new controlled path, to be
  finalized during implementation.

## Acceptance Criteria

- The default foundation pipeline still performs no external network access.
- Network-backed environment synthesis requires explicit opt-in and an
  allowlisted HTTPS source.
- Source payloads are bounded by request budget, timeout, size limit, content
  type, license policy, and sandbox policy before environment construction.
- Accepted network-backed samples preserve source provenance and source-policy
  hashes in environment metadata and lineage.
- Rejected fetches and rejected environment-source inputs produce sanitized
  source-policy rejections and source events.
- Raw external payloads, credentials, authorization headers, provider payloads,
  private user data, and raw source text are not written to manifests, samples,
  trajectories, rejections, quality reports, or source-event artifacts.
- Environment, verifier, and judge generation roles remain disabled and covered
  by regression tests.
- Documentation validation and the unit suite pass.

## Risks

- A network flag can become a policy bypass if validation exists only near the
  fetch step. Keep admission checks in both source governance and environment
  construction.
- Source payloads can leak into artifacts through diagnostics. Store hashes,
  aliases, counts, outcomes, and causes only.
- Fixture tests can give false confidence if they skip the HTTP boundary. Use an
  injected mocked HTTP client that exercises the same code path as real fetches.
- The first environment-source adapter can overgeneralize too early. Keep plan
  0012 focused on contacts data and defer generalized environment synthesis
  until this path is audited.

## Notes

This plan enables a narrow controlled ingestion path. It should not expand the
project into a crawler, browser agent, external API broker, or generated-code
environment factory.
