# Agent-First Core Rebuild

- **Status:** Ticketed
- **Label:** `ready-for-agent`
- **Canonical spec:** [Agent-First Core Rebuild](../../docs/product-specs/agent-first-core-rebuild.md)
- **Current phase:** Ticket 01 is the implementation frontier

This feature replaces the proof-heavy legacy implementation with an isolated,
Agent-first synthesis core after deterministic, three-domain, human-review, and
single-machine scale acceptance. The canonical spec owns desired behavior,
accepted design decisions, migration, and cutover criteria. This tracker owns
only delivery state, dependencies, assignment, and ticket discussion.

## Test Seams

- The synthesis engine is the principal end-to-end seam.
- Domain adapters share one parameterized compliance seam.
- Production and fake model adapters share one provider-neutral JSON seam.

## Tickets

1. [Prove the Agent-first core seam with a test Domain](issues/01-prove-agent-first-core-seam.md) — ready-for-agent
2. [Run provider-neutral multi-turn Agent Episodes](issues/02-run-provider-neutral-agent-episodes.md) — blocked by 01
3. [Add the Contacts Domain adapter](issues/03-add-contacts-domain-adapter.md) — blocked by 02
4. [Add the Mobile Messages Domain adapter](issues/04-add-mobile-messages-domain-adapter.md) — blocked by 02
5. [Add the Workspace Tasks Domain adapter](issues/05-add-workspace-tasks-domain-adapter.md) — blocked by 02
6. [Resume and scale local synthesis runs](issues/06-resume-and-scale-local-runs.md) — blocked by 02
7. [Add shadow quality review](issues/07-add-shadow-quality-review.md) — blocked by 02
8. [Gate semantic enforcement on human calibration](issues/08-gate-semantic-enforcement-on-calibration.md) — blocked by 03, 04, 05, and 07
9. [Run three-domain Agent acceptance](issues/09-run-three-domain-agent-acceptance.md) — blocked by 06 and 08
10. [Cut over and remove the legacy core](issues/10-cut-over-and-remove-legacy-core.md) — blocked by 09

## Dependency Shape

```text
01 -> 02 -> 03 --+
          -> 04 --+
          -> 05 --+-> 08 --+
          -> 07 -------^    +-> 09 -> 10
          -> 06 --------------^
```

Tickets 03 through 07 may proceed independently after Ticket 02. Ticket 08
integrates the three production Domain adapters with calibrated quality policy;
Ticket 09 combines that policy with durable scale evidence. Ticket 10 is the
wide-refactor contract step and starts only after the replacement has passed
real three-domain acceptance.
