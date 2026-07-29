# 01 — Compile Deterministic Coverage Plans

**What to build:** Let a synthesis operator select one versioned coverage
profile and compile it with a domain-owned coverage catalog, run features,
target count, admitted environment capacity, and bounded overrides into a
deterministic coverage plan before any provider call. Establish the shared
coverage vocabulary and strict contracts without yet changing candidate
generation.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Coverage-Driven Representative Synthesis](../../../docs/product-specs/coverage-driven-representative-synthesis.md)

## Acceptance criteria

- [ ] A versioned run profile can opt into a named versioned coverage profile while existing profiles retain their current meaning.
- [ ] Contacts can expose a versioned domain-owned catalog of stable reachable coverage cells without adding contacts-specific branches to the shared compiler.
- [ ] The shared compiler accepts domain catalog, coverage profile, selected features, target count, admitted capacity, and bounded overrides and emits one deterministic plan.
- [ ] The plan distinguishes target accepted-sample distribution from its bounded attempt ceiling.
- [ ] The normal programmatic and command-line surfaces can preview and write the sanitized plan without calling a provider or executing a candidate.
- [ ] Mandatory floors, balancing policy, grounding-reuse limits, feature requirements, and attempt policy are explicit and hash-bound.
- [ ] Unknown versions or dimensions, duplicate cells, contradictory constraints, unavailable features, invalid overrides, insufficient capacity, and statically impossible floors fail locally before any provider call.
- [ ] Fixed inputs produce byte-stable plan content and hashes.
- [ ] Public profile and plan validation tests assert externally visible contracts rather than prompt text or private helper structure.
- [ ] Documentation describes the new profile surface without changing existing default commands.

## Scope guard

Do not call a provider, generate assigned candidates, implement deficit
backfill, add mobile or workspace catalogs, publish run-level coverage evidence,
or change representative admission in this ticket.
