# Plan 0025 Phase D: Adapter Surface Generalization

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status

Deferred. Activate only after
[0025 Phase C](../completed/0025-phase-c-rollout-ready-runtime-api.md) has completed and
runtime sessions can execute action envelopes for contacts and mobile.

## Goal

Generalize the local adapter surface so runtime sessions can be exposed through
manifest and request/result envelopes without making adapter support
contacts-only or connecting external MCP servers.

## Why This Phase

An internal runtime kernel is not fully reusable until it can be consumed
through a stable protocol-like boundary. Phase D forces the runtime interface to
be serializable, capability-declared, and isolated from direct Python imports.

This is a local adapter generalization phase, not external MCP integration.

## Architecture

Current adapter behavior is contacts-first. Phase D changes the direction:

```text
RuntimeDescriptor + RuntimeSession
  -> adapter manifest
  -> runtime action request envelope
  -> runtime action result envelope
  -> episode transition evidence
```

The adapter layer should ask runtime descriptors what operations are supported.
Domain packs provide tool behavior through runtime sessions. Adapter manifests
describe capability; they do not discover arbitrary servers or execute
generated handlers.

## Scope

- Define a runtime adapter manifest that can describe contacts, mobile, and
  future runtimes.
- Reuse or adapt existing MCP-compatible request/result envelopes where they
  match runtime action semantics.
- Replace contacts-only adapter support checks with runtime descriptor
  capability checks.
- Add mobile local adapter support if Phase C session APIs make this a narrow
  wrapper.
- Keep adapter execution in-process and opt-in.

## Out of Scope

- External MCP server discovery.
- Browser automation, remote filesystem access, credential brokering, or
  generated tool handlers.
- Networked adapter protocols.
- Package extraction.
- Dataset release or profile decision changes.

## File Map

- Modify `synthesis/mcp.py`: generalize adapter manifest and envelope handling
  from contacts-specific environment/tool assumptions to runtime descriptors.
- Modify `synthesis/runtime.py`: add adapter capability fields if Phase A did
  not already include enough metadata.
- Modify `synthesis/domain_pipeline.py`: expose runtime-session backed adapter
  construction.
- Extend `tests/test_mcp_adapters.py`: contacts unchanged, mobile local adapter
  support, unsupported runtime capability, redaction.
- Extend `tests/test_runtime_contract.py`: adapter capability validation.
- Update `docs/SECURITY.md`, `docs/BACKEND.md`, `docs/DATA.md`, and
  `docs/ROADMAP.md`.

## Implementation Tasks

### Task 1: Runtime Adapter Manifest Contract

- [ ] Add tests for a runtime-backed adapter manifest with runtime id, protocol
  label, tool schemas, operation list, side-effect classes, reset/checkpoint
  support, and source-policy hash.
- [ ] Implement manifest creation from runtime descriptors and runtime sessions.
- [ ] Validate that manifests omit secrets, host paths, raw source payloads,
  provider prompts, profile paths, and generated code.

### Task 2: Request/Result Envelope Alignment

- [ ] Add tests proving existing MCP-compatible tool-call envelopes can map to
  runtime action request/result records.
- [ ] Reuse existing envelope schema where possible; add narrow compatibility
  adapters only when the runtime action contract requires it.
- [ ] Preserve existing contacts adapter lineage fields.

### Task 3: Remove Contacts-Only Adapter Assumptions

- [ ] Add failing tests showing mobile adapter requests are no longer rejected
  solely because the runtime id is mobile.
- [ ] Replace contacts-specific checks with descriptor capability checks.
- [ ] Keep unsupported adapter capability as a sanitized contract rejection.

### Task 4: Mobile Local Adapter

- [ ] Implement mobile adapter manifest construction from the mobile runtime
  descriptor.
- [ ] Execute `search_phone_messages`, `create_phone_reminder`, and
  `draft_message_reply` through runtime action envelopes.
- [ ] Verify mobile state-changing tools produce action results compatible with
  episode replay and reward labels.

### Task 5: Security Regression

- [ ] Add tests for adapter redaction of local paths, source payloads,
  credentials, headers, provider prompts, and generated code.
- [ ] Confirm adapter execution remains in-process and opt-in.
- [ ] Confirm external MCP server discovery remains absent.

### Task 6: Docs and Validation

- [ ] Document that Phase D is a local adapter surface, not external MCP
  integration.
- [ ] Update 0025 overview with Phase D completion evidence.
- [ ] Run `uv run python scripts/validate_docs.py`.
- [ ] Run `uv run python -m unittest tests.test_mcp_adapters tests.test_runtime_contract tests.test_episode_replay tests.test_reward_labels`.
- [ ] Run `uv run python -m unittest`.

## Acceptance Criteria

- Adapter manifests are runtime-backed rather than contacts-specific.
- Contacts adapter behavior remains stable.
- Mobile local adapter support works when explicitly enabled.
- Unsupported runtime adapter capability is a sanitized contract rejection.
- No external MCP server, generated handler, or network adapter behavior is
  introduced.

## Follow-On

After Phase D, Phase E can evaluate whether the runtime boundary is stable
enough for extraction or should remain internal.
