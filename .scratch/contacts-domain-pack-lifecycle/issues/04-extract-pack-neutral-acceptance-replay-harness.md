# 04 — Extract a Pack-Neutral Acceptance and Replay Harness

**What to build:** Make the existing acceptance-and-replay path reusable by a
second Domain Pack through the smallest shared contract that Contacts and
Workspace demonstrably need, while keeping domain semantics inside their Pack
adapters and preserving the established Workspace result.

**Blocked by:** [03 — Establish Contacts Release Evidence and Qualification](03-establish-contacts-release-evidence-and-qualification.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Contacts Domain Pack Lifecycle and Second-Domain Validation](../../../docs/product-specs/contacts-domain-pack-lifecycle.md)

## Acceptance criteria

- [x] A Pack-neutral acceptance contract can drive the common sequence from an exact planned run through sanitized provider evidence, release verification, qualification, and provider-free replay without taking a domain name or raw runtime session as a shared input.
- [x] Workspace's injected live-shaped acceptance and reconstructed replay proof preserve their existing effective qualification, conformance separation, sanitization guarantees, and bounded negative outcomes through the extracted contract.
- [x] The contract delegates domain-specific plan selection, runtime opening, capability floors, assessment, and tracer semantics to the relevant Domain Pack adapter rather than creating a shared Contacts or Workspace conditional.
- [x] The shared harness exposes only the minimum stable inputs needed by both domains, rejects incomplete or mismatched domain bindings before provider evidence is frozen, and retains no credentials, prompts, responses, or unrestricted source material.
- [x] Regression tests demonstrate that the refactor has not changed default offline behavior, existing Workspace authorization failures, or the provider-free replay boundary.

## Implementation

Added the pack-neutral `AcceptanceReplayHarness` and typed adapter contract in
`synthesis/acceptance_replay.py`. The shared boundary now owns preparation
binding checks, sanitized provider evidence, bounded usage capture, release
pack and Release Candidate prerequisites, zero-provider replay coordination,
and proof handoff. Workspace supplies its exact plan, capability floor,
mutation preflight, release qualification, tracer replay, and proof verifier
through a private adapter; its existing schemas, IDs, failure reasons, and
offline behavior remain compatible. Focused contract tests and Workspace
acceptance/tracer regressions pass.

## Scope guard

Do not yet assemble the Contacts proof, add a Contacts live command, alter
Workspace semantic requirements, or broaden the shared interface for an
unproven third domain. This is the deliberate prefactor that makes the next
Contacts vertical proof possible without cloning Workspace behavior.
