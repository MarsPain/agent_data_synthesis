# 04 — Shadow-admit Contact Follow-ups

**What to build:** Let a synthesis operator shadow-evaluate contact follow-up
mutations from generated authorization through retained evidence. The contact
name must remain bound to the instruction-selected contact, and the follow-up
note must be requester-supported rather than model-invented, while ordinary
execution behavior remains unchanged.

**Blocked by:** [02 — Shadow-admit Workspace Comments End to End](02-shadow-workspace-comments.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Semantic Mutation Admission](../../../docs/product-specs/semantic-mutation-admission.md)

## Acceptance criteria

- [x] Contact follow-up candidates propose action authorization and provenance for the selected contact name and follow-up note.
- [x] Domain policy permits an observed normalized contact identity only when bound to the instruction-selected contact.
- [x] The follow-up note requires literal or semantic instruction support and has no default or model-inferred escape hatch.
- [x] False contact bindings, unsupported notes, missing provenance, and unsupported origins produce bounded shadow findings.
- [x] Valid literal and semantic follow-up requests produce auditable supported shadow evidence.
- [x] Shadow outcomes do not change tool execution, acceptance, or read-only contact behavior.
- [x] Tests cover deterministic validation, all semantic verdicts, retained evidence, and absence of domain-specific branches in the shared kernel.

## Scope guard

Implement only contact follow-up mutation policy and generation. Reuse the
shared contracts rather than expanding mobile or workspace behavior.
