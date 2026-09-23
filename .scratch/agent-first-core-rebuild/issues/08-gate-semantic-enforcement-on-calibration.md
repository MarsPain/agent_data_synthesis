# 08 — Gate Optional Semantic Enforcement on Held-Out Evaluation

**What to build:** Make explicit enforce-mode runs eligible only after a frozen
judge policy passes independent human evaluation, while leaving shadow core
operation and cutover independent of activation.

**Blocked by:** [05 — Add the Workspace Tasks Domain adapter](05-add-workspace-tasks-domain-adapter.md), [07 — Add shadow quality review and blind-label import](07-add-shadow-quality-review.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [x] The existing review-label import is reused; this ticket does not create a competing import or review workflow.
- [x] Calibration development requires at least one hundred reviewed Episodes, thirty per production Domain, all fail/uncertain outcomes from its bounded campaign, and stratified passes; its raw rates are labeled diagnostic.
- [x] Activation uses a separate untouched cohort with at least one hundred deterministically eligible Episodes and thirty per Domain, selected without judge-verdict filtering and reviewed in full.
- [x] Evaluation excludes development semantic-task/grounding groups and rejects new ids or paraphrases as a way to bypass that separation. Rubric, model/prompt settings, source/task scope, and thresholds are frozen before label inspection.
- [x] Judge and human dimensions aggregate using fail, then uncertain, then all-pass precedence. Human uncertain is not approval; unavailable judge verdicts count as uncertain and remain visible.
- [x] Metrics implement the exact parent-spec formulas: agreement over all reviewed Episodes; false-pass over judge-pass Episodes; false-fail over human-pass Episodes. Reports include all numerators, denominators, confusion counts, and overall/per-Domain values.
- [x] Eligibility requires overall agreement at least 85%, overall false-pass at most 5%, overall false-fail at most 10%, per-Domain false-pass at most 10%, and zero human-confirmed critical safety failures among judge passes.
- [x] Missing labels, quotas, required denominators, known independent identities, or untouched evaluation evidence leave enforcement ineligible. Finite-cohort rates are not represented as population guarantees.
- [x] One flat policy identity binds the rubric, judge/generator/Agent identities and prompt/decoding settings, Domain versions, source/task-distribution scope, thresholds, and evaluation evidence. Out-of-scope changes require a new policy and fresh evaluation.
- [x] Enforcement is chosen only for a new run; it admits only judge passes that also satisfy deterministic gates. Fail/uncertain/unavailable results stay out, and an ineligible enforce request fails before provider dispatch.
- [x] Deterministic fixtures exercise exact thresholds and failures, undefined denominators, uncertain verdicts, identity/scope changes, reused evaluation data, critical safety failures, and successful activation.
- [x] Tests prove failed or unavailable activation leaves shadow operation usable and cannot by itself block an otherwise successful core cutover.

## Implementation notes

- `agent_synthesis.enforcement` owns the frozen policy, finite-cohort metrics,
  eligibility report, and report writer. `SynthesisEngine` projects existing
  frozen cohorts and imported direct-human labels into that evaluator; it does
  not create a second review or import path.
- Domain assessments now provide explicit task-type and difficulty review axes;
  diagnostic pass fill combines those axes with the existing structural family.
  The activation record carries the exact frozen development/evaluation evidence
  and is recomputed before enforce-mode dispatch.
- Enforced runs bind an eligible activation record in their immutable
  configuration, preflight the current Domain/model/judge/scope settings before
  any provider call, and retain explicit semantic verdicts in public admission
  records. Shadow-only operation remains unchanged.
- This delivery used deterministic fixtures only. No paid calibration or real
  activation was requested or performed.

## Final validation

- Focused semantic-enforcement, shadow-review, core, resume, architecture,
  model, and CLI suites passed.
- `uv run python -m compileall -q agent_synthesis tests` passed.
- `uv run python scripts/validate_docs.py` passed.
- `uv run python -m unittest` passed.
- Final two-axis review found no remaining Standards or Spec issue after the
  activation-integrity, cohort-separation, and review-stratification fixes.

## Scope guard

This ticket's implementation can complete with deterministic fixtures; real
activation is a separately authorized optional follow-up recorded here. It is
not a prerequisite for Tickets 09 or 10. Do not run paid calibration here without
authorization, tune against held-out acceptance labels, reuse a tuned-on cohort
for the revised policy, or add a cumulative qualification state machine.
