# 10 — Cut Over and Remove the Legacy Core

**What to build:** Replace the public entrypoint with the accepted Agent-first
core and remove the legacy implementation, leaving one synthesis path with
honest shadow-review behavior even if optional enforcement is unfinished.

**Blocked by:** [09 — Run independent three-domain dataset acceptance](09-run-three-domain-agent-acceptance.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [ ] Engineering and independent dataset acceptance from Ticket 09 pass. Judge enforcement is a separately reported optional capability, not an additional cutover gate.
- [ ] The formal Python package and thin run, resume, replay, and review-label-import commands delegate exclusively to the accepted replacement interface.
- [ ] Legacy synthesis/runtime, old-format readers, compatibility fixtures, Domain Pack lifecycle, qualification, authority, training recommendation, proof/tracer implementations, and related active scripts/tests are removed.
- [ ] No compatibility adapter or redirecting import reads old profiles/artifacts. Historical recovery uses repository history or regeneration.
- [ ] No release-lab skeleton is introduced. Any future release consumer must justify a separate package, with no dependency from synthesis back to that consumer.
- [ ] Runtime dependencies are limited to the approved HTTP client, persistence-model library, and standard library; test tooling is development-only.
- [ ] Onboarding, architecture, design, data, operations, security, glossary, and agent maps describe the new core, frozen-input recovery, persistent budgets, and distinct deterministic/human/judge approval.
- [ ] Shadow is the delivered default. An unfinished or unqualified enforcement path stays tracked in Ticket 08; it cannot cause unreviewed demonstrations to be labeled semantically approved.
- [ ] Completed execution plans remain reachable history; current work stays in the existing Local Markdown feature tracker, without a new execution-plan lifecycle.
- [ ] Documentation/architecture validation rejects broken links, stale active claims, competing sources of truth, legacy imports, and release-lab dependency inversion.
- [ ] Core, three-Domain, model, integration, replay, review-import, CLI, architecture, documentation, and scale checks pass within approved budgets; enforcement checks apply when that optional implementation is delivered.
- [ ] A clean environment installs and runs deterministic smoke synthesis, exports both collections and manifest, imports blind-review labels, and resumes interrupted work without legacy packages present.

## Scope guard

This is the final contract step after engineering and dataset acceptance.
Do not start from failed or incomplete evidence, or relax those requirements.
A shadow-only or unqualified judge is permitted by the canonical spec and does
not require an exception. Do not port legacy governance merely to keep its
tests alive.
