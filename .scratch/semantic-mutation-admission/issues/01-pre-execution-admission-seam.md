# 01 — Introduce the Pre-execution Admission Seam

**What to build:** Make the candidate-processing path ready for Semantic
Mutation Admission without changing current behavior. Introduce one injected,
default-pass admission boundary that every initial or repeated candidate
attempt crosses after its task contract and solution policy exist and before
its first tool executes. This is an intentional behavior-preserving prefactor
that makes the first tracer bullet small enough for a fresh implementation
context.

**Blocked by:** None — can start immediately

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Semantic Mutation Admission](../../../docs/product-specs/semantic-mutation-admission.md)

## Acceptance criteria

- [x] Candidate processing depends on one injected admission interface whose default implementation permits existing execution unchanged.
- [x] The interface receives the validated task contract and proposed solution policy before any tool invocation.
- [x] Initial attempts, refinement reruns, and capability-expansion reruns all cross the same boundary exactly once per attempted execution.
- [x] Existing callers that do not configure admission preserve their current behavior and artifacts.
- [x] Focused tests prove the boundary is reached before execution and receives the expected candidate context.
- [x] The existing candidate-processing, pipeline, and profile tests remain green without fixture rewrites unrelated to dependency injection.

## Scope guard

Do not add run-profile modes, authorization records, domain policy, semantic
judgment, evidence schemas, or blocking behavior in this prefactor.
