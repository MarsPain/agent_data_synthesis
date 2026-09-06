# Use a Provisional Agent-First Domain Adapter Seam

## Status

Accepted on 2026-09-06. Supersedes
[ADR 0002: Make the Domain Pack the Semantic Authority and Deep Integration Interface](0002-domain-pack-semantic-authority-and-deep-interface.md).

## Decision

The replacement synthesis path is an isolated library package. Its single
Domain seam is a registered adapter that opens a run. The run issues
deterministic task slots, freezes its initial state, compiles a proposal into a
public task plus an opaque private task case, opens an isolated Episode, and
assesses that Episode.

The shared engine assigns stable candidate and Episode identities, invokes the
registered proposal model, persists the frozen input and private task cases,
places terminal records in demonstrations or negatives, and writes sanitized
public artifacts plus a flat manifest. It does not parse Domain-private bytes,
interpret a Domain's task semantics, or export a general-purpose domain-data
mapping.

An Episode exports action arguments only from the tool's declared input schema
and observations or state changes only from its declared output schema.
Undeclared payload fields remain private, which prevents a Domain from using an
event mapping as a generic provider or oracle-data channel.

Domains own their fixture semantics, tools, compilation rules, mutation
authorization, isolated state, deterministic assessment, semantic keys, and
structural classification. The public Episode models are bounded persistence
models; each persistence module validates the records it owns. The core has no
central contracts module and imports neither legacy synthesis/runtime packages
nor production Domain implementations.

This seam remains provisional until Contacts and a second production Domain
exercise it, including the planned change-locality test. A test-only adapter
proves the first trace without establishing that production Domain semantics or
extensibility are solved.

## Consequences

The legacy entrypoint remains unchanged until the accepted cutover. The new
core starts with deterministic test adapters and a private SQLite ledger; it
does not introduce a production provider, a production Domain, concurrency,
resume, a release lab, or a compatibility layer.

Adding a production Domain must use the adapter seam rather than add
Domain-name branches to the core. If the first two production adapters expose a
missing semantic operation, the interface is revised before it is treated as
stable.
