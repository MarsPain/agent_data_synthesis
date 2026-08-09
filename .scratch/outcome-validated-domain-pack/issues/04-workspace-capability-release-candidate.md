# 04 — Carry Canonical Workspace Capabilities to Release Candidate Evidence

**What to build:** Carry the five canonical Workspace capability references unchanged from the Domain plan through coverage assignments, provider membership checks, task contracts, isolated attempts, episodes, verification, coverage evidence, held-out evaluation, Domain assessment, release completeness, manifests, and release packs for a coverage-driven LLM release-candidate profile.

**Blocked by:** None (Ticket 02 completed)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Outcome-Validated Domain Pack](../../../docs/product-specs/outcome-validated-domain-pack.md)

## Acceptance criteria

- [x] The exact Workspace plan declares item search, task creation, comment addition, item-search recovery, and missing-item safe failure before any provider call.
- [x] Canonical generated task types declare explicit capability requirements; recovery is an assignment/branch structure and missing-item safety remains a held-out scenario.
- [x] Each assignment fixes exact capability references locally and provider output cannot add, remove, rename, or self-attest them.
- [x] Membership validation rejects task, tool, state, grounding, expected-state, recovery, assignment, or capability mismatches before execution and gives them no coverage credit.
- [x] Accepted samples retain plan, pack, runtime, assignment, capability, mutation, episode, verifier, and final-state bindings through the release pack.
- [x] Recovery credit requires a verified initial failure, admissible transition, fallback execution, and intended grounded result rather than branch-plan presence.
- [x] Held-out evaluation consumes the same capability catalog and independently proves all five capabilities, including missing-item safe failure with no unintended mutation.
- [x] Release completeness preserves at least five accepted samples, rejection rate no greater than 0.2, existing required tool combinations, required task/capability floors, and at least one accepted recovery.
- [x] Canonical writers emit no legacy Workspace capability or task aliases; compatibility mappings remain ingestion-only.
- [x] Existing source, mutation, grounding, verification, quality, provenance, and artifact-integrity gates remain mandatory.

## Scope guard

Do not grant Release Candidate solely from the profile purpose or a fulfilled
coverage plan, implement human publication authority, or weaken any existing
machine release floor to make the tracer pass.
