# Make the Domain Pack the Semantic Authority and Deep Integration Interface

## Status

Accepted on 2026-08-08.

Each logical domain is represented by a versioned Domain Pack that is both the
sole authority for domain capability semantics and the common deep integration
interface used by the shared framework. A Domain capability has a stable
pack-local semantic identity and an independently versioned proof contract. Task
types, tools, coverage cells, structural families, held-out tags, mutation
policies, runtime features, and report keys remain distinct projections and
cannot act as capability aliases.

The public lifecycle is a pure planning operation, an opening operation that
creates a run-scoped Domain run, run-owned generation/isolation/attempt/replay
behavior, and typed domain assessment. This boundary hides each domain's
environment, registry, verifier, candidate preparation, mutation, and runtime
composition. The shared framework retains source governance, providers,
orchestration, stable artifact writing, qualification, and human authority.

Runtime identity remains independent from Domain Pack identity. Exact pack,
runtime, component, and capability references are content-bound in every
proof-bearing artifact. Legacy names are accepted only through explicit,
versioned, projection-scoped mappings; compatibility cannot manufacture missing
evidence.

## Considered Options

- Keeping the current public domain bundle was rejected because it exposes a
  shallow fan-out of components and makes shared callers coordinate domain
  internals.
- A small `describe` plus `run` interface was rejected because it would absorb
  orchestration, artifact writing, and recovery authority into each pack.
- One generic projection method over dictionaries was rejected because it would
  weaken type-specific invariants and create an undiscoverable semantic bus.
- Exposing a raw runtime session was rejected because it would leak the
  construction seam and let callers bypass run-owned isolation and policy.
- Treating task types, tool names, coverage labels, or runtime descriptors as
  capability identity was rejected because those concepts evolve independently
  and prove different facts.

## Consequences

Domain authors must publish immutable pack descriptors that select exact
capability, task, generation, coverage, evaluation, mutation, runtime, release,
and compatibility contracts. Any observable semantic or evidence change
requires a new pack composition version. Shared consumers depend on the deep
lifecycle and exact references rather than domain-name branches or internal
components.

Existing Contacts, Mobile, and Workspace artifacts require bounded compatibility
adapters and explicit multi-axis assessments. Historical readability and
verification are preserved, but historical labels are not promoted into current
Release evidence. Canonical writers emit only exact logical pack and capability
references.

The full behavior and acceptance boundary are in the
[Outcome-Validated Domain Pack product spec](../product-specs/outcome-validated-domain-pack.md),
and the target mechanics are in the
[deep design](../design-docs/outcome-validated-domain-pack.md).
