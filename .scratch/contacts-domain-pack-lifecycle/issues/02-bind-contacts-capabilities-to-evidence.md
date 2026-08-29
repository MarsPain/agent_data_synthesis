# 02 — Bind Contacts Capabilities to Coverage and Assessment Evidence

**What to build:** Let a Contacts Domain run carry exact canonical capability
references through assigned generation, isolated attempts, verification,
coverage, held-out evaluation, and typed Domain assessment, so Contacts can
produce current domain evidence without inferring semantics from legacy labels.

**Blocked by:** [01 — Open Contacts Through the Deep Domain Pack Lifecycle](01-open-contacts-deep-domain-pack-lifecycle.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Contacts Domain Pack Lifecycle and Second-Domain Validation](../../../docs/product-specs/contacts-domain-pack-lifecycle.md)

## Acceptance criteria

- [x] The Contacts plan selects exact references for contact lookup, follow-up recording, contact lookup recovery, and missing-contact safe failure, with task types, tools, coverage cells, and held-out tags remaining separate projections.
- [x] Coverage assignments bind their required Contacts capabilities before provider work; provider output cannot add, remove, rename, or self-attest capability membership.
- [x] Accepted Contacts samples retain exact plan, Pack, runtime, assignment, capability, mutation, episode, verifier, and final-state bindings, while rejected or unverified work earns no coverage credit.
- [x] Recovery evidence requires the declared failed lookup, an admissible fallback, a grounded result, and independent verification; a recovery label or branch shape alone is insufficient.
- [x] Held-out evaluation independently establishes the missing-contact safe-failure behavior and proves that it caused no unintended mutation.
- [x] A typed Contacts Domain assessment accepts only exact plan-bound evaluation and release evidence, distinguishes insufficiency from success with bounded reasons, and never grants a release qualification itself.
- [x] Canonical current artifacts emit Contacts Pack and capability references without legacy semantic aliases; the frozen Contacts compatibility corpus remains byte-stable and historical-only.
- [x] Focused evidence-flow and end-to-end tests cover valid evidence plus cross-Pack, capability-version, assignment, recovery, held-out, and assessment-drift rejections.

## Implementation

Contacts coverage now runs through the opened Domain Pack lifecycle. Coverage
assignments and provider prompts carry locally derived capability bindings;
accepted samples and rejection evidence retain the exact Contacts plan, Pack,
runtime, assignment, mutation hash, episode, verifier, and final-state
bindings. Held-out Contacts tasks use canonical capability references and
verify recovery and missing-contact safety independently. Recovery admission
requires executed branch outcomes, grounded fallback evidence, and passing
verification, while replay rejects tampered evidence bindings. A Contacts-owned
typed Domain assessment now requires exact plan identity, separately declared
evaluation/release evidence, and the complete canonical capability set while
remaining qualification-free. The legacy Contacts compatibility corpus is
unchanged.

Focused Contacts, coverage, evaluation, orchestration, three-domain, and
Domain Pack contract tests pass, as do Python compile checks and documentation
validation.

## Scope guard

Do not create or qualify a Contacts release pack, change semantic-mutation
activation policy, or add a real-provider acceptance path. This ticket makes
current Contacts domain evidence complete and auditable, not release-qualified.
