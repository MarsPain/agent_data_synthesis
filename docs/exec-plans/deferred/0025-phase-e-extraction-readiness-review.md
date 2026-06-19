# Plan 0025 Phase E: Extraction Readiness Review

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status

Deferred. Activate only after
[0025 Phase D](0025-phase-d-adapter-surface-generalization.md) has completed or
after equivalent runtime, consumer, rollout, and adapter evidence exists.

## Goal

Make a documented evidence-based decision about whether the internal runtime
kernel should remain inside this repository or proceed to a separate
`awm_runtime` extraction plan.

## Why This Phase

Package extraction is expensive. It introduces versioning, compatibility shims,
cross-repository tests, release process, and migration cost. Phase E prevents
two failure modes:

- extracting too early, before the runtime API is stable;
- never extracting, after multiple consumers already depend on a mature runtime
  boundary.

Phase E is a decision gate. It should not perform extraction.

## Architecture

Review the runtime boundary using evidence from completed phases:

```text
runtime descriptors
  + runtime sessions
  + episode/replay/reward consumers
  + rollout collector
  + local adapter surface
  -> extraction decision
```

The decision must separate domain packs from the runtime kernel. Contacts and
mobile fixtures are not the package boundary; execution contracts, descriptors,
sessions, envelopes, and episode logging are the candidate package boundary.

## Scope

- Audit runtime-facing modules for dataset, profile, release, provider, or
  domain leakage.
- Audit consumers for direct contacts/mobile assumptions.
- Audit tests for cross-consumer coverage across contacts, mobile, and fake
  runtime descriptors.
- Produce an extraction readiness report under `docs/generated/`.
- Update plan lifecycle docs with the decision:
  keep internal, continue hardening, or draft Phase F extraction.

## Out of Scope

- Moving files into a package.
- Creating a new repository.
- Publishing artifacts.
- Changing runtime APIs.
- Adding new runtime features.

## Readiness Criteria

Extraction is eligible only if all of these are true:

- At least two production domain runtimes use the same descriptor/session
  boundary.
- At least one fake/minimal runtime test proves the boundary is not
  contacts/mobile-specific.
- Synthesis, episode quality, executable replay, reward labels, diagnostic
  rollouts, and local adapter manifests consume runtime descriptors or sessions.
- Runtime metadata and descriptors reject dataset version, release admission,
  profile promotion, provider prompts, credentials, raw sources, and host paths.
- Adding a new runtime does not require editing core replay or reward-label
  allowlists.
- Unused runtime methods have been removed or explicitly marked experimental.
- Docs clearly define what belongs to runtime, domain packs, synthesis, reward,
  release, and adapter layers.

## File Map

- Add `docs/generated/awm-runtime-extraction-readiness.md`.
- Modify `docs/exec-plans/deferred/0025-awm-runtime-phase-index.md`
  with the readiness decision.
- Modify `docs/PLANS.md` and `docs/exec-plans/deferred/README.md` if Phase F
  becomes the next deferred or active plan.
- Optionally add `scripts/audit_runtime_boundary.py` only if manual review is
  too error-prone.
- Add or extend `tests/test_docs_validation.py` only if the readiness report or
  plan lifecycle needs validation.

## Implementation Tasks

### Task 1: Boundary Leakage Audit

- [ ] Search runtime modules for dataset-release, profile-decision, provider,
  credential, raw-source, and host-path concepts.
- [ ] Search consumer modules for direct runtime id allowlists and domain
  imports outside registry/session boundaries.
- [ ] Record findings in the readiness report with file references.

### Task 2: Consumer Evidence Audit

- [ ] List which consumers use descriptors, sessions, action envelopes, and
  episode logs.
- [ ] Confirm contacts, mobile, and fake runtime coverage exists for replay,
  reward labels, rollout collection, and adapter manifests.
- [ ] Identify any consumer that still depends on a domain branch.

### Task 3: API Surface Audit

- [ ] List runtime methods and fields.
- [ ] Mark each as used by synthesis, replay, reward labels, rollout,
  adapter, or tests.
- [ ] Recommend removal, internal-only status, or extraction eligibility for
  each method.

### Task 4: Decision Report

- [ ] Write `docs/generated/awm-runtime-extraction-readiness.md`.
- [ ] Include decision status: `keep_internal`, `continue_hardening`, or
  `ready_for_extraction_plan`.
- [ ] Include reasons, evidence, unresolved risks, and the next plan pointer.

### Task 5: Plan Lifecycle Update

- [ ] If status is `keep_internal`, update 0025 overview with the revisit
  trigger.
- [ ] If status is `continue_hardening`, identify the next internal hardening
  plan.
- [ ] If status is `ready_for_extraction_plan`, add or activate Phase F as the
  next extraction planning document.

### Task 6: Validation

- [ ] Run `uv run python scripts/validate_docs.py`.
- [ ] Run `uv run python -m unittest tests.test_docs_validation`.
- [ ] Run focused runtime/consumer tests cited in the readiness report.

## Acceptance Criteria

- A generated readiness report records the extraction decision and evidence.
- The decision is based on consumer pressure and boundary stability, not package
  aesthetics.
- Plan indexes point to the correct next step.
- No package extraction is performed in this phase.

## Follow-On

Only if Phase E returns `ready_for_extraction_plan`, Phase F should be moved
from deferred to active.
