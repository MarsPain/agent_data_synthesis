# Semantic Mutation Admission

- **Status:** Ticketed
- **Canonical spec:** [Semantic Mutation Admission](../../docs/product-specs/semantic-mutation-admission.md)
- **Architecture decision:** [ADR 0001: Independent Semantic Mutation Admission](../../docs/adr/0001-independent-semantic-mutation-admission.md)
- **Current phase:** Implementation

This directory is the feature-level aggregation point for delivery state. The
canonical design remains in the product spec, architectural rationale remains
in the ADR, and implementation state lives in the small tickets under
`issues/`.

## Tickets

1. [Introduce the pre-execution admission seam](issues/01-pre-execution-admission-seam.md) — completed
2. [Shadow-admit workspace comments end to end](issues/02-shadow-workspace-comments.md) — completed
3. [Use an independent model for shadow admission](issues/03-independent-model-shadow-admission.md) — completed
4. [Shadow-admit contact follow-ups](issues/04-shadow-contact-followups.md) — completed
5. [Shadow-admit mobile mutations](issues/05-shadow-mobile-mutations.md) — completed
6. [Shadow-admit workspace task creation](issues/06-shadow-workspace-task-creation.md) — ready for agent
7. [Enforce admission before all declared mutations](issues/07-enforce-declared-mutations.md) — blocked by 03, 04, 05, and 06
8. [Audit admission in release artifacts](issues/08-audit-release-admission-evidence.md) — blocked by 07
9. [Produce and import a reviewed calibration corpus](issues/09-reviewed-calibration-corpus.md) — blocked by 04, 05, and 06
10. [Evaluate the independent judge activation gate](issues/10-evaluate-activation-gate.md) — blocked by 03 and 09
11. [Run the representative activation or no-go gate](issues/11-representative-activation-gate.md) — blocked by 08, 10, and external review/model access

Ticket 01 is an intentional behavior-preserving prefactor. Ticket 02 is the
first narrow tracer bullet. Tickets 03 and 04 complete the independent-provider
path and the contact domain slice. The mobile and workspace-task slices can now
proceed in parallel. Release-audit and calibration paths then proceed
independently and join at Ticket 11.

## Frontier

Ticket 06 is the current implementation frontier. Ticket 09 remains blocked
until that final domain-specific shadow-admission slice is complete.

## Historical Note

The former root-level `ISSUE-0003` was a premature combination of specification,
plan, and implementation ticket. Its requirements were incorporated into the
canonical product spec before removal. An initial seven-ticket breakdown was
also replaced after a stricter tracer-bullet audit found oversized horizontal
slices and redundant dependencies.
