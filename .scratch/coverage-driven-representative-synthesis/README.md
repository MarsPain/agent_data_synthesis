# Coverage-Driven Representative Synthesis

- **Status:** Campaign validation externally blocked on provider authorization
- **Canonical spec:** [Coverage-Driven Representative Synthesis](../../docs/product-specs/coverage-driven-representative-synthesis.md)
- **Architecture context:** [Domain-Aware Representative Generation](../../docs/design-docs/domain-aware-representative-generation.md)
- **Current phase:** Authorized representative provider pilot

This directory is the feature-level aggregation point for delivery state. The
canonical desired behavior and accepted implementation and testing decisions
remain in the product spec. Current task state, dependency order, and assignment
live only in the tickets under `issues/`.

## Tickets

1. [Compile deterministic coverage plans](issues/01-compile-coverage-plans.md) — completed
2. [Run one contacts assignment end to end](issues/02-contacts-coverage-tracer.md) — completed
3. [Backfill accepted-coverage deficits](issues/03-bounded-coverage-backfill.md) — completed
4. [Add mobile and workspace coverage catalogs](issues/04-three-domain-coverage-catalogs.md) — completed
5. [Publish and gate coverage evidence](issues/05-coverage-evidence-and-gates.md) — completed
6. [Validate representative coverage campaigns](issues/06-representative-coverage-campaign.md) — externally blocked; paid calls require explicit authorization
7. [Expand representative structural catalogs](issues/07-expand-representative-structural-catalogs.md) — completed

Ticket 01 establishes the pure plan-compilation contract. Ticket 02 is the
smallest end-to-end tracer bullet through the existing generation and candidate
pipeline. Ticket 03 adds accepted-sample reconciliation and bounded backfill.
Ticket 04 proves the interfaces across all current domain packs. Ticket 05
makes planned-versus-accepted coverage observable and authoritative for
coverage-driven representative claims. Ticket 06 gathers small-pilot and
three-domain campaign evidence only after the deterministic behavior is
complete.

## Outcome

Ticket 07's deterministic fake-provider follow-up grows fulfilled v3 cells from
twelve at target 12 to thirteen at target 30 in every domain, retains the
grounding-reuse limit of two, and classifies legacy and new samples with one
versioned taxonomy. It does not substitute for the required provider pilot.
Ticket 06 may now request explicit provider, model, credential, and budget
authorization before any paid call. The detailed result is retained in
[the generated preflight report](../../docs/generated/representative-coverage-campaign-validation.md).
