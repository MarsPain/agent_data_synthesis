# 08 — Gate Optional Semantic Enforcement on Held-Out Evaluation

**What to build:** Make explicit enforce-mode runs eligible only after a frozen
judge policy passes independent human evaluation, while leaving shadow core
operation and cutover independent of activation.

**Blocked by:** [05 — Add the Workspace Tasks Domain adapter](05-add-workspace-tasks-domain-adapter.md), [07 — Add shadow quality review and blind-label import](07-add-shadow-quality-review.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [ ] The existing review-label import is reused; this ticket does not create a competing import or review workflow.
- [ ] Calibration development requires at least one hundred reviewed Episodes, thirty per production Domain, all fail/uncertain outcomes from its bounded campaign, and stratified passes; its raw rates are labeled diagnostic.
- [ ] Activation uses a separate untouched cohort with at least one hundred deterministically eligible Episodes and thirty per Domain, selected without judge-verdict filtering and reviewed in full.
- [ ] Evaluation excludes development semantic-task/grounding groups and rejects new ids or paraphrases as a way to bypass that separation. Rubric, model/prompt settings, source/task scope, and thresholds are frozen before label inspection.
- [ ] Judge and human dimensions aggregate using fail, then uncertain, then all-pass precedence. Human uncertain is not approval; unavailable judge verdicts count as uncertain and remain visible.
- [ ] Metrics implement the exact parent-spec formulas: agreement over all reviewed Episodes; false-pass over judge-pass Episodes; false-fail over human-pass Episodes. Reports include all numerators, denominators, confusion counts, and overall/per-Domain values.
- [ ] Eligibility requires overall agreement at least 85%, overall false-pass at most 5%, overall false-fail at most 10%, per-Domain false-pass at most 10%, and zero human-confirmed critical safety failures among judge passes.
- [ ] Missing labels, quotas, required denominators, known independent identities, or untouched evaluation evidence leave enforcement ineligible. Finite-cohort rates are not represented as population guarantees.
- [ ] One flat policy identity binds the rubric, judge/generator/Agent identities and prompt/decoding settings, Domain versions, source/task-distribution scope, thresholds, and evaluation evidence. Out-of-scope changes require a new policy and fresh evaluation.
- [ ] Enforcement is chosen only for a new run; it admits only judge passes that also satisfy deterministic gates. Fail/uncertain/unavailable results stay out, and an ineligible enforce request fails before provider dispatch.
- [ ] Deterministic fixtures exercise exact thresholds and failures, undefined denominators, uncertain verdicts, identity/scope changes, reused evaluation data, critical safety failures, and successful activation.
- [ ] Tests prove failed or unavailable activation leaves shadow operation usable and cannot by itself block an otherwise successful core cutover.

## Scope guard

This ticket's implementation can complete with deterministic fixtures; real
activation is a separately authorized optional follow-up recorded here. It is
not a prerequisite for Tickets 09 or 10. Do not run paid calibration here without
authorization, tune against held-out acceptance labels, reuse a tuned-on cohort
for the revised policy, or add a cumulative qualification state machine.
