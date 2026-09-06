# 03 — Add the Contacts Domain Adapter

**What to build:** Let a synthesis operator produce verified Contacts Agent
demonstrations and negatives through the new Domain seam, using isolated local
state and real Agent decisions rather than scripted solution policies.

**Blocked by:** [02 — Run provider-neutral multi-turn Agent Episodes](02-run-provider-neutral-agent-episodes.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [ ] The Contacts adapter opens fixture and admitted local-source runs without teaching the synthesis engine the Contacts source schema.
- [ ] Deterministic Task slots cover contact lookup, authorized follow-up recording, and lookup recovery with grounded task-generation context.
- [ ] Model proposals compile into Task cases whose expected answer, expected state, and mutation authorization remain private from the Agent.
- [ ] Each Candidate receives isolated Contacts state; one follow-up cannot affect another Candidate or replay.
- [ ] Read-only lookup, authorized follow-up, ordinary lookup failure and recovery, and rejected unauthorized follow-up all traverse the same Domain Episode interface.
- [ ] Deterministic assessment verifies final-answer grounding, requested state changes, forbidden state changes, and terminal outcome.
- [ ] Contacts semantic keys collapse paraphrases of the same requested outcome, while structural keys distinguish lookup, mutation, and recovery behavior.
- [ ] The shared Domain compliance suite passes without Contacts-specific exceptions in the core test harness.
- [ ] Provider-mock end-to-end tests produce both formal Agent demonstrations and bounded negatives with Contacts-correct lineage.

## Scope guard

Do not migrate Contacts release qualification, compatibility mappings,
acceptance proofs, live canaries, provider-evidence freezing, or historical
artifact readers. Only synthesis behavior crosses the new seam.
