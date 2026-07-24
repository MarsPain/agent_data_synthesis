# 02 — Shadow-admit Workspace Comments End to End

**What to build:** Let a synthesis operator run a workspace-comment candidate
through a complete offline shadow admission path and inspect whether the
instruction supports the comment mutation, without changing execution or
acceptance. Use a deterministic local judge fixture to establish the versioned
authorization, provenance, verdict, and retained-evidence contracts before a
remote provider is introduced.

**Blocked by:** [01 — Introduce the Pre-execution Admission Seam](01-pre-execution-admission-seam.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Semantic Mutation Admission](../../../docs/product-specs/semantic-mutation-admission.md)

## Acceptance criteria

- [x] A versioned profile can select disabled or shadow admission while older profiles retain disabled behavior and their existing meaning.
- [x] A workspace comment candidate proposes versioned action authorization and provenance for its comment body and instruction-selected task.
- [x] Domain-owned policy requires instruction support for the comment body and permits an observation-backed task identifier only when it is bound to the selected task.
- [x] Deterministic validation reports bounded failures for missing authorization, invalid instruction evidence, missing comment provenance, invalid origins, and false task bindings.
- [x] The local judge fixture produces each strict semantic verdict with bounded reason codes and evidence references.
- [x] Shadow validation and verdict outcomes never change tool execution, candidate acceptance, or unrelated rejection causes.
- [x] Accepted and otherwise-rejected workspace-comment candidates retain sanitized shadow evidence with contract versions and hashes.
- [x] Read-only workspace candidates bypass semantic judgment.
- [x] Candidate-processing and run-level tests demonstrate the complete disabled and shadow behavior without asserting private helper structure.

## Scope guard

Do not add remote model calls, enforce-mode blocking, other mutation actions,
aggregate calibration metrics, or release-pack validation.
