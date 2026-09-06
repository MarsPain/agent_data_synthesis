# 01 — Prove the Agent-First Core Seam With a Test Domain

**What to build:** Let a synthesis operator run one complete, isolated
Agent-first synthesis trace through the new library interface with deterministic
model and Domain adapters, producing inspectable demonstration, negative,
quality, and manifest artifacts without importing the legacy implementation.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [ ] Two focused superseding ADRs record the accepted Agent-first Domain seam and the replacement of independent pre-execution semantic judgment with deterministic authorization plus calibrated quality review.
- [ ] The new package imports and runs without importing the legacy synthesis or runtime packages.
- [ ] A synthesis engine accepts a validated run configuration, registered Domain adapter, and deterministic model adapters through the approved public interface.
- [ ] A test Domain supplies deterministic Task slots, compiles a public/private Task case, opens candidate-local state, executes a valid tool call, and returns a deterministic assessment.
- [ ] One successful Episode is written to demonstrations and one deterministically rejected Episode is written to negatives through the new Episode schema.
- [ ] The exported demonstration excludes private oracle values, credentials, unrestricted provider material, local absolute source paths, and hidden reasoning.
- [ ] The run manifest binds the normalized run configuration and final artifact files without nested evidence graphs or object-level hash chains.
- [ ] Persistence contracts are owned by their modules and validated at the persistence seam; no new central contracts module is introduced.
- [ ] Architecture tests reject core imports of legacy packages, production Domain implementations, or the release lab.
- [ ] The core-focused test command completes within the five-second development target.

## Scope guard

Do not add a production provider adapter, migrate a production Domain, implement
bounded concurrency or resume, add semantic judge enforcement, or change the
current public entrypoint. This ticket proves the replacement seam in isolation.
