# 01 — Establish Canonical Domain Pack Identity and Planning Contracts

**What to build:** Add strict, versioned contracts for logical Domain Pack references, Domain capability references, immutable pack descriptors, pure Domain plans, typed Domain assessments, projection-scoped compatibility mappings, and cumulative qualification subjects. Register the initial logical Contacts, Mobile Messages, and Workspace Tasks descriptors while preserving existing default execution behavior.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Outcome-Validated Domain Pack](../../../docs/product-specs/outcome-validated-domain-pack.md)

## Acceptance criteria

- [ ] Exact Domain Pack references bind logical id, immutable composition version, and canonical content hash; reused versions with changed bytes fail closed.
- [ ] Exact capability references bind logical pack id, stable pack-local key, and capability contract version without aliasing task, tool, coverage, held-out, mutation, or runtime labels.
- [ ] Initial descriptors declare the canonical capability catalogs for Contacts, Mobile Messages, and Workspace Tasks and select exact component and runtime contracts.
- [ ] Pure planning produces byte-stable canonical output and a stable plan id for identical admitted inputs without provider calls, runtime creation, or file mutation.
- [ ] Planning rejects unknown, duplicate, cross-pack, ambiguous, unsupported-version, and internally inconsistent references with bounded reason codes.
- [ ] Compatibility mappings are keyed by source schema/version and projection kind and cannot apply one global string alias across semantic and runtime fields.
- [ ] Domain assessment and qualification-subject contracts can represent exact evidence or insufficiency without granting a qualification implicitly.
- [ ] Existing run profiles and default local execution preserve their observable behavior while the new contracts are not yet selected by consumers.
- [ ] Focused contract tests cover canonical hashing, version reuse, unsafe or oversized records, secret-like fields, and deterministic bounded failures.

## Scope guard

Do not migrate the public runtime lifecycle, change existing release decisions,
write the compatibility corpus, or implement Publishable/Training Recommended
logic in this ticket. This ticket establishes contracts and immutable semantic
descriptors only.
