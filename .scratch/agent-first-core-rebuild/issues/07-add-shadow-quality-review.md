# 07 — Add Shadow Quality Review and Blind-Label Import

**What to build:** Expose deterministic admission, diversity, optional shadow
judgments, blind review queues, and validated human labels without depending
on calibrated semantic enforcement.

**Blocked by:** [03 — Add Contacts and establish early Agent feasibility](03-add-contacts-domain-adapter.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [ ] Demonstration admission requires deterministic execution, authorization, assessment, final grounding, unsafe-material, and semantic-key gates; successful recovery remains eligible and other outcomes stay separate.
- [ ] The judge sees only public task, observable events, bounded deterministic results, and rubric; its known identity differs from both task generator and Agent identities.
- [ ] Each judgment uses the five approved dimensions, bounded reasons, and event references. Any fail dominates, otherwise uncertain dominates, and all dimensions must pass for Episode pass.
- [ ] Missing/matching identities and missing/invalid/provider-failed judgments are explicitly unavailable. All shadow verdicts leave admission unchanged.
- [ ] Reports expose yield, duplicates, structural-family distribution, known/unknown capacity, recovery, judgments, usage, and admission/review status without constant quality scores.
- [ ] Review queues have explicit diagnostic-development or held-out-evaluation purpose and frozen membership. Development selection includes every bounded fail/uncertain outcome plus stratified passes; evaluation selection never depends on a judge verdict.
- [ ] Blind review hides model identities, judge verdicts, admission decisions, and suggested deterministic labels while exposing the public task, tools, and observable trajectory.
- [ ] Basic review-label import belongs to this ticket: only known queued ids and matching cohort/purpose are accepted, with validated dimensions and evidence references; duplicate, foreign, malformed, or unsafe labels are rejected.
- [ ] Partial label submissions stay incomplete until required labels are present. Human aggregate verdicts follow the same five-dimension rule; only human-pass labels identify a human-approved subset.
- [ ] Review imports preserve finalized Episode files and cohort membership. Negatives and diagnostic reviews cannot silently enter a demonstration-acceptance denominator.
- [ ] Public judgment/review artifacts exclude unrestricted rationale, provider payloads, credentials, oracle fields, and absolute source paths.
- [ ] Tests prove shadow invariance, blindness, cohort isolation, partial/invalid import behavior, and correct human subset identification through public interfaces.

## Scope guard

Do not implement or activate semantic enforcement, run paid campaigns, or claim
that error-enriched review rates estimate final dataset quality. Basic human
review and import must remain usable when Ticket 08 is absent or its judge is
ineligible. Queue/cohort metadata belongs to the existing report and label
contracts, not a new qualification subsystem.
