# Plan 0019: Profile-Attributed Quality and Comparison

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

## Status

Planned on 2026-05-30. Completed on 2026-05-30.

## Goal

Propagate sanitized run-profile attribution into samples, rejections, quality
report slices, and parent comparisons so synchronous profile runs can be compared
without relying on manifest-only metadata.

## Architecture

This plan keeps run profiles declarative and synchronous. `main.py` and
`synthesis.pipeline` already pass sanitized run-profile metadata to manifest
writing; this plan narrows that metadata into a per-record attribution contract
and threads it through dataset assembly and quality reporting. The implementation
must not duplicate raw profile files, local source paths, source payloads,
provider prompts, headers, API keys, or arbitrary profile content across
artifacts.

## Tech Stack

- Python standard library dataclasses, dictionaries, JSON serialization, and
  unittest.
- Existing modules under `synthesis/`: `run_profiles`, `pipeline`, `datasets`,
  `quality`, and `contracts`.
- Existing validation through `scripts/validate_docs.py` and
  `uv run python -m unittest`.

---

## Basis

- [../../PLANS.md](../../PLANS.md) has no active successor after
  [../completed/0018-profile-driven-source-admission-and-contacts-environment-overrides.md](../completed/0018-profile-driven-source-admission-and-contacts-environment-overrides.md).
- [../../ROADMAP.md](../../ROADMAP.md) lists async orchestration next, but
  [../deferred/0014-async-local-orchestration-with-durable-queues.md](../deferred/0014-async-local-orchestration-with-durable-queues.md)
  remains deferred until single runs exceed about 10 minutes or 100+
  candidates.
- [../../BACKEND.md](../../BACKEND.md) says to use synchronous run profiles and
  deterministic contacts scale probes before activating a local async runner.
  A deterministic 25-candidate profile run completed synchronously with
  `accepted=14` and `rejected=11`, so the async trigger remains unmet.
- [../../DATA.md](../../DATA.md) explicitly defers run-profile id and
  generation-mode quality slices until profile metadata is propagated to sample
  or rejection records.
- Plans 0017 and 0018 made profiles operational and source-governed, but
  profile attribution is still manifest-only. That limits quality slicing,
  parent comparison, and scale-probe interpretation.

## Scope

- Define a minimal sanitized run-profile attribution record for per-sample and
  per-rejection metadata:
  - `schema_version`;
  - `profile_id`;
  - `generation_mode`;
  - `config_hash`;
  - `source` summary only when already present in sanitized profile metadata.
- Attach the attribution record to accepted samples under
  `lineage.run_profile`.
- Attach the attribution record to rejected candidates under
  `details.run_profile`, including generation-stage, source-policy,
  environment-source, candidate-schema, execution, verification, duplicate, and
  logical-support rejection paths that occur inside the profile-configured
  pipeline.
- Extend quality report slices with:
  - `run_profile_id`;
  - `generation_mode`;
  - `run_profile_schema_version`.
- Extend parent comparison output so profile-related slice keys participate in
  existing `new_slice_keys` and `removed_slice_keys` behavior.
- Preserve manifest-level `run_profile` metadata as the run-level summary.
- Prove no-profile runs preserve current artifact shape by omitting
  `lineage.run_profile` and `details.run_profile`.
- Prove profile-local source runs do not leak raw local paths, contact payloads,
  source emails, provider prompts, headers, API keys, or raw profile JSON into
  samples, rejections, quality reports, source events, or manifests.
- Update canonical docs and plan indexes after implementation.

## Out of Scope

- Async orchestration, durable queues, cancellation, resumption, or per-role
  async cost tracking from plan 0014.
- Semantic duplicate detection from `TD-0002`.
- New run-profile schema versions beyond the existing `run_profile_v1` and
  `run_profile_v2` contracts.
- Persisting raw profile files, local source paths, raw source payloads,
  authorization headers, provider prompts, API keys, or arbitrary environment
  variables in artifacts.
- External MCP server discovery, browser automation, generated environment
  builders, generated tool handlers, generated verifiers, or judge acceptance.
- A web UI, dashboard, or interactive human-review interface.

## Proposed Attribution Contract

For accepted samples, attach this shape under `lineage.run_profile`:

```json
{
  "schema_version": "run_profile_attribution_v1",
  "profile_schema_version": "run_profile_v2",
  "profile_id": "foundation_profile_local_contacts",
  "generation_mode": "foundation_fixture",
  "config_hash": "sha256:...",
  "source": {
    "kind": "local_contacts_json",
    "source_id": "source_profile_contacts_v1",
    "content_hash": "sha256:...",
    "license_label": "cc-by-4.0",
    "source_policy_hash": "sha256:..."
  }
}
```

For rejected candidates, attach the same shape under `details.run_profile`.

The attribution record is derived only from `RunProfile.sanitized_metadata()`.
It must not include `target_candidate_count`, enabled feature lists, raw profile
paths, source file paths, payload rows, contact names, contact emails, prompts,
headers, or secrets. `target_candidate_count` remains manifest-level run
metadata, not per-record lineage.

## File Map

- Modify `synthesis/datasets.py`:
  - add a helper that converts sanitized manifest run-profile metadata into a
    narrow per-record attribution record;
  - attach attribution to samples and rejections before validation and writing;
  - keep no-profile artifacts unchanged.
- Modify `synthesis/contracts.py`:
  - validate `lineage.run_profile` on samples when present;
  - validate `details.run_profile` on rejections when present;
  - reject attribution records with raw path-like or payload-like fields.
- Modify `synthesis/quality.py`:
  - add quality slices for run-profile id, generation mode, and profile schema
    version;
  - read attribution from accepted sample lineage and rejection details.
- Modify `tests/test_contracts.py`:
  - cover valid and invalid profile attribution records on samples and
    rejections.
- Modify `tests/test_quality_reporting.py`:
  - cover profile slices for accepted and rejected records.
- Modify `tests/test_foundation_pipeline.py`:
  - prove default no-profile artifacts omit run-profile attribution;
  - prove profile runs attach sanitized attribution to samples and rejections.
- Modify `tests/test_cli.py`:
  - prove profile-local contacts source CLI artifacts remain redacted after
    attribution propagation.
- Update docs:
  - [../../DATA.md](../../DATA.md) with the implemented attribution and slice
    contract;
  - [../../BACKEND.md](../../BACKEND.md) with the profile attribution step in
    the job lifecycle;
  - [../../ROADMAP.md](../../ROADMAP.md) when the plan is completed;
  - [../../PLANS.md](../../PLANS.md) and plan bucket READMEs when moving the
    plan to completed.

## Implementation Tasks

### Task 1: Characterize Current No-Profile and Profile Artifact Shapes

- [x] Add tests showing `uv run python main.py` without `--run-profile`
  produces samples with no `lineage.run_profile` key and rejections with no
  `details.run_profile` key.
- [x] Add tests showing profile runs currently store profile metadata only in
  `manifest.run_profile`.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_foundation_pipeline tests.test_cli
  ```

  Expected result before implementation: the new attribution assertions fail
  for profile runs and pass for no-profile omission.

### Task 2: Add the Sanitized Attribution Builder

- [x] In `synthesis/datasets.py`, add a private helper such as
  `_run_profile_attribution(run_profile_metadata)` that returns `None` when no
  profile metadata is supplied.
- [x] Map only `schema_version`, `profile_id`, `generation_mode`,
  `config_hash`, and optional sanitized `source` into the attribution record.
- [x] Rename the profile schema field to `profile_schema_version` and set
  attribution `schema_version` to `run_profile_attribution_v1`.
- [x] Add unit coverage proving the helper excludes `target_candidate_count`,
  `enabled_features`, raw paths, and any unknown metadata keys.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_foundation_pipeline
  ```

  Expected result: attribution helper tests pass, while full profile propagation
  tests may still fail until Task 3.

### Task 3: Propagate Attribution to Samples and Rejections

- [x] In `write_dataset_artifacts()`, derive the attribution record once from
  `run_profile_metadata`.
- [x] Attach attribution to each accepted sample under
  `sample["lineage"]["run_profile"]` only when attribution exists.
- [x] Attach attribution to each rejection under
  `rejection["details"]["run_profile"]` only when attribution exists and
  `details` is an object.
- [x] Ensure all early-return pipeline paths that already call
  `write_dataset_artifacts()` receive the same behavior without extra branches.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_foundation_pipeline tests.test_cli
  ```

  Expected result: profile propagation tests pass and no-profile omission tests
  continue to pass.

### Task 4: Validate Attribution Contracts

- [x] In `synthesis/contracts.py`, add validation for
  `run_profile_attribution_v1`.
- [x] Require these fields:
  - `schema_version == "run_profile_attribution_v1"`;
  - non-empty `profile_schema_version`;
  - non-empty `profile_id`;
  - non-empty `generation_mode`;
  - `config_hash` matching the existing `sha256:<64 hex>` format.
- [x] When `source` is present, require only `kind`, `source_id`,
  `content_hash`, `license_label`, and `source_policy_hash`.
- [x] Reject unexpected attribution keys and unexpected source keys.
- [x] Add tests for valid v1/v2 attribution, invalid hashes, unknown keys,
  missing fields, and raw-path-like source keys such as `path`.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_contracts tests.test_foundation_pipeline
  ```

  Expected result: contract tests and artifact-writing tests pass.

### Task 5: Add Profile Quality Slices

- [x] In `synthesis/quality.py`, add slice dimensions:
  - `run_profile_id`;
  - `generation_mode`;
  - `run_profile_schema_version`.
- [x] For accepted samples, read attribution from
  `sample["lineage"]["run_profile"]`.
- [x] For rejections, read attribution from
  `rejection["details"]["run_profile"]`.
- [x] Add tests proving accepted and rejected records contribute to the same
  profile slice counts.
- [x] Add tests proving no-profile records do not create `"unknown"` profile
  slices.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_quality_reporting
  ```

  Expected result: quality profile slice tests pass.

### Task 6: Verify Parent Comparison Picks Up Profile Slices

- [x] Add a parent-comparison test where the parent report lacks profile slices
  and the current report contains them.
- [x] Assert `new_slice_keys` includes the new profile slice keys in the existing
  slice-delta format.
- [x] Keep the parent comparison schema unchanged unless tests prove the current
  shape cannot express profile-slice changes.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_quality_reporting tests.test_foundation_pipeline
  ```

  Expected result: parent comparison detects profile slice keys without a new
  artifact contract.

### Task 7: Redaction and CLI Fixture Coverage

- [x] Extend the profile-local contacts source CLI test to inspect:
  - `samples.jsonl`;
  - `rejections.jsonl`;
  - `quality_report.json`;
  - `manifest.json`;
  - `source_events.jsonl`.
- [x] Assert the combined exported text does not contain:
  - `contacts-profile.json`;
  - raw local absolute paths;
  - source contact emails from the profile fixture;
  - raw profile JSON fields outside the attribution allowlist.
- [x] Assert samples and rejections contain `run_profile_attribution_v1` with
  sanitized source summary fields.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_cli tests.test_source_governance
  ```

  Expected result: redaction and source-governance tests pass.

### Task 8: Update Canonical Docs and Indexes

- [x] Update [../../DATA.md](../../DATA.md) to replace the deferred
  run-profile-slice wording with the implemented attribution and quality-slice
  contract.
- [x] Update [../../BACKEND.md](../../BACKEND.md) to mention profile attribution
  in the artifact export step.
- [x] Update [../../ROADMAP.md](../../ROADMAP.md) to mark profile-attributed
  quality and comparison as implemented when the plan is complete.
- [x] Move this plan to `../completed/`, update [../../PLANS.md](../../PLANS.md),
  and update active/completed bucket READMEs only after implementation is
  accepted.
- [x] Run:

  ```bash
  uv run python scripts/validate_docs.py
  ```

  Expected result: documentation validation passes.

### Task 9: Final Verification

- [x] Run the full unit suite:

  ```bash
  uv run python -m unittest
  ```

  Expected result: all tests pass.

- [x] Run deterministic profile commands:

  ```bash
  uv run python main.py --run-profile tests/fixtures/run_profiles/foundation-scale-probe-25.json --output-dir artifacts/foundation-scale-probe
  uv run python main.py --run-profile tests/fixtures/run_profiles/profile-local-contacts.json --output-dir artifacts/foundation-profile-local-contacts
  ```

  Expected result: both commands complete synchronously and write manifests,
  samples, rejections, and quality reports with sanitized run-profile
  attribution.

- [x] Inspect exported artifacts for forbidden profile/source leakage before
  marking the plan complete.

## Validation

- `uv run python scripts/validate_docs.py`
- `uv run python -m unittest`
- `uv run python main.py --run-profile tests/fixtures/run_profiles/foundation-scale-probe-25.json --output-dir artifacts/foundation-scale-probe`
- `uv run python main.py --run-profile tests/fixtures/run_profiles/profile-local-contacts.json --output-dir artifacts/foundation-profile-local-contacts`

## Acceptance Criteria

- Profile-configured runs attach sanitized profile attribution to accepted
  samples and rejected candidates.
- No-profile runs omit profile attribution entirely.
- Quality reports include profile id, generation mode, and profile schema
  version slices.
- Parent comparison reports surface new or removed profile slice keys through
  the existing comparison contract.
- Manifest-level `run_profile` metadata remains the run-level summary.
- Raw profile files, local source paths, source payloads, contact emails,
  prompts, headers, API keys, and arbitrary profile keys are not written through
  attribution.
- Plan 0014 remains deferred unless the final deterministic commands cross the
  documented runtime or candidate-count trigger.
- `TD-0002` remains unresolved unless the implementation produces a concrete
  dataset-volume or curriculum-benchmark signal that justifies semantic
  duplicate detection.
