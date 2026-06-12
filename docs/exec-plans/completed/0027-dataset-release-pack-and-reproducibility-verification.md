# Plan 0027: Dataset Release Pack and Reproducibility Verification

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

## Status

Completed on 2026-06-12.

## Goal

Turn a passed `dataset_release_report_v1` artifact set into a reproducible,
hash-locked release pack that can be verified later without rerunning candidate
generation.

## Architecture

This plan adds a narrow release-pack layer after dataset release admission. It
does not change candidate generation, profile promotion, held-out evaluation,
dataset release admission thresholds, async orchestration, semantic duplicate
detection, or the default synchronous CLI path.

The release pack reads existing sanitized artifacts, records file-level hashes
and release evidence, validates cross-artifact consistency, and exposes a
standalone verification command. Verification proves that a release directory is
internally consistent and still matches the artifact hashes recorded at pack
creation time; it does not claim downstream model improvement.

## Tech Stack

- Python standard library: `dataclasses`, `hashlib`, `json`, `pathlib`, and
  `unittest`.
- Existing modules: `synthesis.contracts`, `synthesis.dataset_release`,
  `synthesis.datasets`, `synthesis.evaluation`, `synthesis.profile_decisions`,
  and `main.py`.
- New module: `synthesis.release_pack`.
- New script: `scripts/verify_dataset_release.py`.
- Verification through `uv run python scripts/validate_docs.py` and
  `uv run python -m unittest`.

## Basis

- [../completed/0024-profile-purpose-and-dataset-release-admission.md](../completed/0024-profile-purpose-and-dataset-release-admission.md)
  separated profile promotion from dataset release admission.
- [../completed/0026-dataset-release-coverage-and-admission-ratchet.md](../completed/0026-dataset-release-coverage-and-admission-ratchet.md)
  added release completeness gates and a deterministic release-candidate
  fixture that can pass release admission.
- [../deferred/0014-async-local-orchestration-with-durable-queues.md](../deferred/0014-async-local-orchestration-with-durable-queues.md)
  remains deferred because current release-candidate runs are small,
  synchronous, and cheap to rerun.
- [../deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md](../deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md)
  remains deferred because no second runtime consumer exists yet.
- [../tech-debt/README.md](../tech-debt/README.md) keeps semantic duplicate
  detection deferred until volume or curriculum-benchmark signals justify it.

## Why This Plan Now

The framework can now say that a concrete artifact set is releaseable for the
local MVP scope, but it does not yet produce a compact, durable release record
that locks the exact files behind that decision. Without a release pack, a later
reviewer has to manually connect `manifest.json`, `quality_report.json`,
`evaluation_report.json`, `profile_decision_report.json`, and
`dataset_release_report.json`, then trust that none of the files changed after
admission.

The next useful step is therefore not more scale infrastructure. It is a
reproducibility boundary: once release admission passes, produce a machine-
readable pack that records the release evidence and artifact hashes, and provide
a verifier that can fail fast if the directory drifts.

## Scope

- Add `dataset_release_pack_v1` as an optional artifact written only when
  explicitly requested.
- Include file name, byte count, and SHA-256 hash for release artifacts:
  `samples`, `rejections`, `manifest`, `quality_report`, `evaluation_report`,
  `profile_decision_report`, and `dataset_release_report`.
- Include sanitized release evidence:
  - dataset version;
  - run-profile id, generation mode, profile purpose, and config hash;
  - accepted and rejected counts;
  - held-out status;
  - profile-promotion status;
  - dataset-release status;
  - release-completeness status;
  - async-orchestration and semantic-duplicate decisions.
- Add a verification API that checks:
  - all referenced files exist;
  - recorded hashes and byte counts match current files;
  - manifest artifact references include the required release artifacts;
  - dataset version and profile metadata agree across manifest, evaluation,
    profile decision, dataset release, and release pack;
  - `decisions.dataset_release.status == "passed"`;
  - `release_completeness.decision.status == "passed"`.
- Add a standalone CLI script that verifies an output directory or a specific
  release-pack path without rerunning candidate generation.
- Attach `dataset_release_pack.json` to the manifest artifact map only when the
  pack is explicitly written. The final manifest must contain the
  `dataset_release_pack` file-name reference before the pack computes the
  manifest hash; the manifest does not store the pack hash, so this avoids a
  cyclic hash dependency.
- Preserve the default `uv run python main.py` behavior: no release report or
  release pack is written unless the relevant flags are provided.

## Out of Scope

- Implementing async orchestration, durable queues, cancellation, resumption, or
  per-role cost tracking from plan 0014.
- Implementing semantic duplicate detection, embeddings, vector stores, or
  near-duplicate admission gates from `TD-0002`.
- Introducing the AWM runtime boundary from plan 0025.
- Changing release completeness thresholds, held-out evaluation semantics,
  profile-promotion decisions, source governance, sandbox admission, or
  candidate acceptance behavior.
- Publishing packages, uploading artifacts, signing releases with external
  key-management systems, or creating a model-training pipeline.
- Treating release-pack verification as evidence of downstream model quality.

## Contract Design

Add `dataset_release_pack.json` with `schema_version:
dataset_release_pack_v1`.

Expected shape:

```json
{
  "schema_version": "dataset_release_pack_v1",
  "dataset_version": "dataset_foundation_release_candidate",
  "release_id": "dataset_foundation_release_candidate:sha256:...",
  "profile": {
    "schema_version": "run_profile_v1",
    "profile_id": "foundation_release_candidate",
    "generation_mode": "foundation_fixture",
    "profile_purpose": "release_candidate",
    "config_hash": "sha256:..."
  },
  "inputs": {
    "manifest_path": "manifest.json",
    "dataset_release_report_path": "dataset_release_report.json"
  },
  "artifacts": {
    "manifest": {
      "path": "manifest.json",
      "sha256": "sha256:...",
      "byte_count": 1234
    },
    "samples": {
      "path": "samples.jsonl",
      "sha256": "sha256:...",
      "byte_count": 5678
    },
    "rejections": {
      "path": "rejections.jsonl",
      "sha256": "sha256:...",
      "byte_count": 0
    },
    "quality_report": {
      "path": "quality_report.json",
      "sha256": "sha256:...",
      "byte_count": 1234
    },
    "evaluation_report": {
      "path": "evaluation_report.json",
      "sha256": "sha256:...",
      "byte_count": 1234
    },
    "profile_decision_report": {
      "path": "profile_decision_report.json",
      "sha256": "sha256:...",
      "byte_count": 1234
    },
    "dataset_release_report": {
      "path": "dataset_release_report.json",
      "sha256": "sha256:...",
      "byte_count": 1234
    }
  },
  "evidence": {
    "accepted": 6,
    "rejected": 1,
    "heldout_status": "passed",
    "profile_promotion_status": "passed",
    "dataset_release_status": "passed",
    "release_completeness_status": "passed",
    "async_orchestration_status": "defer",
    "semantic_duplicate_detection_status": "defer"
  },
  "verification": {
    "status": "passed",
    "reasons": [
      "all required artifacts are present",
      "artifact hashes are recorded",
      "dataset release admission passed"
    ]
  }
}
```

`release_id` must be deterministic from the dataset version and artifact hashes,
for example:

```text
{dataset_version}:sha256:{hash_of_sorted_artifact_hashes}
```

Allowed `verification.status` values:

- `passed`: every required file exists, hashes are recorded, and release
  evidence is internally consistent.
- `failed`: the pack was buildable or readable, but verification found drift or
  inconsistent release evidence.
- `insufficient_evidence`: required release artifacts or machine-readable fields
  are absent or malformed.

The release pack must not store raw sample contents, raw source payloads, local
profile paths, provider prompts, provider payloads, headers, API keys, or
arbitrary profile JSON. It may read artifact bytes only to compute hashes and
byte counts.

## File Map

- Create `synthesis/release_pack.py` for release-pack construction,
  verification, hash helpers, input loading, and writing.
- Modify `synthesis/contracts.py` to validate `dataset_release_pack_v1` and the
  optional `dataset_release_pack` manifest artifact key.
- Modify `synthesis/datasets.py` only if manifest artifact attachment requires
  a helper for post-run artifact additions before release-pack hashing.
- Modify `main.py` to add `--write-dataset-release-pack` after existing dataset
  release report generation.
- Create `scripts/verify_dataset_release.py` as a standalone verification CLI.
- Add `tests/test_release_pack.py` for pack construction, hash locking,
  verification, drift detection, and contract validation.
- Extend `tests/test_cli.py` for opt-in release-pack generation and default-path
  stability.
- Update [../../DATA.md](../../DATA.md), [../../ROADMAP.md](../../ROADMAP.md),
  and [../../PLANS.md](../../PLANS.md).

## Implementation Tasks

### Task 1: Add Release-Pack Contract Tests

- [x] Add `tests/test_release_pack.py`.
- [x] Add a failing test that builds a release pack from a minimal temporary
  directory containing manifest, samples, rejections, quality report,
  evaluation report, profile decision report, and passed dataset release report.
- [x] Assert that the pack includes `schema_version:
  dataset_release_pack_v1`, deterministic `release_id`, artifact entries with
  `path`, `sha256`, and `byte_count`, and `verification.status == "passed"`.
- [x] Add a failing contract test in `tests/test_contracts.py` or
  `tests/test_release_pack.py` that rejects unsupported verification statuses,
  malformed hash strings, negative byte counts, missing artifact paths, and
  non-mapping evidence fields.

### Task 2: Implement Release-Pack Builder

- [x] Create `synthesis.release_pack`.
- [x] Add a small immutable artifact record with `path`, `sha256`, and
  `byte_count`.
- [x] Implement SHA-256 hashing as `sha256:<64 lowercase hex chars>`.
- [x] Load and validate existing manifest and dataset release report inputs.
- [x] Build sanitized profile and evidence summaries from existing report
  fields only.
- [x] Compute deterministic `release_id` from sorted artifact keys and hashes.
- [x] Validate the pack through `validate_dataset_release_pack_record` before
  returning it.

### Task 3: Add Pack Verification

- [x] Add `verify_dataset_release_pack(pack_path: Path) -> dict[str, object]`.
- [x] Recompute file hashes and byte counts relative to the pack directory.
- [x] Return `failed` when a referenced file is missing, hash differs, byte
  count differs, dataset/profile metadata disagrees, or release evidence no
  longer says `passed`.
- [x] Return `insufficient_evidence` when pack fields or referenced JSON
  artifacts are absent or malformed.
- [x] Add tests for successful verification, missing artifact, modified
  artifact content, dataset-version mismatch, and non-passed dataset release
  evidence.

### Task 4: Wire CLI Opt-In Generation

- [x] Add `--write-dataset-release-pack` to `main.py`.
- [x] Require `--write-dataset-release-report` when
  `--write-dataset-release-pack` is supplied; fail with a clear CLI error if
  the release report is not being written.
- [x] Attach the `dataset_release_pack` file-name reference to `manifest.json`
  before computing the release-pack hash records.
- [x] Write `dataset_release_pack.json` only after
  `dataset_release_report.json` exists and has `dataset_release.status ==
  "passed"`.
- [x] Attach `dataset_release_pack` to the manifest artifact map only when the
  pack is written.
- [x] Preserve default behavior: `uv run python main.py` writes no release pack.

### Task 5: Add Standalone Verification Script

- [x] Create `scripts/verify_dataset_release.py`.
- [x] Accept either `--output-dir artifacts/foundation-release-candidate` or
  `--release-pack artifacts/foundation-release-candidate/dataset_release_pack.json`.
- [x] Print a compact JSON verification result to stdout.
- [x] Exit `0` for `verification.status == "passed"` and `1` otherwise.
- [x] Add tests or CLI coverage proving the script detects drift after an
  artifact file changes.

### Task 6: End-to-End Fixture Coverage

- [x] Extend `tests/test_cli.py` with a release-candidate command:

```bash
uv run python main.py \
  --run-profile tests/fixtures/run_profiles/foundation-release-candidate.json \
  --write-evaluation-report \
  --write-profile-decision-report \
  --write-dataset-release-report \
  --write-dataset-release-pack \
  --output-dir artifacts/foundation-release-candidate
```

- [x] Assert that `dataset_release_pack.json` exists, manifest artifacts include
  `dataset_release_pack`, and standalone verification returns `passed`.
- [x] Add a CLI characterization test showing the foundation smoke path remains
  unchanged when the new flag is absent.

### Task 7: Docs and Validation

- [x] Update [../../DATA.md](../../DATA.md) with the release-pack contract,
  verification statuses, hash-locking behavior, and redaction constraints.
- [x] Update [../../ROADMAP.md](../../ROADMAP.md) to place release-pack
  reproducibility before async orchestration.
- [x] Update [../../PLANS.md](../../PLANS.md) when this plan is completed and
  moved to `../completed/`.
- [x] Run `uv run python scripts/validate_docs.py`.
- [x] Run `uv run python -m unittest`.
- [x] Run the release-candidate command from Task 6 and verify the pack with
  `uv run python scripts/verify_dataset_release.py --output-dir
  artifacts/foundation-release-candidate`.

## Validation

```bash
uv run python scripts/validate_docs.py
uv run python -m unittest
uv run python main.py --run-profile tests/fixtures/run_profiles/foundation-release-candidate.json --write-evaluation-report --write-profile-decision-report --write-dataset-release-report --write-dataset-release-pack --output-dir artifacts/foundation-release-candidate
uv run python scripts/verify_dataset_release.py --output-dir artifacts/foundation-release-candidate
```

Expected outcomes:

- The release-candidate run writes `dataset_release_report.json` with
  `decisions.dataset_release.status == "passed"`.
- The same run writes `dataset_release_pack.json` only when
  `--write-dataset-release-pack` is supplied.
- The release pack records hashes and byte counts for every required release
  artifact.
- Standalone verification returns `verification.status == "passed"` before file
  drift and returns `failed` or `insufficient_evidence` after drift.
- The default `uv run python main.py` path still omits evaluation, profile
  decision, dataset release, and release-pack artifacts.

## Acceptance Criteria

- `dataset_release_pack_v1` is contract-validated.
- A release pack can be created only from a passed dataset release report.
- A release pack locks required release artifacts by file name, SHA-256 hash,
  and byte count.
- Verification can be run later without rerunning candidate generation.
- Verification fails when artifact contents drift after pack creation.
- Manifest artifact references include `dataset_release_pack` only for opt-in
  release-pack runs.
- No raw payloads, prompts, credentials, or arbitrary profile JSON are written
  to the release pack.
- Async orchestration, semantic duplicate detection, and AWM runtime extraction
  remain deferred unless their existing triggers are met.
- Documentation validation and the full unit suite pass.

## Risks

- Hashing large future artifacts can add overhead. Keep this synchronous and
  local for now; revisit streaming or chunked verification only when artifacts
  become large enough to matter.
- The release pack can be confused with model-quality proof. Keep the wording
  strict: it proves artifact integrity and release-admission consistency, not
  downstream training gain.
- Manifest mutation after pack creation can create a hash-ordering trap. Update
  the manifest artifact map with the `dataset_release_pack` file-name reference
  before computing release-pack hashes, then make tests cover the final manifest
  hash behavior explicitly.
- Verification can accidentally expose raw artifact content in errors. Return
  file names, keys, hashes, byte counts, and failure classes only.
