# Plan 0042: Representative Scale And Downstream Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an offline, deterministic evidence campaign that distinguishes
representative runs from diagnostic fixtures, aggregates three-domain scale and
review signals, binds a verified release pack to an external downstream
benchmark protocol, and validates imported baseline-versus-treatment results.

**Architecture:** Add two standalone consumers above the existing artifact
boundary. `synthesis.scale_evidence` consumes current manifest, quality,
evaluation, profile-decision, dataset-release, release-audit, and optional
review-resolution artifacts; `synthesis.downstream_benchmark` binds an existing
verified release pack to a benchmark protocol and validates a sanitized result
written by an external training system. Keep `main.py`, candidate admission,
profile decisions, dataset release, release-pack bytes, and plan activation
unchanged.

**Tech Stack:** Python standard library (`dataclasses`, `hashlib`, `json`,
`math`, `pathlib`), existing contract and release-pack validators, standalone
`argparse` scripts, JSON/JSONL fixtures, `unittest`, and the documentation
validator.

---

## Status

Completed on 2026-07-11. Created on 2026-07-11.

The intermediate commit steps below were intentionally skipped by explicit
operator request; final delivery was consolidated through an operator-directed
amend after review and verification.

Approved design:
[representative-scale-and-downstream-evidence.md](../../design-docs/representative-scale-and-downstream-evidence.md).

## Why This Plan

Plans 0040 and 0041 completed deterministic release-candidate and human-review
evidence across contacts, mobile messages, and workspace tasks. Those fixtures
prove contracts and release workflows, but each current release candidate has
only five accepted samples. The repository therefore does not yet know whether
representative workloads justify async orchestration, semantic duplicate
detection, or generation/verifier investment.

The existing decision thresholds are already explicit:

- async orchestration activates at `100` total candidates or `600` runtime
  seconds;
- semantic duplicate detection activates only at `100` total candidates and an
  exact duplicate rate of at least `0.1`; and
- release audit watches releases with fewer than `8` accepted samples.

Plan 0014 and TD-0002 must remain deferred until real evidence reaches their
triggers. Mechanically repeating mobile/workspace fixture candidates to reach
100 would manufacture duplicate pressure and invalidate the decision. This plan
therefore makes representativeness a validated classification and treats all
current fixture/scale-probe generation modes as `diagnostic_only`.

The product evidence gap is also downstream. `docs/PRODUCT_SENSE.md` names
held-out model improvement as a supporting metric, but this repository should
not become a training platform. A hash-locked benchmark bundle and a sanitized
result-import contract close the evidence exchange without adding trainers,
credentials, schedulers, or model storage.

## Scope

- Define `representative_scale_evidence_v1` with deterministic campaign
  identity, three-domain summaries, consumed artifact hashes, review aggregates,
  evidence classification, trigger observations, and a conservative primary
  recommendation.
- Treat `foundation_fixture`, `deterministic_scale_probe`, `mobile_fixture`, and
  `workspace_fixture` as `diagnostic_only` regardless of candidate count.
- Treat malformed, missing, cross-domain, cross-dataset, or identity-mismatched
  evidence as `insufficient_evidence`.
- Permit `representative` only for an approved non-fixture generation mode with
  consistent domain/profile/report identities and complete required artifacts.
- Reuse the threshold values recorded in each valid
  `profile_decision_report_v1`; do not define a second set of scale thresholds.
- Define `downstream_benchmark_bundle_v1` over one standalone-verified
  `dataset_release_pack_v1` and a fixed baseline/treatment protocol.
- Define `downstream_benchmark_result_v1` for sanitized external result import,
  identity validation, metric validation, deterministic deltas, and conservative
  result status.
- Add standalone commands that consume existing artifact paths and never rerun
  generation or mutate existing artifacts.
- Add unit, contract, CLI, redaction, and offline end-to-end tests.
- Document how an operator runs the evidence exchange and how its claims must be
  interpreted.

## Out Of Scope

- Model training, fine-tuning, reward-model training, policy optimization,
  Agentic RL, or calls to a training service.
- Adding a mobile/workspace LLM task generator solely to satisfy the scale
  threshold. A later plan may add representative domain generation after this
  evidence campaign identifies that gap.
- Changing `DecisionThresholds`, profile-promotion logic, dataset-release
  admission, release-quality audit status, or review-resolution semantics.
- Async orchestration, durable queues, cancellation, distributed workers,
  dashboards, or per-role async cost accounting from plan 0014.
- Embeddings, vector stores, clustering, semantic similarity scoring, or
  near-duplicate admission gates from TD-0002.
- Automatic plan activation, automatic release blocking, or manifest mutation
  from a scale/downstream result.
- External MCP servers, browser automation, real-user data, a fourth domain, or
  package publishing.
- Adding flags to the default `main.py` generation command.

## Existing Boundaries To Preserve

- `synthesis.profile_decisions` owns the thresholds and per-run decisions.
- `synthesis.dataset_release` owns dataset release admission.
- `synthesis.release_pack` owns release-pack construction and standalone
  verification.
- `synthesis.release_review` owns release-review queue and resolution evidence.
- `synthesis.datasets` owns manifests. Plan 0042 writes standalone evidence and
  does not attach new references to existing manifests.
- Existing release-pack hashes and bytes must remain unchanged.
- The external result input may contain only the documented schema. Trainer
  logs, commands, credentials, local paths, and arbitrary metadata are rejected,
  not copied.

## Data Contracts

### Campaign Input

The scale-evidence CLI accepts one explicit JSON object with exactly this
shape:

```json
{
  "schema_version": "representative_scale_campaign_v1",
  "campaign_label": "three_domain_scale_2026_07",
  "runs": [
    {"domain_id": "contacts_fixture", "artifact_dir": "artifacts/contacts"},
    {"domain_id": "mobile_messages_fixture", "artifact_dir": "artifacts/mobile"},
    {"domain_id": "workspace_tasks_fixture", "artifact_dir": "artifacts/workspace"}
  ]
}
```

`artifact_dir` is an input-only path and is never persisted. Exactly one entry
is required for every supported domain. Unknown keys, duplicate domains,
absolute persisted paths, and missing required artifacts are invalid. The
loader resolves input paths relative to the campaign file, while output records
store only artifact basenames and hashes.

### Representative Scale Evidence

`representative_scale_evidence.json` uses
`schema_version: representative_scale_evidence_v1`:

```json
{
  "schema_version": "representative_scale_evidence_v1",
  "campaign_id": "scale_campaign:sha256:0000000000000000000000000000000000000000000000000000000000000000",
  "campaign_label": "three_domain_scale_2026_07",
  "domains": [
    {
      "domain_id": "contacts_fixture",
      "dataset_version": "dataset_contacts_release_candidate",
      "profile_id": "contacts_release_candidate",
      "generation_mode": "llm",
      "classification": "representative",
      "artifacts": {
        "manifest": {"path": "manifest.json", "sha256": "0000000000000000000000000000000000000000000000000000000000000000"},
        "quality_report": {"path": "quality_report.json", "sha256": "1111111111111111111111111111111111111111111111111111111111111111"},
        "evaluation_report": {"path": "evaluation_report.json", "sha256": "2222222222222222222222222222222222222222222222222222222222222222"},
        "profile_decision_report": {"path": "profile_decision_report.json", "sha256": "3333333333333333333333333333333333333333333333333333333333333333"},
        "dataset_release_report": {"path": "dataset_release_report.json", "sha256": "4444444444444444444444444444444444444444444444444444444444444444"},
        "release_quality_audit": {"path": "release_quality_audit.json", "sha256": "5555555555555555555555555555555555555555555555555555555555555555"}
      },
      "observed": {
        "total_candidates": 100,
        "accepted": 80,
        "rejected": 20,
        "runtime_seconds": 601.0,
        "exact_duplicate_count": 4,
        "exact_duplicate_rate": 0.04,
        "heldout_status": "passed",
        "mvp_quality_floor_status": "passed",
        "profile_promotion_status": "blocked",
        "dataset_release_status": "blocked",
        "release_audit_status": "blocked",
        "review_resolution_status": null
      },
      "signals": ["async_orchestration"]
    }
  ],
  "review": {
    "queued": 0,
    "resolved": 0,
    "pending": 0,
    "confirmed_issue": 0,
    "accepted_risk": 0,
    "needs_follow_up": 0,
    "review_minutes": 0
  },
  "triggered_signals": ["async_orchestration"],
  "decision": {
    "recommendation": "activate_async_orchestration",
    "reasons": ["representative contacts run activated its existing async decision"]
  }
}
```

Domain order is fixed as contacts, mobile messages, workspace tasks. Artifact
records contain basename and SHA-256 only. Optional
`review_resolution_report.json` is aggregated when present and valid; aliases,
individual decisions, and reasons are not copied.

Allowed classifications are `representative`, `diagnostic_only`, and
`insufficient_evidence`. Allowed recommendations are:

- `activate_async_orchestration`;
- `activate_semantic_duplicate_detection`;
- `improve_generation_or_verification`;
- `expand_representative_evidence`; and
- `no_change_recommended`.

Recommendation priority is deterministic:

1. any missing/invalid required domain evidence ->
   `expand_representative_evidence`;
2. any representative run with failed quality, evaluation, or a confirmed
   review issue -> `improve_generation_or_verification`;
3. any representative run whose existing semantic decision is `activate` ->
   `activate_semantic_duplicate_detection`;
4. any representative run whose existing async decision is `activate` ->
   `activate_async_orchestration`;
5. otherwise -> `no_change_recommended`.

Diagnostic-only activation signals are retained as watch reasons but cannot
select an activation recommendation.

### Downstream Benchmark Bundle

`downstream_benchmark_bundle.json` uses
`schema_version: downstream_benchmark_bundle_v1`:

```json
{
  "schema_version": "downstream_benchmark_bundle_v1",
  "benchmark_id": "downstream_benchmark:sha256:6666666666666666666666666666666666666666666666666666666666666666",
  "dataset_version": "dataset_contacts_release_candidate",
  "release": {
    "release_id": "dataset_contacts_release_candidate:sha256:7777777777777777777777777777777777777777777777777777777777777777",
    "pack_path": "dataset_release_pack.json",
    "pack_sha256": "8888888888888888888888888888888888888888888888888888888888888888",
    "pack_byte_count": 1234
  },
  "protocol": {
    "protocol_version": "external_agent_benchmark_v1",
    "benchmark_suite_id": "external_agent_tasks_v1",
    "benchmark_suite_version": "external_agent_tasks_v1",
    "baseline_arm": "baseline_without_synthetic_release",
    "treatment_arm": "treatment_with_exact_synthetic_release",
    "primary_metric": "task_success_rate",
    "metrics": [
      {"name": "task_success_rate", "direction": "higher_is_better", "minimum": 0.0, "maximum": 1.0}
    ],
    "result_schema_version": "downstream_benchmark_result_v1"
  },
  "claims": {
    "changes_release_admission": false,
    "proves_causality": false,
    "trains_inside_repository": false
  }
}
```

The bundle is written only when `verify_dataset_release_pack(release_pack_path)` returns
`verification.status == "passed"`. `benchmark_id` hashes canonical JSON of the
release identity and protocol.

### Downstream Benchmark Observation And Result

The explicit external input uses
`schema_version: downstream_benchmark_observation_v1` and contains exactly the
identity, evaluation, and `arms` fields shown below; it does not contain a
comparison or decision. The normalized output uses
`schema_version: downstream_benchmark_result_v1` and adds the computed
`comparison` and `decision` fields. It is written as
`downstream_benchmark_result.json`:

```json
{
  "schema_version": "downstream_benchmark_observation_v1",
  "benchmark_id": "downstream_benchmark:sha256:6666666666666666666666666666666666666666666666666666666666666666",
  "dataset_version": "dataset_contacts_release_candidate",
  "release_id": "dataset_contacts_release_candidate:sha256:7777777777777777777777777777777777777777777777777777777777777777",
  "release_pack_sha256": "8888888888888888888888888888888888888888888888888888888888888888",
  "benchmark_suite_id": "external_agent_tasks_v1",
  "benchmark_suite_version": "external_agent_tasks_v1",
  "evaluation_seed_ids": ["seed_01", "seed_02"],
  "evaluation_sample_count": 200,
  "arms": {
    "baseline": {"model_alias": "baseline_model_a", "metrics": {"task_success_rate": 0.61}},
    "treatment": {"model_alias": "treatment_model_a", "metrics": {"task_success_rate": 0.67}}
  }
}
```

The normalized result is:

```json
{
  "schema_version": "downstream_benchmark_result_v1",
  "benchmark_id": "downstream_benchmark:sha256:6666666666666666666666666666666666666666666666666666666666666666",
  "dataset_version": "dataset_contacts_release_candidate",
  "release_id": "dataset_contacts_release_candidate:sha256:7777777777777777777777777777777777777777777777777777777777777777",
  "release_pack_sha256": "8888888888888888888888888888888888888888888888888888888888888888",
  "benchmark_suite_id": "external_agent_tasks_v1",
  "benchmark_suite_version": "external_agent_tasks_v1",
  "evaluation_seed_ids": ["seed_01", "seed_02"],
  "evaluation_sample_count": 200,
  "arms": {
    "baseline": {
      "model_alias": "baseline_model_a",
      "metrics": {"task_success_rate": 0.61}
    },
    "treatment": {
      "model_alias": "treatment_model_a",
      "metrics": {"task_success_rate": 0.67}
    }
  },
  "comparison": {
    "primary_metric": "task_success_rate",
    "absolute_delta": 0.06,
    "relative_delta": 0.09836065573770492
  },
  "decision": {
    "status": "improved",
    "reasons": ["treatment primary metric exceeds baseline primary metric"]
  }
}
```

Allowed result statuses are `improved`, `no_detected_improvement`, and
`insufficient_evidence`. Equality is `no_detected_improvement`. Relative delta
is `null` when the baseline primary metric is zero. Non-finite/out-of-range
metrics, missing protocol metrics, identity mismatches, duplicate/empty seed
ids, non-positive sample counts, unknown keys, paths, or free-text metadata
produce a sanitized `insufficient_evidence` result rather than a traceback or
partial artifact.

For an invalid observation after a valid bundle was loaded, the normalized
result preserves bundle identities, sets `evaluation_seed_ids` to `[]`,
`evaluation_sample_count` to `0`, `arms` and `comparison` to `null`, and writes
`decision.status: insufficient_evidence` with exactly one fixed reason code.
The result validator permits those null/empty values only for that status.

## File Map

- Add `synthesis/scale_evidence.py`
  - Own campaign input loading, artifact hashing/loading, identity checks,
    representativeness classification, review aggregation, recommendation
    selection, contract construction, and deterministic writing.
- Add `synthesis/downstream_benchmark.py`
  - Own benchmark protocol records, release-pack verification, bundle ids,
    result validation, delta calculation, sanitized insufficient-evidence
    output, and deterministic writing.
- Modify `synthesis/contracts.py`
  - Add exact-key, vocabulary, canonical-id, numeric-range, and path-safety
    validators for the campaign, scale evidence, benchmark bundle, external
    observation, and normalized result.
- Add `scripts/write_representative_scale_evidence.py`
  - Read one campaign file and write one aggregate scale-evidence report.
- Add `scripts/write_downstream_benchmark_bundle.py`
  - Build one bundle from a verified release pack and explicit protocol args.
- Add `scripts/import_downstream_benchmark_result.py`
  - Normalize and validate one external result against one bundle.
- Add `tests/test_scale_evidence.py`
  - Cover three-domain aggregation, identity failures, classification,
    redaction, recommendation priority, and deterministic ids/output.
- Add `tests/test_downstream_benchmark.py`
  - Cover verified-pack prerequisites, bundle identity, metric contracts,
    result normalization, invalid inputs, redaction, and CLI behavior.
- Modify `tests/test_contracts.py`
  - Cover valid/malformed examples for all four new schema versions.
- Modify `tests/test_cli.py`
  - Assert default generation writes none of the new evidence artifacts.
- Add `tests/fixtures/evidence_campaigns/three-domain-diagnostic.json`
  - A relative-path campaign used by CLI tests over temporary copied artifacts.
- Add `tests/fixtures/downstream_benchmark_observation.json`
  - A sanitized valid external baseline/treatment observation fixture.
- Modify `README.md`
  - Add the three standalone commands after they exist.
- Modify `AGENTS.md`
  - Add high-level commands and keep the file a compact map.
- Modify `docs/BACKEND.md`, `docs/DATA.md`, `docs/PRODUCT_SENSE.md`,
  `docs/ROADMAP.md`, `docs/PLANS.md`, `docs/README.md`, and
  `docs/exec-plans/active/README.md`
  - Document boundaries, contracts, interpretation, plan lifecycle, and final
    validation evidence.

## Implementation Tasks

### Task 1: Lock Existing Defaults And Build Artifact Test Helpers

**Files:**

- Modify: `tests/test_cli.py`
- Add: `tests/test_scale_evidence.py`
- Add: `tests/test_downstream_benchmark.py`

- [x] **Step 1: Add default-path characterization assertions.**

  Extend the existing default CLI test with:

  ```text
  self.assertFalse((output_dir / "representative_scale_evidence.json").exists())
  self.assertFalse((output_dir / "downstream_benchmark_bundle.json").exists())
  self.assertFalse((output_dir / "downstream_benchmark_result.json").exists())
  ```

- [x] **Step 2: Add focused artifact builders in the new test modules.**

  The helper must run or construct existing validated three-domain artifacts;
  it must not introduce production fixture helpers. Use this signature in
  `tests/test_scale_evidence.py`:

  ```text
  def write_domain_artifacts(
      root: Path,
      *,
      domain_id: str,
      dataset_version: str,
      generation_mode: str,
      total_candidates: int,
      async_status: str = "defer",
      semantic_status: str = "defer",
  ) -> Path:
      """Write contract-valid existing artifacts and return their directory."""
  ```

  Reuse existing record helpers from their owning test modules only when they
  are public and stable; otherwise copy the minimal validated record shape into
  the new test module.

- [x] **Step 3: Run the characterization tests.**

  ```bash
  uv run python -m unittest tests.test_cli
  ```

  Expected: PASS before production implementation; default output is unchanged.

- [x] **Step 4: Commit the characterization boundary.**

  ```bash
  git add tests/test_cli.py tests/test_scale_evidence.py tests/test_downstream_benchmark.py
  git commit -m "test: lock evidence workflow boundaries"
  ```

### Task 2: Add Evidence And Benchmark Contract Validators

**Files:**

- Modify: `synthesis/contracts.py`
- Modify: `tests/test_contracts.py`

- [x] **Step 1: Write failing valid-record tests.**

  Import and exercise these new validators:

  ```python
  from synthesis.contracts import (
      validate_downstream_benchmark_bundle_record,
      validate_downstream_benchmark_observation_record,
      validate_downstream_benchmark_result_record,
      validate_representative_scale_campaign_record,
      validate_representative_scale_evidence_record,
  )
  ```

  Add one minimal valid record for every schema described above and assert each
  validator returns without error.

- [x] **Step 2: Write failing malformed-record subtests.**

  Cover exact key sets, schema versions, domain uniqueness/order, allowed
  classifications/recommendations/statuses, `sha256` lowercase hex length,
  canonical id prefixes, safe basenames, finite metric bounds, unique seed ids,
  positive sample counts, and boolean claim fields. Use mutations such as:

  ```python
  cases = {
      "absolute artifact path": ("artifacts.manifest.path", "/tmp/manifest.json"),
      "non finite metric": ("arms.baseline.metrics.task_success_rate", float("nan")),
      "unknown recommendation": ("decision.recommendation", "train_model_now"),
  }
  ```

- [x] **Step 3: Run the tests and confirm the missing imports fail.**

  ```bash
  uv run python -m unittest tests.test_contracts
  ```

  Expected: FAIL because the five validators do not exist.

- [x] **Step 4: Add validator constants and functions.**

  Define these public vocabularies and validators in `synthesis/contracts.py`:

  ```text
  REPRESENTATIVE_SCALE_CLASSIFICATIONS = {
      "representative", "diagnostic_only", "insufficient_evidence"
  }
  REPRESENTATIVE_SCALE_RECOMMENDATIONS = {
      "activate_async_orchestration",
      "activate_semantic_duplicate_detection",
      "improve_generation_or_verification",
      "expand_representative_evidence",
      "no_change_recommended",
  }
  DOWNSTREAM_BENCHMARK_STATUSES = {
      "improved", "no_detected_improvement", "insufficient_evidence"
  }

  validate_representative_scale_campaign_record(record: Mapping[str, Any]) -> None
  validate_representative_scale_evidence_record(record: Mapping[str, Any]) -> None
  validate_downstream_benchmark_bundle_record(record: Mapping[str, Any]) -> None
  validate_downstream_benchmark_observation_record(record: Mapping[str, Any]) -> None
  validate_downstream_benchmark_result_record(record: Mapping[str, Any]) -> None
  ```

  Follow the existing `_require_exact_keys`, safe-relative-path, numeric, list,
  and decision validation helpers. Do not loosen an existing validator.

- [x] **Step 5: Run focused contract tests.**

  ```bash
  uv run python -m unittest tests.test_contracts
  ```

  Expected: PASS.

- [x] **Step 6: Commit the contracts.**

  ```bash
  git add synthesis/contracts.py tests/test_contracts.py
  git commit -m "feat: define scale and downstream evidence contracts"
  ```

### Task 3: Aggregate Three-Domain Scale Evidence

**Files:**

- Add: `synthesis/scale_evidence.py`
- Modify: `tests/test_scale_evidence.py`

- [x] **Step 1: Write failing campaign loading and identity tests.**

  Test exactly three required domains, relative input path resolution, missing
  reports, dataset-version mismatch, evaluation-domain mismatch, duplicate
  domains, and output redaction. The public API under test is:

  ```text
  @dataclass(frozen=True)
  class CampaignRunInput:
      domain_id: str
      artifact_dir: Path

  @dataclass(frozen=True)
  class ScaleCampaignInput:
      campaign_label: str
      runs: tuple[CampaignRunInput, ...]

  load_scale_campaign(path: Path) -> ScaleCampaignInput
  ```

- [x] **Step 2: Write failing classification tests.**

  Assert all four fixture modes remain diagnostic even with 100 candidates:

  ```python
  for mode in (
      "foundation_fixture",
      "deterministic_scale_probe",
      "mobile_fixture",
      "workspace_fixture",
  ):
      self.assertEqual(classify_run(valid_artifacts(mode)), "diagnostic_only")
  ```

  Assert a contract-valid `llm` run with consistent artifacts may be
  `representative`; malformed or incomplete input is `insufficient_evidence`.
  Do not classify solely from candidate count.

- [x] **Step 3: Write failing aggregation and priority tests.**

  Cover diagnostic activation watches, representative async activation,
  representative semantic activation, failed held-out/MVP-quality evidence,
  confirmed human issue, incomplete domain evidence, stable domain order, and
  deterministic campaign id.

- [x] **Step 4: Run the new tests and verify they fail.**

  ```bash
  uv run python -m unittest tests.test_scale_evidence
  ```

  Expected: FAIL because `synthesis.scale_evidence` does not exist.

- [x] **Step 5: Implement artifact loading and classification.**

  Add these constants and APIs:

  ```text
  SCALE_CAMPAIGN_SCHEMA_VERSION = "representative_scale_campaign_v1"
  SCALE_EVIDENCE_SCHEMA_VERSION = "representative_scale_evidence_v1"
  REQUIRED_DOMAINS = (
      "contacts_fixture",
      "mobile_messages_fixture",
      "workspace_tasks_fixture",
  )
  DIAGNOSTIC_GENERATION_MODES = {
      "foundation_fixture",
      "deterministic_scale_probe",
      "mobile_fixture",
      "workspace_fixture",
  }
  REPRESENTATIVE_GENERATION_MODES = {"llm"}

  build_representative_scale_evidence(campaign: ScaleCampaignInput) -> dict[str, object]
  write_representative_scale_evidence(*, campaign_path: Path, output_path: Path) -> Path
  ```

  Required artifacts are `manifest.json`, `quality_report.json`,
  `evaluation_report.json`, `profile_decision_report.json`,
  `dataset_release_report.json`, and `release_quality_audit.json`.
  `review_resolution_report.json` is optional. Validate every loaded record with
  its existing contract validator before reading values.

- [x] **Step 6: Implement recommendation selection.**

  Use one pure function with explicit priority:

  ```python
  def select_recommendation(domain_summaries: Sequence[Mapping[str, Any]]) -> dict[str, object]:
      if any(d["classification"] == "insufficient_evidence" for d in domain_summaries):
          return decision("expand_representative_evidence", "required domain evidence is incomplete")
      representative = [d for d in domain_summaries if d["classification"] == "representative"]
      if not representative:
          return decision("expand_representative_evidence", "no representative domain run is available")
      if any(has_quality_problem(d) for d in representative):
          return decision("improve_generation_or_verification", "representative quality evidence requires remediation")
      if any(has_signal(d, "semantic_duplicate_detection") for d in representative):
          return decision("activate_semantic_duplicate_detection", "representative semantic duplicate decision activated")
      if any(has_signal(d, "async_orchestration") for d in representative):
          return decision("activate_async_orchestration", "representative async decision activated")
      return decision("no_change_recommended", "representative evidence activates no development gate")
  ```

  Implement `decision`, `has_quality_problem`, and `has_signal` in the same
  module with sanitized fixed-vocabulary reasons. `has_quality_problem` is true
  only for failed held-out evaluation, failed MVP quality floor, or at least one
  confirmed review issue. It must not treat profile/release `blocked` caused by
  an activated scale decision as a quality failure.

- [x] **Step 7: Run focused tests.**

  ```bash
  uv run python -m unittest tests.test_scale_evidence tests.test_contracts
  ```

  Expected: PASS.

- [x] **Step 8: Commit scale evidence.**

  ```bash
  git add synthesis/scale_evidence.py tests/test_scale_evidence.py
  git commit -m "feat: aggregate representative scale evidence"
  ```

### Task 4: Build A Hash-Locked Downstream Benchmark Bundle

**Files:**

- Add: `synthesis/downstream_benchmark.py`
- Modify: `tests/test_downstream_benchmark.py`

- [x] **Step 1: Write failing bundle tests.**

  Cover valid verified packs, missing packs, malformed packs, drifted artifacts,
  post-pack review-resolution compatibility, metric-name uniqueness, primary
  metric inclusion, metric bounds, deterministic ids, and basename-only output.

- [x] **Step 2: Run the tests and verify the module is missing.**

  ```bash
  uv run python -m unittest tests.test_downstream_benchmark
  ```

  Expected: FAIL because `synthesis.downstream_benchmark` does not exist.

- [x] **Step 3: Implement protocol and bundle records.**

  Use focused immutable types:

  ```text
  @dataclass(frozen=True)
  class BenchmarkMetric:
      name: str
      direction: str
      minimum: float
      maximum: float

  @dataclass(frozen=True)
  class BenchmarkProtocol:
      protocol_version: str
      benchmark_suite_id: str
      benchmark_suite_version: str
      primary_metric: str
      metrics: tuple[BenchmarkMetric, ...]

  build_downstream_benchmark_bundle(*, release_pack_path: Path, protocol: BenchmarkProtocol) -> dict[str, object]
  write_downstream_benchmark_bundle(*, release_pack_path: Path, protocol: BenchmarkProtocol, output_path: Path) -> Path
  ```

  Call `verify_dataset_release_pack(release_pack_path)` first and raise
  `ValueError("dataset release pack verification must pass")` unless its status
  is `passed`. Hash the pack bytes after verification. Load the validated pack
  only to copy dataset/release identity.

- [x] **Step 4: Run bundle and release-pack regression tests.**

  ```bash
  uv run python -m unittest tests.test_downstream_benchmark tests.test_release_pack
  ```

  Expected: PASS.

- [x] **Step 5: Commit bundle construction.**

  ```bash
  git add synthesis/downstream_benchmark.py tests/test_downstream_benchmark.py
  git commit -m "feat: add downstream benchmark bundles"
  ```

### Task 5: Import And Normalize External Benchmark Results

**Files:**

- Modify: `synthesis/downstream_benchmark.py`
- Modify: `tests/test_downstream_benchmark.py`
- Add: `tests/fixtures/downstream_benchmark_observation.json`

- [x] **Step 1: Write failing valid comparison tests.**

  Test improved, equal, regressed, and zero-baseline cases. Assert exact
  calculation behavior:

  ```python
  self.assertAlmostEqual(result["comparison"]["absolute_delta"], 0.06)
  self.assertAlmostEqual(result["comparison"]["relative_delta"], 0.06 / 0.61)
  self.assertEqual(result["decision"]["status"], "improved")
  ```

- [x] **Step 2: Write failing identity and redaction tests.**

  Cover benchmark/release/hash/suite mismatches, unknown arms/keys, duplicate or
  empty seeds, non-positive counts, missing metrics, NaN/infinity, values outside
  protocol bounds, absolute paths, credentials, trainer logs, and malformed
  JSON. Each case must return a contract-valid `insufficient_evidence` result
  containing only a fixed reason code and exception class when needed.

- [x] **Step 3: Implement result normalization.**

  Add this API:

  ```text
  build_downstream_benchmark_result(*, bundle: Mapping[str, Any], observation: Mapping[str, Any]) -> dict[str, object]
  import_downstream_benchmark_result(*, bundle_path: Path, observation_path: Path, output_path: Path) -> Path
  ```

  Validate the bundle before reading the observation. An unreadable or malformed
  bundle is a failed prerequisite and writes no result. Once the bundle is
  valid, catch observation `OSError`, `json.JSONDecodeError`,
  `ContractValidationError`, and `ValueError` and write a contract-valid
  `insufficient_evidence` result using identities from that bundle and one of
  these sanitized reasons:

  ```python
  RESULT_REASON_CODES = {
      "observation_unreadable_or_malformed",
      "benchmark_identity_mismatch",
      "release_identity_mismatch",
      "benchmark_suite_mismatch",
      "evaluation_identity_invalid",
      "metric_contract_invalid",
  }
  ```

- [x] **Step 4: Run result tests.**

  ```bash
  uv run python -m unittest tests.test_downstream_benchmark tests.test_contracts
  ```

  Expected: PASS.

- [x] **Step 5: Commit result import.**

  ```bash
  git add synthesis/downstream_benchmark.py tests/test_downstream_benchmark.py tests/fixtures/downstream_benchmark_observation.json
  git commit -m "feat: validate downstream benchmark results"
  ```

### Task 6: Add Standalone CLI Workflows And Offline End-To-End Coverage

**Files:**

- Add: `scripts/write_representative_scale_evidence.py`
- Add: `scripts/write_downstream_benchmark_bundle.py`
- Add: `scripts/import_downstream_benchmark_result.py`
- Add: `tests/fixtures/evidence_campaigns/three-domain-diagnostic.json`
- Modify: `tests/test_scale_evidence.py`
- Modify: `tests/test_downstream_benchmark.py`

- [x] **Step 1: Write failing subprocess tests for all three commands.**

  Assert successful paths print exactly one `key=path` line, invalid
  prerequisites exit non-zero without a traceback, output parent directories
  are not created implicitly outside the requested path, and existing release
  artifacts remain byte-for-byte unchanged.

- [x] **Step 2: Implement the scale-evidence command.**

  `scripts/write_representative_scale_evidence.py` accepts:

  ```python
  parser.add_argument("--campaign", type=Path, required=True)
  parser.add_argument("--output", type=Path, required=True)
  ```

  It calls `write_representative_scale_evidence(campaign_path=args.campaign, output_path=args.output)`, prints
  `representative_scale_evidence=<path>`, and exits `0` for every validated
  recommendation including `expand_representative_evidence`.

- [x] **Step 3: Implement the bundle command.**

  `scripts/write_downstream_benchmark_bundle.py` accepts:

  ```python
  parser.add_argument("--release-pack", type=Path, required=True)
  parser.add_argument("--benchmark-suite-id", required=True)
  parser.add_argument("--benchmark-suite-version", required=True)
  parser.add_argument("--primary-metric", default="task_success_rate")
  parser.add_argument("--output", type=Path, required=True)
  ```

  Version 1 exposes one bounded `task_success_rate` metric (`0.0..1.0`, higher
  is better) through the CLI. Additional metrics require programmatic protocol
  construction until a later need justifies a richer CLI format.

- [x] **Step 4: Implement the result-import command.**

  `scripts/import_downstream_benchmark_result.py` accepts:

  ```python
  parser.add_argument("--bundle", type=Path, required=True)
  parser.add_argument("--observation", type=Path, required=True)
  parser.add_argument("--output", type=Path, required=True)
  ```

  It exits `0` for `improved` and `no_detected_improvement`, exits `1` for
  `insufficient_evidence`, and always prints
  `downstream_benchmark_result=<path>` when a validated output was written.

- [x] **Step 5: Add the diagnostic campaign fixture.**

  Store only relative fixture artifact directories in the checked-in
  fixture. CLI tests must copy it into a temporary directory and rewrite those
  relative directory values to temporary three-domain artifact directories;
  production code must never special-case test paths.

- [x] **Step 6: Run the offline end-to-end sequence.**

  ```bash
  uv run python -m unittest tests.test_scale_evidence tests.test_downstream_benchmark tests.test_cli
  ```

  Expected: PASS, including campaign -> scale report -> verified release pack ->
  benchmark bundle -> imported result. The diagnostic fixture campaign must
  recommend `expand_representative_evidence`, not an activation.

- [x] **Step 7: Commit the CLI workflows.**

  ```bash
  git add scripts/write_representative_scale_evidence.py scripts/write_downstream_benchmark_bundle.py scripts/import_downstream_benchmark_result.py tests/fixtures/evidence_campaigns/three-domain-diagnostic.json tests/test_scale_evidence.py tests/test_downstream_benchmark.py
  git commit -m "feat: add offline evidence exchange commands"
  ```

### Task 7: Synchronize Documentation And Complete The Evidence Decision

**Files:**

- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/BACKEND.md`
- Modify: `docs/DATA.md`
- Modify: `docs/PRODUCT_SENSE.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/PLANS.md`
- Modify: `docs/README.md`
- Modify: `docs/exec-plans/active/README.md`
- Move: `docs/exec-plans/active/0042-representative-scale-and-downstream-evidence.md` to `docs/exec-plans/completed/0042-representative-scale-and-downstream-evidence.md`

- [x] **Step 1: Document standalone operator commands.**

  Add commands with explicit paths:

  ```bash
  uv run python scripts/write_representative_scale_evidence.py \
    --campaign artifacts/evidence-campaign/campaign.json \
    --output artifacts/evidence-campaign/representative_scale_evidence.json

  uv run python scripts/write_downstream_benchmark_bundle.py \
    --release-pack artifacts/contacts-release/dataset_release_pack.json \
    --benchmark-suite-id external_agent_tasks_v1 \
    --benchmark-suite-version external_agent_tasks_v1 \
    --output artifacts/downstream/downstream_benchmark_bundle.json

  uv run python scripts/import_downstream_benchmark_result.py \
    --bundle artifacts/downstream/downstream_benchmark_bundle.json \
    --observation artifacts/downstream/external_observation.json \
    --output artifacts/downstream/downstream_benchmark_result.json
  ```

- [x] **Step 2: Document contracts and non-claims.**

  Add canonical contract detail to `docs/DATA.md`, offline consumer ownership to
  `docs/BACKEND.md`, supporting-metric interpretation to
  `docs/PRODUCT_SENSE.md`, and the completed roadmap capability to
  `docs/ROADMAP.md`. State explicitly that fixture scale is diagnostic, external
  training is out of repository, and downstream improvement does not alter
  release admission.

- [x] **Step 3: Run focused and complete verification.**

  ```bash
  uv run python -m unittest tests.test_contracts tests.test_scale_evidence tests.test_downstream_benchmark tests.test_release_pack tests.test_profile_decisions tests.test_release_review tests.test_cli
  uv run python -m unittest
  uv run python scripts/validate_docs.py
  ```

  Expected: all commands exit `0` and report no failures.

- [x] **Step 4: Run one deterministic offline smoke workflow.**

  Use temporary or `artifacts/` inputs; record the exact commands and resulting
  statuses in this plan's `Validation Evidence` section. Expected diagnostic
  campaign recommendation: `expand_representative_evidence`. Expected synthetic
  observation import: the status implied by its baseline/treatment values,
  with an explicit statement that this is contract evidence, not a downstream
  model-quality claim.

- [x] **Step 5: Record the evidence-backed next-development decision.**

  If no real representative campaign was supplied, record that plan 0014 and
  TD-0002 remain deferred and that domain-representative generation/evidence is
  the next candidate plan. If a real campaign was supplied, copy only the
  sanitized recommendation and triggered signal names into this plan; do not
  copy raw artifacts or silently activate another plan.

- [x] **Step 6: Complete the lifecycle transition.**

  Mark every task complete, add completion date and validation evidence, move
  this file to `completed/`, set `docs/PLANS.md` Active back to none unless a
  separately approved plan exists, update the completed and docs indexes, and
  update `AGENTS.md` current implementation shape.

- [x] **Step 7: Commit the completed plan and docs.**

  ```bash
  git add README.md AGENTS.md docs/BACKEND.md docs/DATA.md docs/PRODUCT_SENSE.md docs/ROADMAP.md docs/PLANS.md docs/README.md docs/exec-plans/active/README.md docs/exec-plans/completed/0042-representative-scale-and-downstream-evidence.md
  git commit -m "docs: complete representative evidence workflow"
  ```

## Validation Commands

```bash
uv run python -m unittest tests.test_contracts tests.test_scale_evidence tests.test_downstream_benchmark tests.test_release_pack tests.test_profile_decisions tests.test_release_review tests.test_cli
uv run python -m unittest
uv run python scripts/validate_docs.py
```

The implementation must also record one offline smoke sequence using the three
standalone commands. A deterministic synthetic external result is acceptable
for contract verification but cannot be reported as actual model improvement.

## Acceptance Criteria

- The default `uv run python main.py` path writes none of the new artifacts.
- Scale evidence consumes exactly one run for each supported domain and stores
  no input directory or host path.
- All current deterministic fixture and scale-probe modes are
  `diagnostic_only`, even at or above 100 candidates.
- Only consistent non-fixture evidence may be `representative` and support an
  activation recommendation.
- Threshold observations reuse existing profile-decision report values and
  statuses; Plan 0042 does not define competing threshold behavior.
- Incomplete or identity-mismatched domain evidence recommends
  `expand_representative_evidence` through a valid report.
- Quality failures and confirmed review issues outrank infrastructure
  activation recommendations.
- Benchmark bundles require a standalone-verified release pack and bind its
  release id, hash, and byte count.
- Imported results match bundle/release/suite identity, enforce metric ranges,
  calculate deterministic deltas, and sanitize malformed inputs.
- Downstream status does not mutate manifests, samples, quality reports,
  profile decisions, dataset-release reports, release packs, or review evidence.
- No trainer, training API, credential, model weight, async worker, embedding
  provider, or external MCP dependency is added.
- Existing release-pack verification, profile decisions, review resolution,
  and default CLI behavior remain compatible.
- Focused tests, full unit tests, documentation validation, and an offline smoke
  workflow pass.

## Validation Evidence

- Focused evidence, contract, release-pack, and CLI suites passed during the
  implementation RED-GREEN cycles.
- Offline smoke commands wrote a diagnostic three-domain report with
  `expand_representative_evidence`, a verified-pack benchmark bundle, and a
  synthetic imported result with `improved`. The synthetic status verifies the
  exchange contract only and is not a downstream model-quality claim.
- No real representative campaign was supplied. Plan 0014 and TD-0002 remain
  deferred; domain-representative generation and evidence is the next candidate
  development direction.
- Focused completion verification passed `212` tests; the full suite passed
  `548` tests; `uv run python scripts/validate_docs.py` passed. All commands
  exited `0` on 2026-07-11.

## Risks And Mitigations

- **Fixture inflation may masquerade as production pressure.** Classify every
  existing deterministic mode as diagnostic and never infer representativeness
  from candidate count alone.
- **An aggregate report may duplicate threshold logic.** Read threshold values
  and decision statuses from validated profile-decision reports; aggregate
  signals without recomputing them.
- **Cross-run artifacts may be mixed accidentally.** Match domain, dataset,
  profile, release, suite, and hash identities before producing evidence.
- **External results may leak operational data.** Enforce exact keys and opaque
  aliases; reject logs, commands, paths, credentials, and arbitrary metadata.
- **A synthetic test result may be mistaken for model evidence.** Label it as
  deterministic contract evidence in tests, docs, and completion notes.
- **A downstream delta may be overclaimed.** Report only the declared metric
  comparison and keep `proves_causality` false.
- **Plan completion may be blocked on external training.** External training is
  not an acceptance criterion; deterministic bundle/result exchange is. Real
  results are optional operational evidence and require no repository mutation.
