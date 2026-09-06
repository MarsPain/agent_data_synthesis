# 10 — Cut Over and Remove the Legacy Core

**What to build:** Let operators and library consumers use only the accepted
Agent-first core, while removing the legacy runtime, compatibility, proof, and
qualification implementation so future development has one synthesis path and
one test surface.

**Blocked by:** [09 — Run three-domain Agent acceptance](09-run-three-domain-agent-acceptance.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [ ] The formal Python package and thin run, resume, replay, and review CLI commands delegate exclusively to the accepted replacement interface.
- [ ] Legacy synthesis and runtime packages, old-format readers, compatibility fixtures, Domain Pack lifecycle, qualification, publishability, training-recommendation, acceptance-proof, tracer, and related scripts and tests are removed from the active implementation.
- [ ] No compatibility adapter or redirecting Python import lets the replacement read old run profiles or artifacts; old material remains recoverable only through repository history or regeneration.
- [ ] The empty independently packaged release-lab skeleton has a concise purpose statement and may depend on public finalized artifacts in the future; the core cannot import it.
- [ ] Runtime dependencies contain only the approved HTTP client, persistence-model library, and Python standard library requirements; test tooling remains development-only.
- [ ] Canonical onboarding, architecture, design, data, operations, security, glossary, and agent maps describe the new core without retaining stale implementation claims.
- [ ] Existing completed execution plans remain historical and reachable but do not become an active task-state or architecture source.
- [ ] The Local Markdown workflow uses the feature tracker as the sole implementation-state source and does not create a new execution-plan lifecycle.
- [ ] Documentation validation rejects broken links, competing sources of truth, stale active indexes, and release-lab dependency inversion.
- [ ] Core, three Domain, ordinary integration, replay, calibration, CLI, architecture, documentation, and accepted scale checks all pass through the new test commands within their approved time budgets.
- [ ] A clean environment can install the project, run one deterministic smoke synthesis, inspect both dataset collections and manifest, and resume an interrupted run without any legacy package present.

## Scope guard

This is the final contract step of the wide refactor. Do not start it from
partial deterministic evidence, a shadow-only semantic judge, an unsuccessful
campaign, or an unapproved exception to the canonical acceptance criteria.
