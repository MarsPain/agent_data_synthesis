# Plan 0015: Generated Code Sandboxing and Executable Admission Controls

## Status

Planned on 2026-05-27. **Completed on 2026-05-27**. Promoted and resolved
`TD-0001` from [../tech-debt/README.md](../tech-debt/README.md) before external
MCP servers, user-provided tools, or generated environment/verifier roles are
enabled.

## Goal

Add the first generated-code sandbox and executable admission boundary: typed
generated executable records, static safety scanning, explicit admission
decisions, sanitized audit artifacts, and a restricted local execution helper
that can be tested without enabling arbitrary generated tools, environments, or
verifiers by default.

This plan should close the high-impact safety gap recorded in technical debt
while preserving the current default behavior: generated executable code remains
disabled unless a caller explicitly uses the new sandbox admission boundary.

## Basis

This plan follows the guardrails established in:

- [0008-failure-driven-tool-expansion-and-capability-gap-routing.md](0008-failure-driven-tool-expansion-and-capability-gap-routing.md),
  which enabled `tool_generation` only for structured tool proposals and kept
  executable code out of scope.
- [0011-provenance-licensing-and-sandbox-gates.md](0011-provenance-licensing-and-sandbox-gates.md),
  which introduced sandbox policy records but did not implement generated-code
  execution isolation.
- [0013-mcp-compatible-environment-tool-adapters.md](0013-mcp-compatible-environment-tool-adapters.md),
  which added a local adapter contract while explicitly avoiding arbitrary
  external MCP servers and generated handlers.

Relevant current constraints:

- [../../SECURITY.md](../../SECURITY.md) requires generated executable code to be
  treated as untrusted, scanned for forbidden imports and side effects, and
  executed with restricted process controls before acceptance.
- [../../DATA.md](../../DATA.md) requires generated role lineage, source
  provenance, manifest references, and sanitized rejection diagnostics.
- [../../BACKEND.md](../../BACKEND.md) keeps execution deterministic and local
  until throughput or integration needs justify broader runtime complexity.
- [../../ROADMAP.md](../../ROADMAP.md) places external MCP integration and scale
  after local adapter boundaries; generated-code sandboxing is a prerequisite
  for those future surfaces.

## Scope

- Add first-class generated executable artifact records for Python code emitted
  by future environment, verifier, or tool-generation roles.
- Add a static scanner for Python source that rejects forbidden imports,
  subprocess usage, filesystem access outside an artifact directory, network
  modules, environment-variable access, dynamic evaluation, package
  installation hooks, and obvious raw-secret material.
- Add executable admission records that bind a generated artifact, sandbox
  policy hash, static scan result, source role lineage, and final
  `accepted`/`rejected` decision.
- Add a restricted local execution helper for admitted Python snippets using a
  temporary artifact directory, sanitized environment, timeout, and best-effort
  process limits available in the Python standard library.
- Add new rejection cause `unsafe_generated_code` for artifacts that fail scan
  or admission.
- Serialize sanitized sandbox audit artifacts for rejected generated code
  without writing raw code, secrets, environment variables, headers, or provider
  prompts.
- Keep `environment_generation`, `verifier_generation`, and arbitrary
  executable `tool_generation` disabled by default.
- Add tests that prove unsafe generated code is rejected before execution and
  fixture-safe admitted code runs only inside the restricted helper.

## Out of Scope

- Enabling `environment_generation` or `verifier_generation` as production roles.
- Accepting arbitrary user-provided packages, shell commands, migrations, or
  external MCP server handlers.
- Container orchestration, VM isolation, Docker, Firecracker, seccomp profiles,
  or OS-specific sandbox frameworks.
- Browser automation, remote filesystems, credential brokering, OAuth, or
  persistent secret stores.
- Semantic duplicate detection (`TD-0002`).
- Async orchestration and durable queues (deferred plan 0014).

## Architecture

Add a focused `synthesis.sandbox` boundary below role generation and above any
future executable admission path:

- `synthesis.sandbox` owns generated executable records, static scan results,
  admission decisions, redacted audit records, and the restricted local
  execution helper.
- `synthesis.contracts` validates sandbox artifact, scan, admission, and
  execution-result record shapes and adds `unsafe_generated_code` to the
  rejection cause allowlist.
- `synthesis.roles` keeps future executable roles disabled but exposes clear
  metadata for which roles would require sandbox admission before execution.
- `synthesis.tools` continues to admit only curated local implementations. Tool
  proposals remain proposal-only and must not contain executable fields.
- `synthesis.datasets` records sandbox audit artifact paths when generated code
  is rejected or admitted through the fixture path.
- `synthesis.quality` reports sandbox scan/admission outcome counts without
  treating rejected generated code as verifier failures.
- `main.py` may expose a fixture-only opt-in flag for deterministic sandbox
  validation; default `uv run python main.py` remains unchanged.

The local helper is an engineering guardrail, not a full hardened container. It
should make unsafe generated code non-executable in this repository and preserve
an upgrade path to stronger isolation later.

## File Map

- Add `synthesis/sandbox.py` for generated executable records, scanner,
  admission logic, audit redaction, and restricted local execution.
- Modify `synthesis/contracts.py` with validators for generated executable,
  scan result, admission result, sandbox execution result, and
  `unsafe_generated_code`.
- Modify `synthesis/roles.py` only if role metadata needs an explicit
  `requires_sandbox_admission` marker for future executable roles.
- Modify `synthesis/tools.py` to keep proposal parsing rejection tests aligned
  with sandbox executable-field rules; do not admit generated handlers.
- Modify `synthesis/datasets.py` if sandbox audit paths need manifest entries
  for the fixture path.
- Modify `synthesis/quality.py` if sandbox admission slices are added to
  `quality_report.json`.
- Modify `main.py` only for a deterministic fixture flag such as
  `--enable-sandbox-fixture`.
- Add `tests/test_sandbox.py` for scanner, admission, execution helper, and
  audit redaction coverage.
- Extend `tests/test_contracts.py`, `tests/test_roles.py`,
  `tests/test_tools.py`, `tests/test_foundation_pipeline.py`,
  `tests/test_quality_reporting.py`, and `tests/test_cli.py` only where the
  sandbox fixture touches existing contracts or reports.
- Update [../../SECURITY.md](../../SECURITY.md), [../../DATA.md](../../DATA.md),
  [../../BACKEND.md](../../BACKEND.md), and [../../ROADMAP.md](../../ROADMAP.md)
  when implementation details settle.

## Implementation Tasks

### Task 1: Define Generated Executable and Sandbox Contracts

- [x] Add `GeneratedExecutableArtifact` with artifact id, artifact kind
  (`tool_handler`, `environment_builder`, `verifier`), language (`python`),
  source hash, declared entrypoint, source role, role lineage, created
  timestamp, and sandbox policy hash.
- [x] Add `GeneratedCodeScanResult` with status, violation list, forbidden
  symbol list, source hash, scanner version, and redaction summary.
- [x] Add `SandboxAdmissionResult` with artifact id, scan status, policy id,
  accepted flag, rejection cause, sanitized reason, and audit artifact path.
- [x] Add `SandboxExecutionResult` with artifact id, status, timeout flag,
  exit class, stdout/stderr hashes, duration, and sanitized error class.
- [x] Add contract validators and tests for malformed artifact ids, unsupported
  languages, missing policy hashes, raw-secret leakage, and invalid admission
  states.
- [x] Add `unsafe_generated_code` to the rejection cause allowlist and prove
  existing rejection validation still accepts all current causes.

### Task 2: Implement Static Python Safety Scanner

- [x] Parse Python source with `ast` and reject syntax errors as
  `unsafe_generated_code`.
- [x] Reject forbidden imports and access patterns including `os`, `sys`,
  `subprocess`, `socket`, `urllib`, `http`, `ftplib`, `pathlib`, `shutil`,
  `importlib`, `builtins.__import__`, `eval`, `exec`, `open`, `compile`,
  `globals`, `locals`, and `os.environ`.
- [x] Reject shell/package-install patterns such as `pip`, `uv`, `npm`,
  `curl`, and `wget` when they appear in call targets, string command fields,
  or obvious subprocess arguments.
- [x] Reject absolute filesystem paths, parent-directory traversal, home
  directory references, SSH/cloud credential path fragments, API-key-like
  strings, and authorization-header-like strings.
- [x] Return sanitized violation records with categories and line numbers but no
  raw source excerpts.
- [x] Add tests for safe pure functions, syntax errors, forbidden imports,
  dynamic evaluation, network access, filesystem escape attempts, and raw-secret
  patterns.

### Task 3: Add Admission and Redacted Audit Artifacts

- [x] Add an admission function that requires a valid sandbox policy with
  `generated_code_allowed=True`, artifact-subdirectory filesystem isolation,
  and secret redaction enabled.
- [x] Reject artifacts when the static scanner reports any violation.
- [x] Write sandbox audit artifacts that include hashes, violation categories,
  policy metadata, role lineage, and admission outcome, but never raw code,
  provider prompts, headers, environment variables, or API keys.
- [x] Add manifest references for sandbox audit artifacts only when the fixture
  path is explicitly enabled.
- [x] Add tests proving rejected artifacts preserve sanitized diagnostics and
  accepted fixture artifacts record audit references.

### Task 4: Add Restricted Local Execution Helper

- [x] Run admitted Python snippets in a subprocess with a temporary artifact
  working directory, sanitized environment, deterministic stdin, timeout, and
  best-effort CPU/memory limits where the host Python supports `resource`.
- [x] Require the declared entrypoint to return JSON-serializable data through a
  narrow wrapper rather than arbitrary file output.
- [x] Capture stdout/stderr only as hashes and byte counts in exported records.
- [x] Treat timeout, non-zero exit, non-JSON output, and wrapper errors as
  sandbox execution failures with sanitized error classes.
- [x] Add tests for successful fixture execution, timeout termination, non-JSON
  output, attempted environment access, and attempted filesystem escape.

### Task 5: Preserve Role and Tool Guardrails

- [x] Keep `environment_generation` and `verifier_generation` disabled in the
  default role registry.
- [x] Keep `tool_generation` proposal-only: proposals containing code,
  handlers, packages, shell commands, or migrations continue to fail schema
  parsing before admission.
- [x] Add role metadata or tests showing executable roles cannot call a provider
  or execute code unless a future plan explicitly enables them and routes output
  through sandbox admission.
- [x] Add tests proving disabled roles still fail before provider calls and
  tool proposals with executable fields still reject without writing raw code.

### Task 6: Add Fixture Pipeline Visibility

- [x] Add a deterministic sandbox fixture path that exercises scan, admission,
  restricted execution, audit serialization, manifest references, and quality
  slices without accepting arbitrary generated code from an LLM.
- [x] Add quality report slices for sandbox scan status, admission outcome,
  artifact kind, and sandbox execution status.
- [x] Ensure default foundation, branching, task-expansion,
  source-governance, network-source, and MCP-adapter runs remain unchanged
  unless the sandbox fixture flag is enabled.
- [x] Add CLI tests for fixture flag behavior and no-op default behavior.

### Task 7: Docs and Validation

- [x] Update security docs with the implemented sandbox boundary, scanner
  categories, audit redaction rules, and limits of the local helper.
- [x] Update data docs with generated executable, scan, admission, execution,
  audit, manifest, and quality-report fields.
- [x] Update backend docs with the new `synthesis.sandbox` boundary and default
  disabled behavior.
- [x] Update roadmap wording to show generated-code sandboxing as the active
  safety prerequisite before external MCP servers or generated executable roles.
- [x] Move `TD-0001` to resolved status in
  [../tech-debt/README.md](../tech-debt/README.md) when implementation lands.
- [x] Run `uv run python scripts/validate_docs.py`.
- [x] Run `uv run python -m unittest`.
- [x] Run deterministic fixture commands for default pipeline and sandbox
  fixture output.

## Validation

- `uv run python scripts/validate_docs.py`
- `uv run python -m unittest`
- `uv run python main.py`
- `uv run python main.py --enable-sandbox-fixture --output-dir artifacts/foundation-sandbox`

## Acceptance Criteria

- Default local synthesis remains unchanged and does not execute generated code.
- Generated executable artifacts have versioned, validated, lineage-preserving
  records before scan or admission.
- Static scanning rejects unsafe Python before execution and emits sanitized
  violation records.
- Admission requires an explicit sandbox policy, successful scan result,
  artifact-subdirectory isolation, and secret redaction.
- Restricted local execution is available only after admission and records
  sanitized execution results.
- Raw code, prompts, API keys, headers, environment variables, and host paths do
  not appear in sandbox audit artifacts, manifests, quality reports, accepted
  samples, or rejection diagnostics.
- `environment_generation` and `verifier_generation` remain disabled, and
  `tool_generation` remains proposal-only.
- Sandbox fixture quality slices and manifest references are present only when
  the fixture path is explicitly enabled.
- Documentation validation and the unit suite pass.

## Risks

- A Python subprocess with static scanning is not a hardened security boundary.
  Keep the plan explicit: this is the first local admission guardrail and should
  be replaceable by a stronger container or OS sandbox later.
- Static scanning can miss obfuscated behavior. Default behavior must remain
  generated-code disabled, and admission should be conservative.
- Over-broad scanner rules may reject useful safe code. Prefer clear rejection
  categories and fixture tests over silent acceptance.
- Audit artifacts can accidentally leak sensitive source material. Store hashes,
  categories, counts, aliases, and sanitized error classes only.

## Notes

This plan resolves the safety prerequisite that currently blocks external MCP
servers, user-provided tools, and executable generated environment/verifier
roles. Semantic duplicate detection remains `TD-0002`, and async orchestration
remains deferred as plan 0014.
