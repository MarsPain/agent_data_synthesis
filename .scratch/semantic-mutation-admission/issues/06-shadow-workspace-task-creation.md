# 06 — Shadow-admit Workspace Task Creation

**What to build:** Let a synthesis operator distinguish an authorized workspace
task-creation request from a lookup-only instruction before execution. The
selected project may be observation-bound, but title, priority, and due label
must remain requester-supported and auditable in shadow evidence without
changing current candidate outcomes.

**Blocked by:** [02 — Shadow-admit Workspace Comments End to End](02-shadow-workspace-comments.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Semantic Mutation Admission](../../../docs/product-specs/semantic-mutation-admission.md)

## Acceptance criteria

- [x] Workspace task-creation candidates propose action authorization and complete provenance for title, priority, due label, and project identity.
- [x] Project identity may use an observation only when bound to the instruction-selected project.
- [x] Title and every supplied priority or due label require literal or semantic instruction support with no requester-content defaults in version 1.
- [x] Lookup-only instructions, negated creation, false project bindings, invented content, and parameter smuggling produce bounded shadow findings.
- [x] Explicit literal and semantic task-creation requests produce auditable supported shadow evidence.
- [x] Shadow outcomes leave execution, acceptance, workspace comments, and read-only workspace behavior unchanged.
- [x] Tests include the retained `_30_v5` lookup-only failure pattern as immutable input evidence rather than rewriting historical artifacts.
- [x] Shared-kernel tests continue to prove that domain meaning comes from declarations rather than domain or tool-name branches.

## Scope guard

Do not re-adjudicate historical samples into a release or enable enforce mode in
this ticket.
