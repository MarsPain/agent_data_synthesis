# 05 — Shadow-admit Mobile Mutations

**What to build:** Let a synthesis operator shadow-evaluate both mobile
mutation behaviors end to end: creating a reminder from an instruction-selected
message and drafting a reply for an instruction-selected thread. Requester text
and optional scheduling content must be supported, while message and thread
identifiers remain observation-bound and execution remains unchanged.

**Blocked by:** [02 — Shadow-admit Workspace Comments End to End](02-shadow-workspace-comments.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Semantic Mutation Admission](../../../docs/product-specs/semantic-mutation-admission.md)

## Acceptance criteria

- [x] Reminder and draft-reply candidates each propose action authorization and complete requester-controlled argument provenance.
- [x] Reminder title and supplied due time require instruction support, with no version-1 due-time default.
- [x] Reply body requires instruction support and cannot be empty, defaulted, or model-inferred.
- [x] Source message and thread identifiers may use observations only when bound to the instruction-selected message or thread.
- [x] Missing bodies, unsupported scheduling values, false bindings, and parameter smuggling produce bounded shadow findings.
- [x] Valid literal and semantic reminder and reply instructions produce auditable supported shadow evidence.
- [x] Shadow outcomes leave mobile execution, acceptance, and read-only search behavior unchanged.
- [x] Tests cover both mutation actions, all provenance forms allowed by their policies, all semantic verdicts, and retained evidence through public behavior seams.

## Scope guard

Do not introduce mobile-specific conditionals into the shared admission kernel
or enable enforce mode.
