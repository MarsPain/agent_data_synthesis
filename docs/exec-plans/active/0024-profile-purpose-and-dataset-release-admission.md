# Plan 0024: Profile Purpose and Dataset Release Admission

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status

Active.

## Goal

Separate profile promotion from dataset release admission so diagnostic profiles
can validate framework behavior without being mistaken for releaseable dataset
versions.

## Architecture

This plan adds a narrow release-admission layer above the existing synchronous
artifact pipeline. `synthesis.run_profiles` will classify profile purpose,
`synthesis.dataset_release` will build a sanitized release decision report from
existing manifest, quality, evaluation, and profile-decision artifacts, and
`synthesis.datasets` plus `main.py` will attach the new report only when
explicitly requested. The default pipeline remains synchronous and unchanged
unless the new opt-in report flag is supplied.

## Tech Stack

- Python standard library: `dataclasses`, `json`, `pathlib`, and `unittest`.
- Existing modules: `synthesis.run_profiles`, `synthesis.profile_decisions`,
  `synthesis.contracts`, `synthesis.datasets`, and `main.py`.
- New module: `synthesis.dataset_release`.
- New script: `scripts/dataset_release_report.py`.
- Verification through `uv run python scripts/validate_docs.py` and
  `uv run python -m unittest`.

---

## Basis

- [../../PLANS.md](../../PLANS.md) has no active implementation plan after
  [../completed/0023-evaluation-quality-ratchet-and-profile-promotion.md](../completed/0023-evaluation-quality-ratchet-and-profile-promotion.md).
- The latest opt-in scale-probe artifacts under
  `artifacts/foundation-scale-probe-evaluation/` show:
  - `total_candidates: 25`;
  - `runtime_seconds: 0.03129795799031854`;
  - `async_orchestration.status: defer`;
  - `semantic_duplicate_detection.status: defer`;
  - `profile_promotion.status: passed`;
  - `exact_duplicate_rate: 0.12`, recorded as a low-volume watch signal.
- [../deferred/0014-async-local-orchestration-with-durable-queues.md](../deferred/0014-async-local-orchestration-with-durable-queues.md)
  remains deferred until single runs exceed about 10 minutes, reach about 100+
  candidates, hit painful recovery costs, or require per-role/per-provider cost
  attribution.
- [../tech-debt/README.md](../tech-debt/README.md) keeps `TD-0002` semantic
  duplicate detection unresolved until dataset volume or curriculum benchmark
  signals justify it.

## Why This Plan Now

Plan 0023 made profile promotion strict enough for local MVP quality decisions,
but the current scale-probe profile is intentionally diagnostic: it contains
controlled duplicate, verification-failure, and logical-support cases. A
diagnostic profile can pass promotion because the framework correctly detects
and reports those cases, yet that does not mean the generated artifact set is a
dataset version suitable for release.

Starting async orchestration would add infrastructure before the release boundary
is clear. Implementing semantic duplicate detection would also be premature
because the current duplicate signal is below the documented volume threshold.
The next narrow step is to make release eligibility explicit and machine
readable.

## Scope

- Add a profile-purpose classification:
  - `diagnostic_probe`: exercises framework behavior and is not releaseable;
  - `release_candidate`: eligible for dataset release admission;
  - `benchmark`: reusable benchmark or comparison profile and not releaseable by
    default.
- Preserve backward compatibility for existing run-profile fixtures by deriving
  a default purpose when the field is absent:
  - `generation.mode == "deterministic_scale_probe"` defaults to
    `diagnostic_probe`;
  - `generation.mode == "foundation_fixture"` defaults to `release_candidate`;
  - `generation.mode == "llm"` defaults to `release_candidate`.
- Include sanitized `profile_purpose` in run-profile manifest metadata and
  per-record run-profile attribution.
- Add `dataset_release_report_v1`, generated only when explicitly requested.
- Add a machine-readable `dataset_release` decision with statuses:
  - `passed`;
  - `failed`;
  - `blocked`;
  - `ineligible`;
  - `insufficient_evidence`.
- Require release admission to pass only when:
  - profile purpose is `release_candidate`;
  - `profile_promotion.status == "passed"`;
  - held-out evaluation evidence is present and passed;
  - `async_orchestration.status == "defer"`;
  - `semantic_duplicate_detection.status == "defer"`;
  - source-policy rejection rate is `0.0`;
  - manifest artifacts include `samples`, `rejections`, `quality_report`,
    `evaluation_report`, and `profile_decision_report`.
- Attach `dataset_release_report.json` to the manifest artifact map only when
  the report is explicitly written.
- Update canonical docs to distinguish `mvp_quality_floor`,
  `profile_promotion`, and `dataset_release`.

## Out of Scope

- Implementing async orchestration, durable queues, cancellation, resumption, or
  per-role cost tracking from plan 0014.
- Implementing semantic duplicate detection, embeddings, vector stores, or
  near-duplicate admission gates from `TD-0002`.
- Changing candidate generation, candidate acceptance, exact duplicate
  admission, verifier semantics, source governance, sandbox admission, or the
  default CLI output.
- Adding dashboards, REST APIs, external MCP servers, distributed workers,
  browser automation, model training, or downstream fine-tuning.
- Treating release admission as proof of downstream model improvement.

## Contract Design

### Run Profile Purpose

Extend `RunProfile` with:

```python
PROFILE_PURPOSES = {"diagnostic_probe", "release_candidate", "benchmark"}

@dataclass(frozen=True)
class RunProfile:
    schema_version: str
    profile_id: str
    dataset_version: str
    profile_purpose: str
    seed: DomainSeed
    generation: RunProfileGeneration
    features: RunProfileFeatures
    config_hash: str
    source: RunProfileSource | None = None
```

The profile JSON may include:

```json
{
  "profile_purpose": "release_candidate"
}
```

Existing fixtures remain valid when the field is absent. The loader derives the
purpose with this exact function:

```python
def _default_profile_purpose(generation_mode: str) -> str:
    if generation_mode == "deterministic_scale_probe":
        return "diagnostic_probe"
    return "release_candidate"
```

The profile purpose participates in the profile config hash because changing the
purpose changes release eligibility.

### Dataset Release Report

`dataset_release_report.json` uses `schema_version:
dataset_release_report_v1` and is generated only when explicitly requested. The
report reads existing manifest, quality report, evaluation report, and profile
decision report artifacts.

Expected shape:

```json
{
  "schema_version": "dataset_release_report_v1",
  "dataset_version": "dataset_foundation_scale_probe_25",
  "profile": {
    "schema_version": "run_profile_v1",
    "profile_id": "foundation_scale_probe_25",
    "generation_mode": "deterministic_scale_probe",
    "profile_purpose": "diagnostic_probe",
    "config_hash": "sha256:..."
  },
  "inputs": {
    "manifest_path": "manifest.json",
    "quality_report_path": "quality_report.json",
    "evaluation_report_path": "evaluation_report.json",
    "profile_decision_report_path": "profile_decision_report.json"
  },
  "observed": {
    "accepted": 14,
    "rejected": 11,
    "success_rate": 0.56,
    "executable_rate": 1.0,
    "source_policy_rejection_rate": 0.0,
    "heldout_status": "passed",
    "profile_promotion_status": "passed",
    "async_orchestration_status": "defer",
    "semantic_duplicate_detection_status": "defer"
  },
  "decisions": {
    "dataset_release": {
      "status": "ineligible",
      "reasons": [
        "profile_purpose diagnostic_probe is not release_candidate"
      ],
      "triggered_by": [
        "profile_purpose"
      ]
    }
  },
  "release_artifacts": {
    "samples": "samples.jsonl",
    "rejections": "rejections.jsonl",
    "quality_report": "quality_report.json",
    "evaluation_report": "evaluation_report.json",
    "profile_decision_report": "profile_decision_report.json"
  }
}
```

Allowed `dataset_release.status` values:

- `passed`: artifact set can be treated as a releaseable local MVP dataset
  version.
- `failed`: quality or held-out evaluation failed.
- `blocked`: release would require first implementing activated scale work such
  as async orchestration or semantic duplicate detection.
- `ineligible`: profile purpose is not releaseable.
- `insufficient_evidence`: required input artifacts or machine-readable fields
  are absent or malformed.

### Manifest Artifact Map

Add `dataset_release_report` to the allowed manifest artifact keys. The key is
absent by default and present only when the report is written:

```json
{
  "artifacts": {
    "samples": "samples.jsonl",
    "rejections": "rejections.jsonl",
    "quality_report": "quality_report.json",
    "evaluation_report": "evaluation_report.json",
    "profile_decision_report": "profile_decision_report.json",
    "dataset_release_report": "dataset_release_report.json"
  }
}
```

## File Map

- Modify `synthesis/run_profiles.py` for profile-purpose parsing, defaulting,
  canonical hashing, sanitized metadata, and per-record attribution inputs.
- Modify `synthesis/datasets.py` to carry `profile_purpose` into per-record
  run-profile attribution and to attach `dataset_release_report.json` to the
  manifest artifact map.
- Modify `synthesis/contracts.py` to validate profile purpose,
  `dataset_release_report_v1`, release decision statuses, and the new manifest
  artifact key.
- Create `synthesis/dataset_release.py` for release report input loading,
  report building, release-decision construction, validation, and writing.
- Create `scripts/dataset_release_report.py` for standalone report generation
  from an artifact directory or explicit artifact paths.
- Modify `main.py` to add `--write-dataset-release-report` and write the report
  after evaluation and profile-decision reports.
- Add `tests/test_dataset_release.py` for release report builder behavior.
- Extend `tests/test_run_profiles.py`, `tests/test_contracts.py`,
  `tests/test_cli.py`, and `tests/test_quality_reporting.py`.
- Update `docs/DATA.md`, `docs/BACKEND.md`, `docs/ROADMAP.md`,
  `docs/README.md`, and `docs/PLANS.md`.

## Implementation Tasks

### Task 1: Add Profile Purpose to Run Profiles

**Files:**

- Modify: `synthesis/run_profiles.py`
- Modify: `tests/test_run_profiles.py`
- Modify: `tests/fixtures/run_profiles/foundation-scale-probe-25.json`
- Modify: `tests/fixtures/run_profiles/foundation-fixture.json`

- [ ] Add failing tests for explicit purpose and derived defaults.

  Add these test methods to `tests/test_run_profiles.py`:

  ```python
  def test_load_run_profile_accepts_explicit_profile_purpose(self) -> None:
      with tempfile.TemporaryDirectory() as tmpdir:
          path = Path(tmpdir) / "profile.json"
          path.write_text(
              json.dumps(
                  {
                      "schema_version": "run_profile_v1",
                      "profile_id": "release_contacts",
                      "dataset_version": "dataset_release_contacts",
                      "profile_purpose": "release_candidate",
                      "seed": {
                          "seed_id": "seed_contacts",
                          "domain": "contacts",
                          "description": "Contacts release candidate.",
                          "task_taxonomy": ["single_tool_lookup"],
                      },
                      "generation": {"mode": "foundation_fixture"},
                      "features": {},
                  }
              ),
              encoding="utf-8",
          )

          profile = load_run_profile(path)

          self.assertEqual(profile.profile_purpose, "release_candidate")
          self.assertEqual(
              profile.sanitized_metadata()["profile_purpose"],
              "release_candidate",
          )

  def test_deterministic_scale_probe_defaults_to_diagnostic_purpose(self) -> None:
      profile = load_run_profile(
          Path("tests/fixtures/run_profiles/foundation-scale-probe-25.json")
      )

      self.assertEqual(profile.profile_purpose, "diagnostic_probe")
      self.assertEqual(
          profile.sanitized_metadata()["profile_purpose"],
          "diagnostic_probe",
      )

  def test_profile_purpose_participates_in_config_hash(self) -> None:
      with tempfile.TemporaryDirectory() as tmpdir:
          base = {
              "schema_version": "run_profile_v1",
              "profile_id": "purpose_hash",
              "dataset_version": "dataset_purpose_hash",
              "seed": {
                  "seed_id": "seed_contacts",
                  "domain": "contacts",
                  "description": "Contacts release candidate.",
                  "task_taxonomy": ["single_tool_lookup"],
              },
              "generation": {"mode": "foundation_fixture"},
              "features": {},
          }
          release_path = Path(tmpdir) / "release.json"
          diagnostic_path = Path(tmpdir) / "diagnostic.json"
          release_path.write_text(
              json.dumps({**base, "profile_purpose": "release_candidate"}),
              encoding="utf-8",
          )
          diagnostic_path.write_text(
              json.dumps({**base, "profile_purpose": "diagnostic_probe"}),
              encoding="utf-8",
          )

          release_profile = load_run_profile(release_path)
          diagnostic_profile = load_run_profile(diagnostic_path)

          self.assertNotEqual(release_profile.config_hash, diagnostic_profile.config_hash)
  ```

- [ ] Run profile tests and confirm they fail before implementation.

  ```bash
  uv run python -m unittest tests.test_run_profiles
  ```

  Expected failure: `RunProfile` has no `profile_purpose` attribute or sanitized
  metadata lacks `profile_purpose`.

- [ ] Implement `profile_purpose` parsing and defaulting.

  Add these constants and field changes in `synthesis/run_profiles.py`:

  ```python
  PROFILE_PURPOSES = {"diagnostic_probe", "release_candidate", "benchmark"}
  ```

  Add `profile_purpose: str` to `RunProfile`, include it in
  `sanitized_metadata()`, and include it in `_canonical_profile_mapping()`.

  In `load_run_profile()`, derive the purpose after generation is loaded:

  ```python
  generation = _load_generation(raw.get("generation"))
  profile_purpose = _load_profile_purpose(
      raw.get("profile_purpose"),
      generation_mode=generation.mode,
  )
  ```

  Add this helper:

  ```python
  def _load_profile_purpose(value: object, *, generation_mode: str) -> str:
      if value is None:
          return _default_profile_purpose(generation_mode)
      purpose = _require_string(value, "profile_purpose")
      if purpose not in PROFILE_PURPOSES:
          raise RunProfileValidationError(
              f"profile_purpose must be one of {sorted(PROFILE_PURPOSES)}"
          )
      return purpose


  def _default_profile_purpose(generation_mode: str) -> str:
      if generation_mode == "deterministic_scale_probe":
          return "diagnostic_probe"
      return "release_candidate"
  ```

- [ ] Add explicit fixture purpose values.

  Set `profile_purpose` in `tests/fixtures/run_profiles/foundation-scale-probe-25.json`
  to `diagnostic_probe`. Set `profile_purpose` in
  `tests/fixtures/run_profiles/foundation-fixture.json` to
  `release_candidate`.

- [ ] Run the focused tests.

  ```bash
  uv run python -m unittest tests.test_run_profiles
  ```

  Expected result: all run-profile tests pass.

### Task 2: Preserve Profile Purpose in Manifest and Record Attribution

**Files:**

- Modify: `synthesis/datasets.py`
- Modify: `synthesis/contracts.py`
- Modify: `tests/test_quality_reporting.py`
- Modify: `tests/test_contracts.py`

- [ ] Add failing tests for sanitized metadata and per-record attribution.

  Add a quality-reporting test that runs a profile fixture and asserts:

  ```python
  manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
  self.assertEqual(manifest["run_profile"]["profile_purpose"], "release_candidate")

  sample = json.loads((output_dir / "samples.jsonl").read_text(encoding="utf-8").splitlines()[0])
  self.assertEqual(
      sample["lineage"]["run_profile"]["profile_purpose"],
      "release_candidate",
  )
  ```

  Add a contract test that rejects unsupported purpose values in
  `manifest["run_profile"]` and `lineage.run_profile`.

- [ ] Run focused tests and confirm they fail.

  ```bash
  uv run python -m unittest tests.test_quality_reporting tests.test_contracts
  ```

  Expected failure: contract validation rejects or omits `profile_purpose`.

- [ ] Extend sanitized attribution.

  In `synthesis/datasets.py`, include `profile_purpose` in the narrow
  run-profile attribution record only when it is present in manifest metadata:

  ```python
  if "profile_purpose" in run_profile_metadata:
      attribution["profile_purpose"] = run_profile_metadata["profile_purpose"]
  ```

  Keep excluding profile paths, source paths, payload rows, prompts, headers,
  API keys, and arbitrary profile JSON keys.

- [ ] Extend contract validation.

  In `synthesis/contracts.py`, add profile-purpose validation for manifest
  metadata and run-profile attribution:

  ```python
  RUN_PROFILE_PURPOSES = {"diagnostic_probe", "release_candidate", "benchmark"}
  ```

  Require that any present `profile_purpose` is a non-empty string and a member
  of `RUN_PROFILE_PURPOSES`.

- [ ] Run focused tests.

  ```bash
  uv run python -m unittest tests.test_quality_reporting tests.test_contracts
  ```

  Expected result: focused tests pass.

### Task 3: Add Dataset Release Report Contracts

**Files:**

- Modify: `synthesis/contracts.py`
- Add: `tests/test_dataset_release.py`
- Modify: `tests/test_contracts.py`

- [ ] Write failing contract tests for `dataset_release_report_v1`.

  Add these cases:

  ```python
  def test_dataset_release_report_contract_accepts_release_decision(self) -> None:
      report = {
          "schema_version": "dataset_release_report_v1",
          "dataset_version": "dataset_release",
          "profile": {
              "schema_version": "run_profile_v1",
              "profile_id": "release_profile",
              "generation_mode": "foundation_fixture",
              "profile_purpose": "release_candidate",
              "config_hash": "sha256:" + "a" * 64,
          },
          "inputs": {
              "manifest_path": "manifest.json",
              "quality_report_path": "quality_report.json",
              "evaluation_report_path": "evaluation_report.json",
              "profile_decision_report_path": "profile_decision_report.json",
          },
          "observed": {
              "accepted": 3,
              "rejected": 0,
              "success_rate": 1.0,
              "executable_rate": 1.0,
              "source_policy_rejection_rate": 0.0,
              "heldout_status": "passed",
              "profile_promotion_status": "passed",
              "async_orchestration_status": "defer",
              "semantic_duplicate_detection_status": "defer",
          },
          "decisions": {
              "dataset_release": {
                  "status": "passed",
                  "reasons": ["release admission passed"],
                  "triggered_by": ["profile_promotion", "heldout_evaluation"],
              }
          },
          "release_artifacts": {
              "samples": "samples.jsonl",
              "rejections": "rejections.jsonl",
              "quality_report": "quality_report.json",
              "evaluation_report": "evaluation_report.json",
              "profile_decision_report": "profile_decision_report.json",
          },
      }

      validate_dataset_release_report_record(report)
  ```

  Add rejection tests for unsupported release status, missing input artifact
  names, raw secret-like keys, and `profile.profile_purpose == "diagnostic_probe"`
  paired with `dataset_release.status == "passed"`.

- [ ] Run contract tests and confirm they fail.

  ```bash
  uv run python -m unittest tests.test_contracts
  ```

  Expected failure: `validate_dataset_release_report_record` is not defined.

- [ ] Implement contract validation.

  In `synthesis/contracts.py`, add:

  ```python
  DATASET_RELEASE_STATUSES = {
      "passed",
      "failed",
      "blocked",
      "ineligible",
      "insufficient_evidence",
  }
  ```

  Add `dataset_release_report` to `MANIFEST_ARTIFACT_KEYS`.

  Add `validate_dataset_release_report_record(record)` that validates:

  - schema version equals `dataset_release_report_v1`;
  - raw secret material is absent;
  - artifact path fields are basenames;
  - profile fields are sanitized;
  - observed statuses are machine-readable strings;
  - release decision has allowed status, non-empty reasons, and trigger list;
  - `profile_purpose != "release_candidate"` cannot pair with
    `dataset_release.status == "passed"`.

- [ ] Run contract tests.

  ```bash
  uv run python -m unittest tests.test_contracts
  ```

  Expected result: contract tests pass.

### Task 4: Build Dataset Release Report Generation

**Files:**

- Create: `synthesis/dataset_release.py`
- Create: `tests/test_dataset_release.py`

- [ ] Write failing report-builder tests.

  Cover these cases in `tests/test_dataset_release.py`:

  - `release_candidate` plus passed promotion and passed held-out evidence
    returns `dataset_release.status == "passed"`.
  - `diagnostic_probe` returns `ineligible`.
  - activated async orchestration returns `blocked`.
  - activated semantic duplicate detection returns `blocked`.
  - failed profile promotion returns `failed`.
  - missing evaluation evidence returns `insufficient_evidence`.
  - source-policy rejection rate above zero returns `failed`.

  Use small in-memory dictionaries rather than reading artifact fixtures.

- [ ] Run report-builder tests and confirm they fail.

  ```bash
  uv run python -m unittest tests.test_dataset_release
  ```

  Expected failure: module `synthesis.dataset_release` is missing.

- [ ] Implement `synthesis/dataset_release.py`.

  Add:

  ```python
  DATASET_RELEASE_REPORT_SCHEMA_VERSION = "dataset_release_report_v1"

  @dataclass(frozen=True)
  class DatasetReleaseInputs:
      manifest: Mapping[str, Any]
      quality_report: Mapping[str, Any]
      evaluation_report: Mapping[str, Any] | None
      profile_decision_report: Mapping[str, Any] | None
      manifest_path: Path
      quality_report_path: Path
      evaluation_report_path: Path | None = None
      profile_decision_report_path: Path | None = None
  ```

  Implement `build_dataset_release_report(...)`, `load_dataset_release_inputs(...)`,
  and `write_dataset_release_report(...)` following the existing
  `synthesis.profile_decisions` style.

  Release-decision ordering:

  1. return `insufficient_evidence` if required artifacts or fields are missing
     or malformed;
  2. return `ineligible` if `profile_purpose != "release_candidate"`;
  3. return `blocked` if async or semantic duplicate decisions are `activate`;
  4. return `failed` if profile promotion or held-out evaluation failed;
  5. return `failed` if source-policy rejection rate is above `0.0`;
  6. return `passed`.

- [ ] Validate generated reports through contracts.

  Call `validate_dataset_release_report_record(report)` before writing the
  report. Write JSON with `ensure_ascii=False`, `indent=2`, and `sort_keys=True`
  to match existing report files.

- [ ] Run report-builder tests.

  ```bash
  uv run python -m unittest tests.test_dataset_release
  ```

  Expected result: dataset-release tests pass.

### Task 5: Add CLI and Manifest Integration

**Files:**

- Modify: `main.py`
- Modify: `synthesis/datasets.py`
- Create: `scripts/dataset_release_report.py`
- Modify: `tests/test_cli.py`

- [ ] Write failing CLI tests.

  Add one test that runs:

  ```bash
  uv run python main.py --run-profile tests/fixtures/run_profiles/foundation-scale-probe-25.json --write-evaluation-report --write-profile-decision-report --write-dataset-release-report --output-dir <tmpdir>
  ```

  Assert:

  ```python
  report = json.loads((output_dir / "dataset_release_report.json").read_text(encoding="utf-8"))
  self.assertEqual(report["decisions"]["dataset_release"]["status"], "ineligible")

  manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
  self.assertEqual(
      manifest["artifacts"]["dataset_release_report"],
      "dataset_release_report.json",
  )
  ```

  Add a second test that `--write-dataset-release-report` without
  `--write-profile-decision-report` exits non-zero and prints a clear argparse
  error.

- [ ] Run CLI tests and confirm they fail.

  ```bash
  uv run python -m unittest tests.test_cli
  ```

  Expected failure: CLI does not recognize `--write-dataset-release-report`.

- [ ] Add manifest attachment helper.

  In `synthesis/datasets.py`, add:

  ```python
  def attach_dataset_release_report_to_manifest(
      *,
      manifest_path: Path,
      report_path: Path,
  ) -> None:
      _attach_artifact_to_manifest(
          manifest_path=manifest_path,
          artifact_key="dataset_release_report",
          artifact_path=report_path,
      )
  ```

  Reuse the same internal helper pattern as evaluation and profile decision
  report attachment.

- [ ] Wire the CLI.

  In `main.py`, add `--write-dataset-release-report`. Validate that the flag
  requires both `--write-evaluation-report` and `--write-profile-decision-report`.
  After writing the profile decision report, call `write_dataset_release_report`
  and attach the report to the manifest.

- [ ] Add the standalone script.

  Create `scripts/dataset_release_report.py` with arguments:

  - `--manifest`;
  - `--quality-report`;
  - `--evaluation-report`;
  - `--profile-decision-report`;
  - optional `--output`.

  The script should call `write_dataset_release_report()` and print the output
  path.

- [ ] Run focused CLI and script tests.

  ```bash
  uv run python -m unittest tests.test_cli tests.test_dataset_release
  ```

  Expected result: focused tests pass.

### Task 6: Update Canonical Documentation

**Files:**

- Modify: `docs/DATA.md`
- Modify: `docs/BACKEND.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/README.md`
- Modify: `docs/PLANS.md`
- Modify: `docs/exec-plans/active/README.md`
- Modify: `AGENTS.md`

- [ ] Update `docs/DATA.md`.

  Document `profile_purpose`, `dataset_release_report_v1`, release decision
  statuses, release artifact references, and the difference between
  `profile_promotion` and `dataset_release`.

- [ ] Update `docs/BACKEND.md`.

  Add the optional dataset-release report step after profile decision reporting.
  State that release admission reads existing artifacts and does not change
  candidate processing.

- [ ] Update `docs/ROADMAP.md`.

  Mark plan 0024 as the next release-boundary step before async orchestration.
  Keep async orchestration and semantic duplicate detection deferred.

- [ ] Update plan indexes.

  Add this plan to `docs/PLANS.md`, `docs/exec-plans/active/README.md`, and
  `docs/README.md`. Update `AGENTS.md` so it no longer says there is no active
  implementation plan.

- [ ] Run documentation validation.

  ```bash
  uv run python scripts/validate_docs.py
  ```

  Expected result: `Documentation validation passed.`

### Task 7: End-to-End Verification

**Files:**

- Runtime output under `artifacts/foundation-scale-probe-release/`
- No source edits beyond implementation and docs files above.

- [ ] Run the focused release command.

  ```bash
  uv run python main.py --run-profile tests/fixtures/run_profiles/foundation-scale-probe-25.json --write-evaluation-report --write-profile-decision-report --write-dataset-release-report --output-dir artifacts/foundation-scale-probe-release
  ```

  Expected result:

  - `dataset_release_report.json` exists;
  - `manifest.json` references `artifacts.dataset_release_report`;
  - `dataset_release_report.profile.profile_purpose == "diagnostic_probe"`;
  - `dataset_release_report.decisions.dataset_release.status == "ineligible"`;
  - `profile_decision_report.decisions.profile_promotion.status == "passed"`;
  - `profile_decision_report.decisions.async_orchestration.status == "defer"`;
  - `profile_decision_report.decisions.semantic_duplicate_detection.status == "defer"`.

- [ ] Run documentation validation.

  ```bash
  uv run python scripts/validate_docs.py
  ```

  Expected result: `Documentation validation passed.`

- [ ] Run the full test suite.

  ```bash
  uv run python -m unittest
  ```

  Expected result: all tests pass.

## Acceptance Criteria

- Existing run-profile fixtures remain valid after `profile_purpose` is added.
- Deterministic scale-probe profiles are classified as `diagnostic_probe`.
- Release-candidate profiles can be explicitly classified as
  `release_candidate`.
- Sanitized run-profile metadata and per-record attribution include
  `profile_purpose` without raw profile paths, source paths, payload rows,
  prompts, headers, API keys, or arbitrary profile JSON.
- `dataset_release_report_v1` is validated, sanitized, deterministic, and
  written only when explicitly requested.
- A diagnostic profile cannot produce `dataset_release.status == "passed"`.
- A release candidate cannot pass release admission unless profile promotion and
  held-out evaluation both pass.
- Release admission is blocked when async orchestration or semantic duplicate
  detection activates.
- Manifest artifact references include `dataset_release_report` only for opt-in
  runs.
- Default local synthesis remains synchronous and does not write release reports
  unless explicitly requested.
- Plan 0014 remains deferred unless scale triggers are met.
- `TD-0002` remains unresolved unless future volume or benchmark evidence
  justifies a separate semantic duplicate detection plan.
- Documentation validation and the full unit suite pass.

## Risks

- **Terminology drift:** `profile_promotion` and `dataset_release` can sound
  interchangeable. Keep docs explicit: promotion is configuration readiness;
  release is artifact-set admission.
- **Backward compatibility:** Existing profiles do not have `profile_purpose`.
  Use deterministic defaulting and include purpose in the config hash so future
  purpose changes remain auditable.
- **False confidence:** Release admission only proves local MVP artifact
  eligibility. It does not prove downstream model improvement.
- **Over-coupling:** Avoid making release admission re-execute evaluations or
  candidates. It should read existing artifacts and make a deterministic
  decision.
- **Premature scale work:** Do not use this plan to implement async
  orchestration or semantic duplicate detection. It should make those future
  decisions clearer.
