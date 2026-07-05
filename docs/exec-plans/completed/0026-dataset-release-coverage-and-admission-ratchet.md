# Plan 0026: Dataset Release Coverage and Admission Ratchet

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status

Completed on 2026-06-09.

## Goal

Tighten dataset release admission so a small release-candidate smoke run cannot
be mistaken for a sufficiently covered local MVP dataset version.

## Architecture

This plan ratchets the opt-in `dataset_release_report_v1` layer added in
[../completed/0024-profile-purpose-and-dataset-release-admission.md](../completed/0024-profile-purpose-and-dataset-release-admission.md).
It keeps candidate execution, held-out evaluation, profile promotion, async
orchestration, semantic duplicate detection, and the default synchronous CLI
unchanged. The release report will add a deterministic completeness decision
over existing manifest and quality-report evidence, then require a dedicated
release-candidate fixture to satisfy that decision.

## Tech Stack

- Python standard library: `dataclasses`, `json`, `pathlib`, and `unittest`.
- Existing modules: `synthesis.dataset_release`, `synthesis.contracts`,
  `synthesis.quality`, `synthesis.run_profiles`, `synthesis.tasks`, and
  `main.py`.
- Existing docs: [../../DATA.md](../../DATA.md),
  [../../ROADMAP.md](../../ROADMAP.md), and [../../PLANS.md](../../PLANS.md).
- Verification through `uv run python scripts/validate_docs.py` and
  `uv run python -m unittest`.

## Basis

- Plan 0024 made release eligibility explicit, but a current deterministic
  release-candidate probe using `tests/fixtures/run_profiles/foundation-fixture.json`
  can pass release admission with only 2 accepted samples and 1 verifier
  rejection.
- [../deferred/0014-async-local-orchestration-with-durable-queues.md](../deferred/0014-async-local-orchestration-with-durable-queues.md)
  remains deferred because the probe has 3 total candidates and sub-second
  runtime, well below the async trigger thresholds.
- [../indexes/0025-awm-runtime-boundary-and-shared-environment-kernel.md](../indexes/0025-awm-runtime-boundary-and-shared-environment-kernel.md)
  remains deferred because no second runtime consumer has been introduced.
- [../tech-debt/README.md](../tech-debt/README.md) keeps semantic duplicate
  detection deferred until volume or curriculum signals justify it.

## Why This Plan Now

The next risk is not throughput or runtime extraction. It is release semantics:
`profile_promotion` says a profile is good enough for the local MVP scope, while
`dataset_release` should say a concrete artifact set has enough sample evidence
to be treated as a releaseable dataset version. Plan 0024 separated those
decisions; this plan makes the later decision stricter.

## Scope

- Add release completeness thresholds to `dataset_release_report_v1`:
  - minimum accepted sample count;
  - maximum rejection rate;
  - required accepted task-type coverage;
  - required tool-combination coverage.
- Add an observed completeness summary to the release report using sanitized
  counts and quality-report slices only.
- Make release admission return `insufficient_evidence` when the artifact set is
  release-eligible by purpose but too small or under-covered.
- Add a deterministic release-candidate fixture/profile that satisfies the new
  release completeness gates without enabling async orchestration or semantic
  duplicate detection.
- Preserve `diagnostic_probe` and `benchmark` release ineligibility.
- Preserve the current opt-in behavior: no release report is written unless
  `--write-dataset-release-report` is supplied with evaluation and profile
  decision reports.

## Out of Scope

- Implementing async orchestration, durable queues, cancellation, resumption, or
  per-role cost tracking from plan 0014.
- Implementing semantic duplicate detection, embeddings, vector stores, or
  near-duplicate admission gates from `TD-0002`.
- Introducing the AWM runtime boundary from plan 0025.
- Changing held-out evaluation semantics, profile promotion thresholds, source
  governance, sandbox admission, or default non-profile CLI output.
- Treating release admission as proof of downstream model improvement.

## Contract Design

Extend `dataset_release_report_v1` with a `release_completeness` section:

```json
{
  "release_completeness": {
    "thresholds": {
      "min_accepted_samples": 5,
      "max_rejection_rate": 0.2,
      "required_task_types": [
        "lookup_contact_email",
        "contact_followup",
        "contact_branch_fallback"
      ],
      "required_tool_combinations": [
        "lookup_contact_email",
        "lookup_contact_email+record_contact_followup"
      ]
    },
    "observed": {
      "accepted": 6,
      "rejected": 1,
      "rejection_rate": 0.1428571429,
      "task_types": [
        "contact_branch_fallback",
        "contact_followup",
        "lookup_contact_email"
      ],
      "tool_combinations": [
        "lookup_contact_email",
        "lookup_contact_email+record_contact_followup"
      ]
    },
    "decision": {
      "status": "passed",
      "reasons": [
        "accepted 6 is at or above min_accepted_samples 5",
        "rejection_rate 0.1428571429 is at or below max_rejection_rate 0.2",
        "required task types are covered",
        "required tool combinations are covered"
      ],
      "triggered_by": [
        "accepted",
        "rejection_rate",
        "task_type_coverage",
        "tool_combination_coverage"
      ]
    }
  }
}
```

`decisions.dataset_release.status` remains one of `passed`, `failed`,
`blocked`, `ineligible`, or `insufficient_evidence`. When all earlier release
gates pass but `release_completeness.decision.status != "passed"`, the dataset
release decision must be `insufficient_evidence` with `triggered_by` including
`release_completeness`.

## File Map

- Modify `synthesis/dataset_release.py` to compute release completeness from
  manifest counts and `quality_report.slices.task_type` plus
  `quality_report.slices.tool_combination`.
- Modify `synthesis/contracts.py` to validate the new
  `release_completeness` object, thresholds, observed values, and decision.
- Modify `synthesis/tasks.py` and `synthesis/run_profiles.py` only if a new
  deterministic release-candidate generation mode or fixture profile is needed.
- Add or modify `tests/fixtures/run_profiles/*release*.json` for the dedicated
  release-candidate profile.
- Add `tests/test_dataset_release.py` coverage for passed, insufficient, and
  ineligible release outcomes.
- Extend `tests/test_cli.py` with an end-to-end release-candidate fixture
  command.
- Update [../../DATA.md](../../DATA.md), [../../ROADMAP.md](../../ROADMAP.md),
  and [../../PLANS.md](../../PLANS.md).

## Implementation Tasks

### Task 1: Add Release Completeness Contract Tests

- [x] Add a unit test where a release-candidate report with 2 accepted samples,
  1 rejection, and missing branching coverage returns
  `dataset_release.status == "insufficient_evidence"`.
- [x] Add a unit test where a release-candidate report with at least 5 accepted
  samples, rejection rate at or below 0.2, required task types, and required
  tool combinations returns `dataset_release.status == "passed"`.
- [x] Add a contract test that rejects malformed `release_completeness`
  thresholds, unsupported decision statuses, and non-list coverage fields.

### Task 2: Implement Release Completeness Decision

- [x] Add a small threshold record or mapping in `synthesis.dataset_release`.
- [x] Compute accepted count, rejected count, rejection rate, task-type coverage,
  and tool-combination coverage from already sanitized artifacts.
- [x] Attach `release_completeness` to every dataset release report.
- [x] Make `dataset_release` return `insufficient_evidence` when completeness is
  not passed and earlier gates did not already fail, block, or mark the profile
  ineligible.

### Task 3: Add a Dedicated Release-Candidate Fixture

- [x] Add deterministic fixture coverage that can produce at least 5 accepted
  contacts samples covering lookup, state change, and branch fallback behavior.
- [x] Add a `release_candidate` run-profile fixture for that deterministic path.
- [x] Keep the existing `foundation-fixture` profile valid as a smoke profile;
  it should no longer be enough evidence for release admission if it remains at
  2 accepted samples.

### Task 4: Update CLI and Artifact Tests

- [x] Extend CLI tests so the smoke release-candidate profile writes
  `dataset_release_report.json` with `dataset_release.status ==
  "insufficient_evidence"`.
- [x] Add an end-to-end deterministic release-candidate command that writes
  evaluation, profile decision, and dataset release reports with
  `dataset_release.status == "passed"`.
- [x] Confirm the default `uv run python main.py` path still omits
  `dataset_release_report`.

### Task 5: Docs and Validation

- [x] Update [../../DATA.md](../../DATA.md) with the release completeness
  thresholds, observed coverage fields, and decision behavior.
- [x] Update [../../ROADMAP.md](../../ROADMAP.md) to show this ratchet before
  async orchestration.
- [x] Run `uv run python scripts/validate_docs.py`.
- [x] Run `uv run python -m unittest`.

## Validation

```bash
uv run python scripts/validate_docs.py
uv run python -m unittest
uv run python main.py --run-profile tests/fixtures/run_profiles/foundation-fixture.json --write-evaluation-report --write-profile-decision-report --write-dataset-release-report --output-dir artifacts/foundation-release-smoke
uv run python main.py --run-profile tests/fixtures/run_profiles/foundation-release-candidate.json --write-evaluation-report --write-profile-decision-report --write-dataset-release-report --output-dir artifacts/foundation-release-candidate
```

Expected outcomes:

- The smoke profile produces `dataset_release.status == "insufficient_evidence"`
  unless its accepted sample and coverage evidence is expanded.
- The dedicated release-candidate profile produces `dataset_release.status ==
  "passed"`.
- Async orchestration and semantic duplicate detection remain deferred unless
  their existing thresholds are met.

## Acceptance Criteria

- `dataset_release_report_v1` includes machine-readable release completeness
  thresholds, observed coverage, and decision fields.
- A release-candidate profile cannot pass dataset release admission solely
  because profile promotion and held-out evaluation passed.
- Small or under-covered release-candidate artifact sets return
  `insufficient_evidence`.
- A deterministic release-candidate fixture can pass all release admission gates
  without enabling async orchestration, semantic duplicate detection, or AWM
  runtime extraction.
- Documentation validation and the full unit suite pass.
