# 04 — Add the Mobile Messages Domain Adapter

**What to build:** Let a synthesis operator produce verified Mobile Messages
Agent demonstrations and negatives through the new Domain seam, including
read-only, state-changing, and recovery trajectories in isolated local state.

**Blocked by:** [02 — Run provider-neutral multi-turn Agent Episodes](02-run-provider-neutral-agent-episodes.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [ ] The Mobile Messages adapter opens fixture and admitted local-source runs without shared-core knowledge of message, reminder, or draft schemas.
- [ ] Deterministic Task slots cover message search, reminder creation, draft reply, and search recovery with grounded generation context.
- [ ] Expected messages, reminder state, draft state, and mutation authorization remain private from the Agent.
- [ ] Each Candidate receives isolated Mobile Messages state; reminders and drafts cannot leak across Candidates or replay.
- [ ] Read-only search, authorized reminder and draft mutations, recoverable search failure, and rejected unauthorized mutation traverse the common Domain Episode interface.
- [ ] Deterministic assessment checks observation grounding, final response, requested final state, and absence of unintended state change.
- [ ] Semantic and structural keys distinguish requested meaning and executed tool/state/recovery topology without relying on instruction wording.
- [ ] The shared Domain compliance suite passes without Mobile-specific branches in the synthesis engine or quality module.
- [ ] Provider-mock end-to-end tests emit correctly separated demonstrations and negatives with Mobile Messages lineage.

## Scope guard

Do not retain Mobile compatibility corpora, release evidence, legacy run-profile
support, or Domain Pack projection mappings. This ticket ports only behavior
needed to synthesize and verify Episodes.
