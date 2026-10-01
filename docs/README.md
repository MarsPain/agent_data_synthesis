# Documentation Index

Canonical current behavior is described by the Core Docs below. Domain terms
live in [CONTEXT.md](../CONTEXT.md); current work and exception decisions live
only in the [local issue tracker](../.scratch/README.md).

## Core Docs

- [Design](DESIGN.md): current Agent-first engine contracts.
- [Backend](BACKEND.md): process, ledger, and adapter boundaries.
- [Data](DATA.md): public collections, manifest, review, and lineage.
- [Security](SECURITY.md): local source, provider, mutation, and approval boundaries.
- [Operations](OPERATIONS.md): run, resume, replay, and review import.
- [Product sense](PRODUCT_SENSE.md) and [roadmap](ROADMAP.md).
- [Issue-tracker configuration](agents/issue-tracker.md) in `agents/`.

## Deep Design

The `design-docs/` area contains the
[framework source analysis](design-docs/agent-data-synthesis-framework.md),
[Agent-first architecture explainers](design-docs/architecture-explainers.md),
and historical designs from the removed legacy path. Historical source links
are descriptive; the code is available through repository history.

## Product Specs

The [Agent-first core rebuild spec](product-specs/agent-first-core-rebuild.md)
records the original acceptance contract and cutover design. The operator's
explicit exception and unchanged formal decision are recorded in the local
tracker. Other files under `product-specs/` document historical features.

## Architecture Decisions

The `adr/` [index](adr/README.md) records system-wide decisions, including the
Agent-first Domain seam and bounded public-intent compilation.

## References

The `references/` area includes the
[PDF source analysis](references/agent-data-synthesis-pdf-analysis.md).
The `generated/` area contains generated documentation and historical reports.

## Historical Execution Records

The `exec-plans/` archive and [PLANS.md](PLANS.md) are historical records.
They are not a current task tracker or active runtime specification.
