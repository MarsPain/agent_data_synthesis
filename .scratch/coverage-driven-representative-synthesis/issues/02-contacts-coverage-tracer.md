# 02 — Run One Contacts Assignment End to End

**What to build:** Use a compiled plan to issue locally owned coverage
assignments and run assigned contacts candidates through the existing remote
generation, candidate processing, semantic mutation admission, execution,
verification, exact duplicate, and dataset assembly path. This is the first
end-to-end tracer bullet for smart scheduling.

**Blocked by:** [01 — Compile Deterministic Coverage Plans](01-compile-coverage-plans.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Coverage-Driven Representative Synthesis](../../../docs/product-specs/coverage-driven-representative-synthesis.md)

## Acceptance criteria

- [x] The scheduler deterministically selects a mandatory or largest-deficit contacts cell and issues one stable assignment within the compiled plan.
- [x] The provider receives only the selected assignment contract and the minimum domain-approved grounding context.
- [x] Provider output cannot set plan, assignment, cell, fulfillment, lineage, or coverage-score fields.
- [x] Local validation proves that the returned task contract belongs to the assigned cell before candidate processing begins.
- [x] A contract that is valid for another cell but violates its assignment is rejected rather than silently reclassified.
- [x] A conforming assigned candidate crosses the existing semantic mutation, execution, verification, and exact duplicate gates without a parallel execution path.
- [x] Accepted samples and relevant rejections retain sanitized assignment identifiers, versions, and hashes without raw prompts, provider responses, credentials, or unrestricted grounding rows.
- [x] Deterministic fake-provider tests exercise the complete run-profile-to-artifact seam for at least one read-only and one state-changing contacts cell.
- [x] Runs without a coverage profile preserve their existing artifacts and behavior.

## Scope guard

Do not implement multi-wave backfill, mobile or workspace catalogs, semantic
duplicate detection, new mutation authorization semantics, or representative
coverage admission in this ticket.
