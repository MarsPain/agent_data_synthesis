# Plan 0013: MCP-Compatible Environment and Tool Adapters

## Status

Planned on 2026-05-18.
Implemented on 2026-05-18; pending review.

## Goal

Add the first MCP-compatible adapter contract for local environments and tools
without connecting arbitrary external MCP servers, enabling browser automation,
or weakening the source-governance and sandbox gates established in plans 0011
and 0012.

The plan should make the current contacts environment and curated tool registry
describable through a stable adapter manifest and executable through a local
in-process shim. This gives later distributed workers, remote adapters, and
tool-server integrations a contract to target while keeping early execution
deterministic and no-network by default.

## Basis

This plan follows the controlled source-governance and network-ingestion work in
[0012-controlled-network-backed-environment-synthesis](0012-controlled-network-backed-environment-synthesis.md).
The repository now has local executable environments, typed tools, role-backed
generation, refinement, tool proposal admission, branching, task expansion,
source provenance, and controlled HTTPS contacts ingestion.

Stage 4 in [../../ROADMAP.md](../../ROADMAP.md) starts with interoperability
before scale. The next narrow step is an adapter boundary that can represent
environment state, tool schemas, call envelopes, observations, side effects,
and lineage in a protocol-shaped form without adopting external runtime
complexity too early.

Relevant current constraints:

- [../../DESIGN.md](../../DESIGN.md) keeps executable environments, tools,
  tasks, trajectories, verification, and lineage as the core sample contract.
- [../../BACKEND.md](../../BACKEND.md) keeps orchestration local until
  throughput needs justify actors or queues.
- [../../DATA.md](../../DATA.md) requires versioned tools, environment
  provenance, side-effect metadata, trajectory events, and quality slices.
- [../../SECURITY.md](../../SECURITY.md) requires external access to remain
  explicit, logged, bounded, and isolated from secrets.

## Scope

- Define a local MCP-compatible adapter manifest for one environment-tool bundle.
- Represent environment identity, environment version, reset/checkpoint support,
  source provenance, tool schemas, side-effect class, and verifier implications.
- Add request and response envelope contracts for tool calls routed through the
  adapter boundary.
- Implement a contacts-domain local shim that exposes existing curated tools
  through the new contract without starting an external MCP server.
- Preserve existing trajectory event shapes while recording adapter lineage for
  calls executed through the shim.
- Add validation and quality visibility for adapter manifest version, adapter
  execution outcome, and adapter rejection cause.
- Keep default `uv run python main.py` behavior stable unless the adapter path is
  explicitly enabled.

## Out of Scope

- Connecting to arbitrary external MCP servers.
- Browser tools, web automation, remote filesystem access, or external API
  tool calls.
- Generated executable environment code, generated verifier code, or generated
  tool handlers.
- Durable queues, distributed workers, dashboards, or multi-process actor
  routing.
- OAuth, user approval UI, persistent credentials, or secret brokering.
- General conversion of every local module into an MCP server.

## Architecture

The adapter layer should sit between the local environment/tool registry and the
trajectory runner:

- `synthesis.mcp` or another focused module owns adapter manifests, call
  envelopes, result envelopes, adapter errors, and local shim routing.
- `synthesis.tools` continues to own curated tool definitions, schemas,
  side-effect metadata, and compatibility checks.
- `synthesis.environments` continues to own state construction,
  reset/checkpoint behavior, and source-provenance metadata.
- `synthesis.execution` can route a candidate through either direct local tool
  calls or the local adapter shim while preserving the same trajectory semantics.
- `synthesis.contracts` validates adapter manifests, call envelopes, result
  envelopes, and adapter-lineage records.
- `synthesis.datasets` writes adapter lineage on accepted samples and adapter
  rejection details on failed candidates.
- `synthesis.quality` reports adapter outcomes and rejection causes without
  changing aggregate executable-rate semantics.
- `synthesis.sources` and `synthesis.roles` remain guardrails: the adapter path
  must not bypass source policy, sandbox policy, or disabled future roles.

## File Map

- Add `synthesis/mcp.py` or equivalent focused adapter-boundary module.
- Modify `synthesis/contracts.py` with adapter manifest, call envelope, result
  envelope, and adapter-lineage validation.
- Modify `synthesis/tools.py` only where existing tool metadata must be exported
  into the adapter manifest.
- Modify `synthesis/environments.py` only where environment metadata and
  reset/checkpoint capabilities must be surfaced to the adapter manifest.
- Modify `synthesis/execution.py` to route explicitly enabled candidates through
  the local adapter shim.
- Modify `synthesis/pipeline.py` and `main.py` with an opt-in adapter fixture
  flag that keeps default runs unchanged.
- Modify `synthesis/datasets.py` and `synthesis/quality.py` if adapter lineage
  and slices require new artifact fields.
- Extend `tests/test_contracts.py`, `tests/test_tools.py`,
  `tests/test_foundation_pipeline.py`, `tests/test_quality_reporting.py`, and
  `tests/test_cli.py`.
- Add focused `tests/test_mcp_adapters.py` if the adapter module is introduced.
- Update [../../BACKEND.md](../../BACKEND.md), [../../DATA.md](../../DATA.md),
  [../../SECURITY.md](../../SECURITY.md), and [../../ROADMAP.md](../../ROADMAP.md)
  as implementation details settle.

## Implementation Tasks

### Task 1: Define Adapter Contracts

- [x] Add an adapter manifest record with adapter id, protocol label, schema
  version, environment id/version, source-policy hash, supported operations,
  tool schemas, side-effect classes, and verifier implications.
- [x] Add tool-call request and result envelopes with call id, adapter id,
  tool name, validated arguments, observation payload, side-effect summary,
  execution status, and classified error details.
- [x] Add adapter lineage records that can be attached to accepted samples and
  rejected candidates.
- [x] Add contract tests for malformed manifests, unknown tools, invalid
  arguments, missing source provenance, and unsupported operations.

### Task 2: Add the Local Contacts Adapter Shim

- [x] Build a local in-process shim that maps the current contacts environment
  and curated contacts tools into the adapter contract.
- [x] Keep the shim deterministic and no-network; it must not spawn servers,
  read credentials, or use external MCP clients.
- [x] Preserve environment reset/checkpoint behavior before and after shimmed
  tool calls.
- [x] Add tests proving direct local execution and shimmed execution produce
  equivalent accepted samples for the fixture path.

### Task 3: Route Explicit Adapter Execution

- [x] Add an opt-in pipeline option and CLI flag for the adapter fixture path.
- [x] Route selected candidates through the adapter shim while preserving the
  existing trajectory event contract.
- [x] Store adapter lineage on accepted samples and adapter rejection details on
  failed candidates.
- [x] Confirm the default foundation, refinement, branching, task-expansion, and
  source-governance runs remain stable.

### Task 4: Report Adapter Quality and Rejections

- [x] Add quality-report slices for adapter id, protocol label, adapter execution
  outcome, and adapter rejection cause.
- [x] Ensure adapter-contract rejections do not inflate executable-rate or
  verifier success metrics.
- [x] Preserve existing source-governance, role, branch, refinement, task
  expansion, and tool-proposal metrics.
- [x] Add parent-comparison visibility if adapter slices affect report deltas.

### Task 5: Docs and Validation

- [x] Update backend, data, and security docs with final adapter contracts,
  opt-in behavior, and non-goals.
- [x] Update roadmap wording once the local adapter fixture exists.
- [x] Run `uv run python scripts/validate_docs.py`.
- [x] Run `uv run python -m unittest`.
- [x] Run a deterministic adapter-fixture command without real network access.

## Validation

- `uv run python scripts/validate_docs.py`
- `uv run python -m unittest`
- Deterministic no-network adapter fixture command, to be finalized during
  implementation.

## Acceptance Criteria

- Default local synthesis still uses direct curated local tools and performs no
  adapter execution unless explicitly enabled.
- The adapter manifest records environment identity, source provenance,
  supported tools, side effects, verifier implications, and schema version.
- Shimmed contacts-tool execution preserves the same task, trajectory,
  verification, and quality semantics as direct local execution.
- Accepted samples record adapter lineage only when the adapter path is used.
- Adapter-contract failures are rejected with classified causes and sanitized
  details.
- The adapter path does not connect to arbitrary external MCP servers, open
  network connections, read credentials, or execute generated code.
- Source governance, sandbox policy, and disabled future-role guardrails remain
  enforced.
- Documentation validation and the unit suite pass.

## Risks

- A broad "MCP support" claim can hide major runtime complexity. Keep this plan
  limited to a local compatibility contract and in-process shim.
- Adapter envelopes can duplicate tool and trajectory contracts. Reuse existing
  tool schemas and trajectory event shapes where possible.
- Protocol-shaped abstractions can become a bypass around source governance or
  sandbox controls. Require source provenance and side-effect metadata in the
  manifest and validate before execution.
- Adding an adapter path can create two subtly different execution semantics.
  Use equivalence tests against direct local execution.

## Notes

This plan creates the interoperability boundary needed before external MCP
servers or distributed workers are considered. It is intentionally not a server
implementation plan.
