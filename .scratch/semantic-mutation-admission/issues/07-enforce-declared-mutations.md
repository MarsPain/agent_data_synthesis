# 07 — Enforce Admission Before All Declared Mutations

**What to build:** Let a synthesis operator select enforce mode and know that no
declared state-changing tool can execute unless deterministic validation passes
and an independent semantic judge returns `supported`. Every other verdict or
provider outcome must reject before execution while disabled, shadow, and
read-only behavior remain stable.

**Blocked by:** [03 — Use an Independent Model for Shadow Admission](03-independent-model-shadow-admission.md), [04 — Shadow-admit Contact Follow-ups](04-shadow-contact-followups.md), [05 — Shadow-admit Mobile Mutations](05-shadow-mobile-mutations.md), [06 — Shadow-admit Workspace Task Creation](06-shadow-workspace-task-creation.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Semantic Mutation Admission](../../../docs/product-specs/semantic-mutation-admission.md)

## Acceptance criteria

- [ ] Only deterministic success followed by an independent `supported` verdict permits a declared mutation to execute.
- [ ] Unsupported, uncertain, invalid, unavailable, timed-out, and retry-exhausted outcomes reject before the first tool invocation.
- [ ] Enforce configuration rejects absent judge identity and generator/judge model equality.
- [ ] Release-candidate profiles require enforce mode regardless of the mutations eventually produced.
- [ ] Every current state-changing action is covered without domain-specific enforcement branches.
- [ ] Rejections expose sanitized admission evidence and bounded reasons without raw judge material.
- [ ] Disabled mode makes no judge calls, shadow mode never changes outcomes, and read-only candidates retain existing behavior.
- [ ] Candidate-processing tests prove the tool environment remains untouched on every non-supported enforce path, including reruns.
- [ ] Run-level tests cover valid and invalid configurations, model independence, provider failure, and legacy-profile compatibility.

## Scope guard

Do not claim release readiness merely because enforce behavior exists. Reviewed
calibration and representative activation evidence remain separate gates.
