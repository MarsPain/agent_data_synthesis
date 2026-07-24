# 03 — Use an Independent Model for Shadow Admission

**What to build:** Let a synthesis operator configure the specialized semantic
mutation judge independently from task generation and obtain hardened shadow
verdicts for workspace comments. Remote failure, malformed output, correlated
same-model judgment, and untrusted instruction content must remain visible and
safe without changing candidate execution in shadow mode.

**Blocked by:** [02 — Shadow-admit Workspace Comments End to End](02-shadow-workspace-comments.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Semantic Mutation Admission](../../../docs/product-specs/semantic-mutation-admission.md)

## Acceptance criteria

- [x] The enabled `mutation_admission_judge` role remains distinct from general post-execution verification.
- [x] Production and deterministic local judge adapters implement the same injected interface.
- [x] Judge configuration has an explicit model identity independent from the task-generator model and retains no credentials.
- [x] Judge input contains only the normalized instruction, proposed mutation, validated provenance, and minimal referenced evidence, all untrusted text being explicitly delimited.
- [x] Strict parsing accepts only the versioned three-value verdict, bounded findings, reason codes, evidence references, hashes, and lineage.
- [x] Provider calls use the specified timeout and at most one retry; invalid output, timeout, unavailability, and exhaustion produce bounded outcomes.
- [x] Same-model shadow runs are marked diagnostic-only, while different-model lineage is independently auditable.
- [x] Raw prompts, responses, chain-of-thought, credentials, transport headers, host paths, and unrelated observations are absent from retained artifacts.
- [x] Shadow tests cover semantic support, negation, ambiguity, missing content, false provenance, parameter smuggling, and prompt injection without altering execution.

## Scope guard

Do not enable fail-closed execution or claim release readiness in this ticket.
