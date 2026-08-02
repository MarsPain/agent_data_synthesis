# Coverage-Driven Representative Synthesis

- **Status:** Completed; contacts v4 follow-up deferred
- **Canonical spec:** [Coverage-Driven Representative Synthesis](../../docs/product-specs/coverage-driven-representative-synthesis.md)
- **Architecture context:** [Domain-Aware Representative Generation](../../docs/design-docs/domain-aware-representative-generation.md)
- **Current phase:** No further contacts demo expansion planned

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
6. [Validate representative coverage campaigns](issues/06-representative-coverage-campaign.md) — completed
7. [Expand representative structural catalogs](issues/07-expand-representative-structural-catalogs.md) — completed
8. [Add taxonomy-distinct contacts v4 structures](issues/08-contacts-v4-taxonomy-distinct-structures.md) — blocked by operator product-scope decision

Ticket 01 establishes the pure plan-compilation contract. Ticket 02 is the
smallest end-to-end tracer bullet through the existing generation and candidate
pipeline. Ticket 03 adds accepted-sample reconciliation and bounded backfill.
Ticket 04 proves the interfaces across all current domain packs. Ticket 05
makes planned-versus-accepted coverage observable and authoritative for
coverage-driven representative claims. Ticket 06 gathers small-pilot and
three-domain campaign evidence only after the deterministic behavior is
complete. Ticket 08 records the evidence-driven option to add contacts
state-action structure that remains distinct under the common taxonomy. The
synthesis operator has accepted contacts as a demonstration domain and deferred
that expansion rather than adding product scope solely to grow the metric.

## Outcome

Ticket 07's deterministic fake-provider follow-up grows fulfilled v3 cells from
twelve at target 12 to thirteen at target 30 in every domain, retains the
grounding-reuse limit of two, and classifies legacy and new samples with one
versioned taxonomy. It does not substitute for the required provider pilot.
Ticket 06 used the deterministic gate to request explicit provider, model,
credential, and budget authorization. The authorized serial provider pilot
accepted 12 of 12 candidates in every domain, improved common-taxonomy family
coverage over the prior baseline, and stayed within its 72-call authorization.
Its gate decision was `ready-for-authorized-campaign`. The separately
authorized thirty-per-domain campaign then completed at 30 accepted samples
and 13 fulfilled cells per domain, but contacts did not add a new common
structural family between pilot and campaign. Its final decision is therefore
`revise-catalog`; a success conclusion is rejected until contacts adds
taxonomy-distinct executable structure, potentially with expanded environment
capacity. The artifacts remain diagnostic and no dataset was promoted. The
detailed result is retained in the
[generated validation report](../../docs/generated/representative-coverage-campaign-validation.md).

## Current Disposition

The contacts demo has completed its architectural purpose: the framework
detected structural saturation, rejected an unsupported success conclusion,
and avoided release promotion. Ticket 08 remains a deferred design option, not
an implementation frontier. No new contacts provider campaign is planned.
