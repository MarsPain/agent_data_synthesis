# Plan 0020: Profile Decision Gates and Benchmark Reporting

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

## Status

Planned on 2026-05-30. Completed on 2026-05-30.

## Goal

Convert synchronous run-profile artifacts into an explicit benchmark decision
report that says whether to keep async orchestration deferred, activate
semantic duplicate detection, and accept the current profile run as meeting a
configured MVP quality floor.

## Architecture

This plan adds a small reporting boundary above existing dataset artifacts. It
does not change candidate generation, candidate processing, source governance,
profile attribution, quality slicing, or default synchronous pipeline behavior.
The decision report reads `manifest.json`, `quality_report.json`, and optional
`parent_comparison.json`, applies deterministic thresholds, and writes a
sanitized `profile_decision_report.json` plus an optional manifest artifact
reference when invoked from the CLI.

## Tech Stack

- Python standard library: `argparse`, `dataclasses`, `json`, `pathlib`,
  `time`, and `unittest`.
- Existing artifacts from `synthesis.datasets` and quality reports from
  `synthesis.quality`.
- Existing validation through `scripts/validate_docs.py` and
  `uv run python -m unittest`.

---

## Basis

- [../../PLANS.md](../../PLANS.md) previously had no active successor after
  [../completed/0019-profile-attributed-quality-and-comparison.md](../completed/0019-profile-attributed-quality-and-comparison.md).
- [../deferred/0014-async-local-orchestration-with-durable-queues.md](../deferred/0014-async-local-orchestration-with-durable-queues.md)
  remains deferred until single runs exceed about 10 minutes or 100+
  candidates.
- [../tech-debt/README.md](../tech-debt/README.md) keeps `TD-0002` semantic
  duplicate detection unresolved until dataset volume or curriculum-benchmark
  signals justify implementation.
- Plans 0017, 0018, and 0019 made synchronous profile runs configurable,
  source-governed, attributable at record level, and sliceable in quality
  reports.
- The deterministic 25-candidate scale probe remains below the async trigger,
  but the project has no executable report that preserves that decision
  rationale as an artifact.

## Scope

- Add a deterministic profile decision report contract with:
  - input artifact paths and dataset/profile identity;
  - observed candidate counts, success and executable rates, rejection counts,
    exact-duplicate rate, source/infrastructure rejection rates, optional runtime
    seconds, and profile slice presence;
  - thresholds used for the decision;
  - decisions for `async_orchestration`, `semantic_duplicate_detection`, and
    `mvp_quality_floor`;
  - clear `activate`, `defer`, `passed`, `failed`, or `insufficient_evidence`
    statuses with machine-readable reasons.
- Add `synthesis.profile_decisions` as the domain-specific report builder.
- Add `scripts/profile_decision_report.py` as a thin CLI over the report builder.
- Add a `main.py` opt-in flag that writes the decision report after a profile
  run completes, without changing default `uv run python main.py` artifacts.
- Add manifest artifact plumbing only when a decision report is requested.
- Keep the report sanitized: no raw profile files, local source paths, source
  payloads, contact emails, prompts, headers, API keys, or arbitrary profile
  JSON.
- Update canonical docs and plan indexes for the new active plan and planned
  report contract.

## Out of Scope

- Implementing async orchestration, durable queues, cancellation, resumption, or
  per-role async cost tracking from plan 0014.
- Implementing semantic duplicate detection from `TD-0002`.
- Adding embeddings, local models, vector stores, or LLM-as-judge duplicate
  checks.
- Adding dashboards, web services, REST APIs, browser automation, or monitoring
  exporters.
- Changing candidate acceptance behavior, duplicate gate semantics, quality
  report schema, source governance, sandbox admission, or MCP adapter execution.
- Treating a decision report as proof of downstream model improvement; held-out
  task evaluation remains future work.

## Decision Contract

`profile_decision_report.json` uses `schema_version:
profile_decision_report_v1`.

```json
{
  "schema_version": "profile_decision_report_v1",
  "dataset_version": "dataset_foundation_scale_probe_25",
  "profile": {
    "schema_version": "run_profile_v1",
    "profile_id": "foundation_scale_probe_25",
    "generation_mode": "deterministic_scale_probe",
    "target_candidate_count": 25,
    "config_hash": "sha256:..."
  },
  "inputs": {
    "manifest_path": "manifest.json",
    "quality_report_path": "quality_report.json",
    "parent_comparison_path": null
  },
  "observed": {
    "total_candidates": 25,
    "accepted": 14,
    "rejected": 11,
    "success_rate": 0.56,
    "executable_rate": 1.0,
    "exact_duplicate_count": 3,
    "exact_duplicate_rate": 0.12,
    "infrastructure_rejection_count": 0,
    "source_policy_rejection_count": 0,
    "runtime_seconds": null,
    "profile_slice_count": 3
  },
  "thresholds": {
    "async_candidate_count": 100,
    "async_runtime_seconds": 600,
    "semantic_duplicate_min_candidates": 100,
    "semantic_duplicate_exact_rate": 0.1,
    "mvp_min_success_rate": 0.5,
    "mvp_min_executable_rate": 0.8,
    "mvp_max_infrastructure_rejection_rate": 0.0,
    "mvp_max_source_policy_rejection_rate": 0.0
  },
  "decisions": {
    "async_orchestration": {
      "status": "defer",
      "reasons": [
        "total_candidates 25 is below async_candidate_count 100",
        "runtime_seconds is unavailable"
      ],
      "triggered_by": []
    },
    "semantic_duplicate_detection": {
      "status": "defer",
      "reasons": [
        "total_candidates 25 is below semantic_duplicate_min_candidates 100"
      ],
      "triggered_by": []
    },
    "mvp_quality_floor": {
      "status": "passed",
      "reasons": [
        "success_rate 0.56 is at or above mvp_min_success_rate 0.5",
        "executable_rate 1.0 is at or above mvp_min_executable_rate 0.8"
      ],
      "triggered_by": [
        "success_rate",
        "executable_rate"
      ]
    }
  }
}
```

Decision status rules:

- `async_orchestration.status` is `activate` when
  `total_candidates >= async_candidate_count` or
  `runtime_seconds >= async_runtime_seconds`. It is `defer` when both available
  signals are below threshold. If runtime is unavailable and candidate count is
  below threshold, the report still returns `defer` and records the missing
  runtime as a reason because candidate-count evidence is sufficient to avoid
  activating 0014.
- `semantic_duplicate_detection.status` is `activate` only when
  `total_candidates >= semantic_duplicate_min_candidates` and
  `exact_duplicate_rate >= semantic_duplicate_exact_rate`. It is `defer` when
  volume is below threshold even if the exact duplicate rate is high.
- `mvp_quality_floor.status` is `passed` when success and executable rates meet
  thresholds and infrastructure/source-policy rejection rates do not exceed
  their caps. It is `failed` otherwise. If a required rate is missing or
  malformed, it is `insufficient_evidence`.

## File Map

- Create `synthesis/profile_decisions.py`:
  - load and validate report inputs from mappings or artifact paths;
  - calculate observed metrics and deterministic decisions;
  - serialize a sanitized report mapping.
- Create `scripts/profile_decision_report.py`:
  - parse CLI arguments;
  - call `synthesis.profile_decisions`;
  - write `profile_decision_report.json`.
- Modify `synthesis/datasets.py`:
  - optionally reference `profile_decision_report` in `manifest.artifacts`
    when the pipeline writes one.
- Modify `main.py`:
  - add `--write-profile-decision-report`;
  - record elapsed wall time for a requested profile decision report;
  - write the report after `run_foundation_pipeline()` completes.
- Modify `synthesis/contracts.py`:
  - allow `manifest.artifacts.profile_decision_report`;
  - add `validate_profile_decision_report_record()` for the report builder and
    CLI writer.
- Add `tests/test_profile_decisions.py`:
  - cover report construction, threshold decisions, sanitization, and CLI
    writing.
- Modify `tests/test_cli.py`:
  - cover opt-in CLI report generation for a deterministic profile run.
- Update docs:
  - [../../DATA.md](../../DATA.md) with the planned report contract after
    implementation;
  - [../../BACKEND.md](../../BACKEND.md) with the report step in the profile
    workflow after implementation;
  - [../../ROADMAP.md](../../ROADMAP.md) to position decision reporting before
    async orchestration;
  - [../../PLANS.md](../../PLANS.md), [README.md](README.md),
    [../../README.md](../../README.md), and
    [../../../README.md](../../../README.md) indexes as needed.

## Implementation Tasks

### Task 1: Characterize Current Profile Evidence

- [x] Add `tests/test_profile_decisions.py` with a fixture helper that loads a
  scale-probe `manifest` and `quality_report` mapping from the existing
  pipeline output shape.
- [x] Write a failing test named
  `test_scale_probe_decision_report_defers_async_and_semantic_duplicates`.
- [x] Assert the report builder returns:
  - `schema_version == "profile_decision_report_v1"`;
  - `observed.total_candidates == 25`;
  - `observed.accepted == 14`;
  - `observed.rejected == 11`;
  - `observed.exact_duplicate_count == 3`;
  - `decisions.async_orchestration.status == "defer"`;
  - `decisions.semantic_duplicate_detection.status == "defer"`;
  - `decisions.mvp_quality_floor.status == "passed"`.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_profile_decisions
  ```

  Expected result before implementation: import or report-builder failure.

### Task 2: Implement the Report Builder

- [x] Create `synthesis/profile_decisions.py` with:
  - `DecisionThresholds`;
  - `ProfileDecisionInputs`;
  - `build_profile_decision_report()`;
  - `load_profile_decision_inputs()`;
  - `write_profile_decision_report()`.
- [x] Add `validate_profile_decision_report_record()` to
  `synthesis/contracts.py` and call it before writing the report.
- [x] Derive `total_candidates` from `quality_report["counts"]["total"]` and
  cross-check it against `manifest.accepted_count + manifest.rejected_count`
  when both are present.
- [x] Derive exact duplicate count from
  `quality_report["rejection_causes"]["quality_duplicate"]`, defaulting to `0`.
- [x] Derive profile slice count by counting slice keys that start with:
  - `run_profile_id:`;
  - `generation_mode:`;
  - `run_profile_schema_version:`.
- [x] Return deterministic decision reasons that include the observed value and
  the threshold value.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_profile_decisions
  ```

  Expected result: report-builder tests pass.

### Task 3: Add Threshold and Insufficient-Evidence Coverage

- [x] Add tests for async activation when `total_candidates == 100`.
- [x] Add tests for async activation when `runtime_seconds == 600`.
- [x] Add tests for semantic duplicate activation when
  `total_candidates == 100` and `exact_duplicate_rate >= 0.1`.
- [x] Add tests proving semantic duplicate detection remains deferred when
  `total_candidates < 100`, even if exact duplicate rate is above threshold.
- [x] Add tests for `mvp_quality_floor.status == "failed"` when
  `success_rate < 0.5`, `executable_rate < 0.8`, infrastructure rejection rate
  exceeds `0.0`, or source-policy rejection rate exceeds `0.0`.
- [x] Add tests for `mvp_quality_floor.status == "insufficient_evidence"` when
  `quality_report.rates` omits a required rate.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_profile_decisions
  ```

  Expected result: all threshold tests pass.

### Task 4: Add Sanitized CLI Reporting

- [x] Create `scripts/profile_decision_report.py` with arguments:
  - `--manifest`;
  - `--quality-report`;
  - `--parent-comparison`;
  - `--runtime-seconds`;
  - `--output`;
  - threshold overrides matching `DecisionThresholds`.
- [x] Make default output path
  `{manifest.parent}/profile_decision_report.json` when `--output` is omitted.
- [x] Add a CLI test that writes a report from synthetic manifest and quality
  report files in a temp directory.
- [x] Assert the serialized report does not contain:
  - raw profile source paths;
  - `contacts-profile.json`;
  - contact emails;
  - `AGENT_DATA_API_KEY`;
  - `Authorization`.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_profile_decisions
  ```

  Expected result: CLI report tests pass.

### Task 5: Wire Opt-In Pipeline CLI Support

- [x] Add `--write-profile-decision-report` to `main.py`.
- [x] Measure elapsed wall time with `time.perf_counter()` only when the flag is
  enabled.
- [x] After `run_foundation_pipeline()` returns, call
  `write_profile_decision_report()` with:
  - `result.manifest_path`;
  - `result.quality_report_path`;
  - `result.parent_comparison_path`;
  - elapsed runtime seconds.
- [x] Print the report path in the completion message only when the report is
  written.
- [x] Keep default runs unchanged when the flag is not supplied.
- [x] Add a CLI test that runs:

  ```bash
  uv run python main.py \
    --run-profile tests/fixtures/run_profiles/foundation-scale-probe-25.json \
    --write-profile-decision-report \
    --output-dir <tmpdir>/foundation-scale-probe
  ```

  Expected result: `profile_decision_report.json` exists and records
  `async_orchestration.status == "defer"`.

### Task 6: Add Manifest Artifact Reference Without Default Churn

- [x] Keep report generation after the initial manifest write so existing
  dataset artifact assembly remains unchanged.
- [x] When `--write-profile-decision-report` is present, rewrite `manifest.json`
  after report generation to add `artifacts.profile_decision_report`.
- [x] Preserve no default manifest churn:
  - when `--write-profile-decision-report` is absent, current manifest shape is
    unchanged;
  - when present, the only manifest addition is the report artifact reference.
- [x] Extend `validate_manifest_record()` so
  `artifacts.profile_decision_report` is allowed when present.
- [x] Add tests proving default manifests omit the report artifact and opt-in
  manifests include it.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_contracts tests.test_cli tests.test_profile_decisions
  ```

  Expected result: manifest contract and CLI tests pass.

### Task 7: Update Canonical Docs and Plan Indexes

- [x] Update [../../DATA.md](../../DATA.md) with
  `profile_decision_report_v1` after the implementation exists.
- [x] Update [../../BACKEND.md](../../BACKEND.md) to mention opt-in profile
  decision reporting after artifact export.
- [x] Update [../../ROADMAP.md](../../ROADMAP.md) to mark profile decision
  reporting implemented when complete and keep async orchestration after it.
- [x] Move this plan to `../completed/` when accepted, then update:
  - [../../PLANS.md](../../PLANS.md);
  - [README.md](README.md);
  - [../completed/README.md](../completed/README.md);
  - [../../README.md](../../README.md);
  - [../../../README.md](../../../README.md) if the command becomes a primary
    developer workflow.
- [x] Run:

  ```bash
  uv run python scripts/validate_docs.py
  ```

  Expected result: documentation validation passes.

### Task 8: Final Verification

- [x] Run the full unit suite:

  ```bash
  uv run python -m unittest
  ```

  Expected result: all tests pass.

- [x] Run deterministic profile reporting:

  ```bash
  uv run python main.py \
    --run-profile tests/fixtures/run_profiles/foundation-scale-probe-25.json \
    --write-profile-decision-report \
    --output-dir artifacts/foundation-scale-probe
  ```

  Expected result: command completes synchronously, writes
  `profile_decision_report.json`, keeps `async_orchestration.status == "defer"`,
  keeps `semantic_duplicate_detection.status == "defer"`, and passes the MVP
  quality floor under default thresholds.

- [x] Inspect the combined exported report and manifest text for forbidden raw
  profile/source/provider leakage before marking the plan complete.

## Validation

- `uv run python scripts/validate_docs.py`
- `uv run python -m unittest`
- `uv run python main.py --run-profile tests/fixtures/run_profiles/foundation-scale-probe-25.json --write-profile-decision-report --output-dir artifacts/foundation-scale-probe`

## Acceptance Criteria

- A profile decision report can be generated from existing manifest and quality
  artifacts without rerunning candidate generation.
- The main CLI can write the report only when explicitly requested.
- Default pipeline runs and default manifests remain unchanged.
- The deterministic 25-candidate scale probe produces a report that keeps plan
  0014 deferred and keeps `TD-0002` deferred.
- Reports activate async orchestration only when candidate-count or runtime
  thresholds are met.
- Reports activate semantic duplicate detection only when both volume and exact
  duplicate-rate thresholds are met.
- Reports pass or fail the MVP quality floor using explicit thresholds and
  machine-readable reasons.
- Reports and manifest references remain sanitized and do not leak profile
  paths, source payloads, contact emails, prompts, headers, API keys, or
  arbitrary profile JSON.
- Documentation validation and the full unit suite pass.
