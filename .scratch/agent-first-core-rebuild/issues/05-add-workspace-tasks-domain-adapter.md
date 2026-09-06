# 05 — Add the Workspace Tasks Domain Adapter

**What to build:** Let a synthesis operator produce verified Workspace Tasks
Agent demonstrations and negatives through the new Domain seam, including
search, task creation, comment mutation, safe failure, and recovery behavior.

**Blocked by:** [02 — Run provider-neutral multi-turn Agent Episodes](02-run-provider-neutral-agent-episodes.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [ ] The Workspace Tasks adapter opens fixture and admitted local-source runs without shared-core knowledge of workspace item, task, document, or comment schemas.
- [ ] Deterministic Task slots cover item search, task creation, comment addition, search recovery, and missing-item safe failure.
- [ ] Expected workspace item, task state, comment state, and mutation authorization remain private from the Agent.
- [ ] Each Candidate receives isolated Workspace state; created tasks and comments cannot affect another Candidate or replay.
- [ ] Search, authorized task and comment mutation, recoverable selector failure, missing-item safe failure, and rejected unauthorized mutation use the common Domain Episode interface.
- [ ] Deterministic assessment verifies grounded final responses, exact requested mutations, safe failure, and absence of unintended state changes.
- [ ] Semantic and structural keys distinguish request meaning and executed search, mutation, and recovery topology without treating coverage labels as diversity.
- [ ] The shared Domain compliance suite passes without Workspace-specific branches in the synthesis engine or quality module.
- [ ] Provider-mock end-to-end tests emit correctly separated demonstrations and negatives with Workspace Tasks lineage.

## Scope guard

Do not migrate Workspace qualification, publishability, Training Recommended,
tracer proofs, live acceptance, authority fixtures, or compatibility readers.
Only Agent synthesis and deterministic assessment are in scope.
