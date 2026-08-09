# 02 — Introduce the Deep Domain Pack Lifecycle Through Workspace

**What to build:** Introduce the public plan/open/assess lifecycle and run-owned generation, candidate isolation, attempt, and replay operations. Move the existing Workspace fixture path behind this deep seam while preserving its observable outputs and keeping source admission, providers, orchestration, artifact writing, and qualification in the shared framework.

**Blocked by:** [01 — Establish canonical Domain Pack identity and planning contracts](01-canonical-identity-and-planning-contracts.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Outcome-Validated Domain Pack](../../../docs/product-specs/outcome-validated-domain-pack.md)

## Acceptance criteria

- [x] Shared callers can plan, open, generate, fork, attempt, replay, and assess Workspace behavior without receiving the internal environment/registry/verifier/preparer/mutation component bundle.
- [x] Opening verifies the complete plan, admitted source, logical pack, and exact runtime contract before constructing Workspace state.
- [x] Each candidate attempt runs in isolated candidate-scoped state obtained through the Domain run rather than a caller-visible raw runtime session.
- [x] Initial, refinement, and capability-expansion attempts cross the same task membership, mutation-admission, execution, and verification boundary.
- [x] Replay rejects pack, runtime, source, episode, verifier, or capability-contract drift with bounded reasons.
- [x] Existing Workspace fixture profiles preserve accepted/rejected outcomes, final state, episodes, and sanitized artifacts through the new lifecycle.
- [x] Shared orchestration still owns scheduling, stable merge, cancellation, resumption, and output paths; the Domain Pack performs none of those actions.
- [x] Architecture tests prevent Workspace-specific names and Domain run internals from leaking into unrelated shared consumers.
- [x] Existing Contacts and Mobile behavior remains unchanged pending their explicit compatibility adapter work.

## Scope guard

Do not implement the real coverage-driven Workspace Release Candidate, the
Contacts/Mobile corpus, publishability, downstream training verification, or the
final tracer root. This is a behavior-preserving Workspace lifecycle tracer.
