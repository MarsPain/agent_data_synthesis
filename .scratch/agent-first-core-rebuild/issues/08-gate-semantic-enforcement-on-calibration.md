# 08 — Gate Semantic Enforcement on Human Calibration

**What to build:** Let a quality reviewer import stratified blind-review labels
and allow semantic judgment to become an admission gate only when measured
agreement and error rates satisfy every global and per-Domain threshold.

**Blocked by:** [03 — Add the Contacts Domain adapter](03-add-contacts-domain-adapter.md), [04 — Add the Mobile Messages Domain adapter](04-add-mobile-messages-domain-adapter.md), [05 — Add the Workspace Tasks Domain adapter](05-add-workspace-tasks-domain-adapter.md), [07 — Add shadow quality review](07-add-shadow-quality-review.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [ ] Review-label import accepts only known queued Episode ids and bounded dimension verdicts, and rejects duplicate, missing, foreign, malformed, or unsafe labels.
- [ ] Calibration requires at least one hundred reviewed Episodes, at least thirty from each production Domain, every fail or uncertain judgment from the bounded campaign, and stratified passing judgments.
- [ ] The calibration result reports overall and per-Domain agreement, false-pass rate, false-fail rate, sample counts, missing strata, and critical safety findings.
- [ ] Enforcement is eligible only when overall agreement is at least 85 percent, false-pass rate is at most 5 percent, false-fail rate is at most 10 percent, every Domain false-pass rate is at most 10 percent, and judge-passed Episodes contain no human-confirmed critical safety failure.
- [ ] Any unmet threshold, missing Domain quota, unknown model identity, or incomplete label set leaves the judge in shadow mode with bounded reasons.
- [ ] Enforce mode rejects judge-failed Episodes, routes uncertain Episodes out of demonstrations, and still cannot admit an Episode that failed a deterministic gate.
- [ ] A quality-policy identity binds the calibrated rubric, judge identity, threshold set, and review evidence used by an enforcing run without creating a cumulative qualification state machine.
- [ ] Recalibration under a changed rubric, model, or threshold set creates a new policy identity and cannot borrow the prior decision.
- [ ] Deterministic calibration fixtures exercise every inclusive threshold, one-below-threshold case, per-Domain failure, critical safety failure, and successful activation without real provider calls.

## Scope guard

Do not run the real-provider campaign, weaken the approved thresholds, add
publication qualification, or treat confidence scores and free-form rationale
as calibration evidence.
