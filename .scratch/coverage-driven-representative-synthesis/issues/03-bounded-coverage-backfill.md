# 03 — Backfill Accepted-Coverage Deficits

**What to build:** Reconcile planned coverage against accepted samples and
bounded in-flight work after each processing wave, then use remaining attempt
capacity to backfill the highest-priority unresolved deficit. Rejections must
remain visible and must never satisfy coverage or trigger unbounded provider
spend.

**Blocked by:** [02 — Run One Contacts Assignment End to End](02-contacts-coverage-tracer.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Coverage-Driven Representative Synthesis](../../../docs/product-specs/coverage-driven-representative-synthesis.md)

## Acceptance criteria

- [x] The scheduler tracks planned, in-flight, accepted, rejected, and remaining counts separately for every assigned cell.
- [x] Only an accepted sample with locally validated assignment membership fulfills one planned unit.
- [x] Provider-schema, assignment, mutation-admission, execution, verification, exact-duplicate, and refinement rejections leave the corresponding accepted-sample deficit unfilled.
- [x] Mandatory deficits are selected before discretionary deficits, followed by largest normalized deficit and stable tie-breaking.
- [x] In-flight assignments prevent overscheduling the same cell but never count as fulfilled.
- [x] Remaining attempt capacity is used only for bounded deficit backfill and stops exactly at the plan ceiling.
- [x] Exhaustion produces deterministic incomplete status and bounded cell-level reasons without silently relaxing floors or concentration rules.
- [x] Feature-dependent assignments are scheduled only when both the run profile and catalog allow the feature.
- [x] Repeated deterministic runs produce identical assignments, accepted order, rejections, and reconciliation results.
- [x] High-seam tests demonstrate recovery from at least one rejected assignment without exceeding the declared attempt budget.

## Scope guard

Do not add distributed queues, concurrent workers, automatic semantic-duplicate
admission, new tools, or silent provider-budget expansion.
