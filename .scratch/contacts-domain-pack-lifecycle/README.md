# Contacts Domain Pack Lifecycle and Second-Domain Validation

- **Status:** Ticketed
- **Label:** `ready-for-agent`
- **Canonical spec:** [Contacts Domain Pack Lifecycle and Second-Domain Validation](../../docs/product-specs/contacts-domain-pack-lifecycle.md)
- **Governing decisions:** [ADR 0002](../../docs/adr/0002-domain-pack-semantic-authority-and-deep-interface.md), [ADR 0003](../../docs/adr/0003-separate-evidence-verification-from-external-authority.md)
- **Current phase:** Implementation — first lifecycle tracer bullet ready

This tracker entry publishes the canonical specification for operationalizing
Contacts as the second end-to-end Domain Pack.  The feature begins from the
existing `contacts` descriptor and legacy compatibility corpus, but produces
new current evidence through the deep lifecycle rather than promoting legacy
artifacts.

## Tickets

1. [Open Contacts through the deep Domain Pack lifecycle](issues/01-open-contacts-deep-domain-pack-lifecycle.md) — ready-for-agent
2. [Bind Contacts capabilities to coverage and assessment evidence](issues/02-bind-contacts-capabilities-to-evidence.md) — ready-for-agent
3. [Establish Contacts release evidence and qualification](issues/03-establish-contacts-release-evidence-and-qualification.md) — ready-for-agent
4. [Extract a Pack-neutral acceptance and replay harness](issues/04-extract-pack-neutral-acceptance-replay-harness.md) — ready-for-agent
5. [Assemble the provider-free Contacts acceptance proof](issues/05-assemble-provider-free-contacts-acceptance-proof.md) — ready-for-agent
6. [Add explicitly authorized Contacts live acceptance](issues/06-add-authorized-contacts-live-acceptance.md) — ready-for-agent
7. [Run Contacts live acceptance and freeze replay proof](issues/07-run-contacts-live-acceptance-and-freeze-replay.md) — ready-for-agent

## Frontier

[Open Contacts through the deep Domain Pack lifecycle](issues/01-open-contacts-deep-domain-pack-lifecycle.md)
is the current implementation frontier. The later real-provider operation
requires fresh explicit authorization and is not implied by ticket readiness.

## Delivery boundary

The intended observable result is a provider-free Contacts acceptance proof
that can reconstruct a current, exact Contacts Release Candidate chain from
frozen evidence.  A real-provider Contacts campaign is separately and
explicitly authorized; it is never implied by this `ready-for-agent` status.

Each ticket links the canonical specification and owns its own scope,
dependencies, assignment, and acceptance state. The feature index does not
duplicate the product specification.
