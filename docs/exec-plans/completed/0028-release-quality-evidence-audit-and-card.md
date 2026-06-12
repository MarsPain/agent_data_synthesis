# Plan 0028: Release Quality Evidence Audit and Dataset Card

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

## Status

Completed on 2026-06-12.

## Goal

Add an opt-in release quality evidence layer that makes a release-candidate
artifact set honest about diversity, duplicate pressure, and known limitations
without implementing full semantic duplicate detection or changing default
candidate admission.

## Architecture

This plan adds a narrow post-release-report audit layer after
`dataset_release_report_v1` and before optional human-facing release
documentation. The audit reads existing sanitized artifacts plus local
`samples.jsonl` identifiers and structured task metadata, then emits a compact
`release_quality_audit.json` with machine-readable risk signals.

The audit is evidence, not a new default quality gate. It does not rerun
generation, does not call embeddings or remote models, does not change exact
duplicate admission, and does not block release by default. Dataset release
admission continues to be owned by `dataset_release_report_v1`; the new report
adds reviewable context for small release candidates where basic quality gates
can pass while training-signal diversity remains thin.

The plan also adds a lightweight `dataset_release_card.md` that summarizes what
the release is and is not. The card is intended for humans reviewing a local
MVP release pack. It must say explicitly that release-pack verification proves
artifact integrity and release-admission consistency, not downstream model
quality or transfer gain.

## Tech Stack

- Python standard library: `dataclasses`, `json`, `pathlib`, `hashlib`,
  `re`, `statistics`, and `unittest`.
- Existing modules: `synthesis.contracts`, `synthesis.dataset_release`,
  `synthesis.datasets`, `synthesis.profile_decisions`,
  `synthesis.release_pack`, and `main.py`.
- New module: `synthesis.release_quality`.
- Verification through `uv run python scripts/validate_docs.py` and
  `uv run python -m unittest`.

## Basis

- [../completed/0024-profile-purpose-and-dataset-release-admission.md](../completed/0024-profile-purpose-and-dataset-release-admission.md)
  separated profile promotion from concrete dataset release admission.
- [../completed/0026-dataset-release-coverage-and-admission-ratchet.md](../completed/0026-dataset-release-coverage-and-admission-ratchet.md)
  added release completeness gates so tiny release-candidate smoke runs cannot
  pass solely on profile and held-out decisions.
- [../completed/0027-dataset-release-pack-and-reproducibility-verification.md](../completed/0027-dataset-release-pack-and-reproducibility-verification.md)
  added hash-locked release packs and offline verification, but intentionally
  did not claim downstream model quality.
- [../tech-debt/README.md](../tech-debt/README.md) keeps `TD-0002` semantic
  duplicate detection unresolved until dataset volume or curriculum-benchmark
  evidence justifies embeddings, vector stores, or near-duplicate admission
  gates.
- [../deferred/0014-async-local-orchestration-with-durable-queues.md](../deferred/0014-async-local-orchestration-with-durable-queues.md)
  remains deferred because current release-candidate runs are small,
  synchronous, and cheap to rerun.
- [../deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md](../deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md)
  remains deferred because no second runtime consumer exists yet.

## Why This Plan Now

The framework now has enough release machinery to produce a local MVP artifact
set and prove the files have not drifted. The remaining risk is interpretive:
reviewers can mistake "passed basic release gates" for "diverse enough to be a
meaningful training dataset." Existing filters catch executable failures,
verifier failures, logical-support failures, schema failures, source-policy
failures, release incompleteness, and exact duplicates. They do not clearly
summarize whether a small release is dominated by one task family or whether
near-duplicate pressure deserves human review.

Full semantic duplicate detection is still premature. The next useful step is
therefore an audit report: expose deterministic risk signals from existing
artifacts, make limitations visible in a release card, and leave hard admission
behavior unchanged until larger runs or curriculum metrics justify `TD-0002`.

## Scope

- Add `release_quality_audit_v1` as an optional artifact written only when
  explicitly requested.
- Read existing artifacts:
  - `manifest.json`;
  - `quality_report.json`;
  - `evaluation_report.json`;
  - `profile_decision_report.json`;
  - `dataset_release_report.json`;
  - `samples.jsonl`;
  - `rejections.jsonl`.
- Compute deterministic audit evidence:
  - accepted/rejected counts;
  - exact duplicate count and rate from quality/profile reports;
  - largest accepted task-type share;
  - largest accepted tool-combination share;
  - number of accepted task types and tool combinations;
  - release completeness status;
  - semantic duplicate decision status from the profile decision report;
  - small-release warning when accepted count is near the current release
    minimum;
  - reviewable duplicate-family risk groups using sample ids and hashed family
    keys, not raw instructions.
- Add an audit decision with statuses:
  - `clear`: no configured risk threshold is triggered;
  - `watch`: release admission can remain valid, but reviewers should inspect
    concentration or duplicate-family signals;
  - `insufficient_evidence`: required audit inputs are missing or malformed;
  - `blocked`: profile decisions say semantic duplicate detection has activated
    and must be implemented before release use.
- Add `dataset_release_card.md` as an optional human-readable artifact that
  summarizes:
  - dataset version;
  - profile id and profile purpose;
  - release status;
  - release pack verification status when available;
  - sample/rejection counts;
  - held-out and profile-promotion status;
  - release completeness status;
  - release quality audit status;
  - known limitations and non-claims.
- Attach `release_quality_audit` and `dataset_release_card` to the manifest only
  when those artifacts are explicitly written.
- Preserve the default `uv run python main.py` behavior: no audit or card is
  written unless the relevant flags are provided.

## Out of Scope

- Implementing full semantic duplicate detection, embeddings, vector stores,
  clustering, or near-duplicate admission gates from `TD-0002`.
- Blocking dataset release admission by default when the audit returns `watch`.
- Changing candidate generation, candidate acceptance, exact duplicate
  signatures, release completeness thresholds, held-out evaluation semantics,
  profile-promotion decisions, or release-pack verification semantics.
- Implementing async orchestration, durable queues, cancellation, resumption, or
  per-role cost tracking from plan 0014.
- Introducing the AWM runtime boundary from plan 0025.
- Claiming downstream model improvement, transfer gain, or training utility
  from the audit or card.

## Contract Design

Add `release_quality_audit.json` with
`schema_version: release_quality_audit_v1`.

Expected shape:

```json
{
  "schema_version": "release_quality_audit_v1",
  "dataset_version": "dataset_foundation_release_candidate",
  "profile": {
    "schema_version": "run_profile_v1",
    "profile_id": "foundation_release_candidate",
    "generation_mode": "foundation_fixture",
    "profile_purpose": "release_candidate",
    "config_hash": "sha256:..."
  },
  "inputs": {
    "manifest_path": "manifest.json",
    "quality_report_path": "quality_report.json",
    "evaluation_report_path": "evaluation_report.json",
    "profile_decision_report_path": "profile_decision_report.json",
    "dataset_release_report_path": "dataset_release_report.json",
    "samples_path": "samples.jsonl",
    "rejections_path": "rejections.jsonl"
  },
  "observed": {
    "accepted": 6,
    "rejected": 1,
    "exact_duplicate_count": 0,
    "exact_duplicate_rate": 0.0,
    "task_type_count": 3,
    "tool_combination_count": 2,
    "largest_task_type_share": 0.5,
    "largest_tool_combination_share": 0.6666666667,
    "release_completeness_status": "passed",
    "semantic_duplicate_detection_status": "defer"
  },
  "thresholds": {
    "small_release_watch_accepted_samples": 8,
    "max_largest_task_type_share": 0.75,
    "max_largest_tool_combination_share": 0.8,
    "max_exact_duplicate_rate": 0.0,
    "max_duplicate_family_size": 2
  },
  "duplicate_family_risks": [
    {
      "family_key": "sha256:...",
      "risk_kind": "same_task_type_and_tool_combination",
      "risk_level": "watch",
      "sample_ids": ["sample_a", "sample_b", "sample_c"],
      "sample_count": 3,
      "reason": "3 accepted samples share the same task type and tool combination"
    }
  ],
  "decision": {
    "status": "watch",
    "reasons": [
      "accepted 6 is below small_release_watch_accepted_samples 8",
      "duplicate family risk groups require review"
    ],
    "triggered_by": ["small_release_size", "duplicate_family_risk"]
  }
}
```

`duplicate_family_risks` must not include raw task instructions, raw
trajectory arguments, contact emails, local profile paths, source paths, raw
source payloads, prompts, provider payloads, headers, API keys, arbitrary
profile JSON, or host paths. It may include accepted `sample_id` values,
deterministic family hashes, counts, and reason codes.

Family keys should be deterministic from structured fields already present in
accepted samples, for example:

```text
task_type | ordered_tool_names | verifier_type | difficulty_level
```

The first implementation must keep this intentionally simple. It is a review
signal for concentration and near-duplicate risk, not a semantic equivalence
classifier.

`dataset_release_card.md` is human-readable and should use stable headings:

```markdown
# Dataset Release Card

## Identity
## Release Decision
## Artifact Integrity
## Quality Evidence
## Coverage and Diversity
## Known Limitations
## Non-Claims
```

The card must not be used as a machine contract. Machine consumers should read
`release_quality_audit.json`, `dataset_release_report.json`, and
`dataset_release_pack.json`.

## File Map

- Create `synthesis/release_quality.py` for audit construction, family-key
  hashing, duplicate-family risk summarization, card rendering, and artifact
  writing.
- Modify `synthesis/contracts.py` to validate
  `release_quality_audit_v1` and allow optional manifest artifact keys
  `release_quality_audit` and `dataset_release_card`.
- Modify `synthesis/datasets.py` to add manifest attachment helpers for
  `release_quality_audit` and `dataset_release_card`.
- Modify `main.py` to add `--write-release-quality-audit` and
  `--write-dataset-release-card`.
- Add `tests/test_release_quality.py` for audit construction, contract
  validation, redaction, duplicate-family risk grouping, and card rendering.
- Extend `tests/test_cli.py` for opt-in audit/card generation and default-path
  stability.
- Update [../../DATA.md](../../DATA.md), [../../ROADMAP.md](../../ROADMAP.md),
  [../../PLANS.md](../../PLANS.md), and this active plan lifecycle state.

## Implementation Tasks

### Task 1: Add Release Quality Audit Contract Tests

- [x] Add `tests/test_release_quality.py`.
- [x] Add a failing test that builds a minimal release quality audit from
  temporary manifest, samples, rejections, quality report, evaluation report,
  profile decision report, and dataset release report artifacts.
- [x] Assert that the audit includes `schema_version:
  release_quality_audit_v1`, sanitized profile metadata, input artifact names,
  observed counts, thresholds, duplicate-family risks, and
  `decision.status == "watch"` when small-release or concentration thresholds
  are triggered.
- [x] Add contract tests rejecting unsupported decision statuses, malformed hash
  strings, negative counts, non-list duplicate-family sample ids, missing input
  artifact names, and raw secret-like keys.
- [x] Add a redaction test proving the exported audit does not include raw
  task instructions, local paths, source paths, prompts, headers, API keys, or
  arbitrary profile JSON.

### Task 2: Implement the Audit Builder

- [x] Create `synthesis.release_quality`.
- [x] Add a small immutable threshold record with defaults:
  - `small_release_watch_accepted_samples = 8`;
  - `max_largest_task_type_share = 0.75`;
  - `max_largest_tool_combination_share = 0.8`;
  - `max_exact_duplicate_rate = 0.0`;
  - `max_duplicate_family_size = 2`.
- [x] Load required JSON artifacts using existing file names from the manifest
  whenever possible.
- [x] Parse `samples.jsonl` only to extract sample ids and structured task/tool
  metadata needed for family keys.
- [x] Build deterministic family keys from task type, ordered tool names,
  verifier type, and difficulty level; hash the joined family string as
  `sha256:<64 lowercase hex chars>`.
- [x] Compute observed accepted/rejected counts, duplicate pressure,
  concentration shares, release completeness status, and semantic duplicate
  decision status.
- [x] Return `blocked` when profile decisions say
  `semantic_duplicate_detection.status == "activate"`.
- [x] Return `watch` for small-release, exact-duplicate, concentration, or
  duplicate-family threshold triggers.
- [x] Return `clear` when all required inputs are present and no threshold
  triggers.
- [x] Return `insufficient_evidence` when required artifacts are absent or
  malformed.
- [x] Validate the audit with `validate_release_quality_audit_record` before
  returning it.

### Task 3: Add Manifest and CLI Integration

- [x] Add `release_quality_audit` and `dataset_release_card` to allowed
  manifest artifact keys.
- [x] Add `attach_release_quality_audit_to_manifest` and
  `attach_dataset_release_card_to_manifest` helpers in `synthesis.datasets`.
- [x] Add `--write-release-quality-audit` to `main.py`.
- [x] Require `--write-dataset-release-report` when
  `--write-release-quality-audit` is supplied; fail with a clear CLI error if
  the release report is not being written.
- [x] Write `release_quality_audit.json` after
  `dataset_release_report.json` exists.
- [x] Attach `release_quality_audit` to the manifest only when the audit is
  written.
- [x] Preserve default behavior: `uv run python main.py` writes no release
  quality audit and no dataset release card.

### Task 4: Add Dataset Release Card Rendering

- [x] Implement `render_dataset_release_card(...) -> str` in
  `synthesis.release_quality`.
- [x] Add `--write-dataset-release-card` to `main.py`.
- [x] Require `--write-dataset-release-report` when the card flag is supplied.
- [x] If `release_quality_audit.json` exists, include its status and reasons in
  the card. If it is absent, include a short "not generated" line.
- [x] If `dataset_release_pack.json` exists, include its `release_id` and
  verification status. If it is absent, include a short "not generated" line.
- [x] Always include a `Non-Claims` section stating that release admission,
  audit status, and pack verification do not prove downstream model quality,
  transfer gain, or training utility.
- [x] Attach `dataset_release_card` to the manifest only when the card is
  written.
- [x] Add tests proving the card has stable headings, includes the required
  release evidence, and does not leak raw sample contents or profile paths.

### Task 5: Add End-to-End Fixture Coverage

- [x] Extend `tests/test_cli.py` with a release-candidate command:

```bash
uv run python main.py \
  --run-profile tests/fixtures/run_profiles/foundation-release-candidate.json \
  --write-evaluation-report \
  --write-profile-decision-report \
  --write-dataset-release-report \
  --write-release-quality-audit \
  --write-dataset-release-card \
  --output-dir artifacts/foundation-release-candidate-quality-audit
```

- [x] Assert that `release_quality_audit.json` and
  `dataset_release_card.md` exist.
- [x] Assert that `manifest.json` references `release_quality_audit` and
  `dataset_release_card`.
- [x] Assert that the audit decision is `clear` or `watch`, never `blocked`,
  for the deterministic release-candidate fixture unless the profile decision
  report intentionally activates semantic duplicate detection.
- [x] Add a CLI characterization test showing the foundation smoke path remains
  unchanged when the new flags are absent.

### Task 6: Docs and Validation

- [x] Update [../../DATA.md](../../DATA.md) with the release quality audit
  contract, thresholds, decision statuses, duplicate-family risk redaction
  rules, and dataset release card purpose.
- [x] Update [../../ROADMAP.md](../../ROADMAP.md) to place release quality
  evidence before async orchestration.
- [x] Keep `TD-0002` in [../tech-debt/README.md](../tech-debt/README.md) open;
  this plan adds evidence, not full semantic duplicate detection.
- [x] Run `uv run python scripts/validate_docs.py`.
- [x] Run `uv run python -m unittest`.
- [x] Run the end-to-end release-candidate command from Task 5.

## Validation

```bash
uv run python scripts/validate_docs.py
uv run python -m unittest
uv run python main.py --run-profile tests/fixtures/run_profiles/foundation-release-candidate.json --write-evaluation-report --write-profile-decision-report --write-dataset-release-report --write-release-quality-audit --write-dataset-release-card --output-dir artifacts/foundation-release-candidate-quality-audit
```

Expected outcomes:

- Default `uv run python main.py` output remains unchanged.
- The release-candidate audit command writes `release_quality_audit.json`.
- The release-candidate card command writes `dataset_release_card.md`.
- The manifest references the audit and card only when those artifacts are
  explicitly requested.
- Audit output uses sample ids, counts, hashes, statuses, and reason codes, not
  raw instructions, raw trajectory arguments, local paths, source payloads,
  prompts, provider payloads, headers, API keys, or arbitrary profile JSON.
- `TD-0002` remains unresolved and explicitly separate from this audit.

## Acceptance Criteria

- `release_quality_audit_v1` is contract-validated.
- The audit can be generated from an existing release-candidate artifact set
  without rerunning candidate generation.
- The audit exposes exact duplicate pressure, concentration pressure,
  duplicate-family risk groups, release completeness status, and semantic
  duplicate decision status.
- `watch` is review evidence, not a default release blocker.
- `blocked` is returned only when existing profile decisions activate semantic
  duplicate detection.
- `dataset_release_card.md` summarizes release evidence and non-claims for
  human review.
- No raw sample contents, raw task instructions, local profile paths, source
  paths, source payloads, prompts, provider payloads, headers, API keys,
  credentials, or arbitrary profile JSON are written to audit or card artifacts.
- Async orchestration, semantic duplicate admission, and AWM runtime extraction
  remain deferred unless their existing triggers are met.
- Documentation validation and the full unit suite pass.

## Risks

- The audit can be mistaken for semantic duplicate detection. Keep naming and
  docs precise: it is a deterministic risk audit, not semantic equivalence
  classification.
- A `watch` result can be overinterpreted as release failure. Keep
  `dataset_release_report_v1` as the release admission owner unless a later plan
  explicitly changes admission semantics.
- Family-key heuristics can miss real paraphrases. That is acceptable for this
  stage because the goal is evidence visibility, not full duplicate blocking.
- Human-readable card text can drift from machine contracts. Generate it from
  the same loaded artifacts and keep machine consumers pointed at JSON reports.
