# Plan 0023: Evaluation Quality Ratchet and Profile Promotion Gates

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status

Completed on 2026-05-31.

## Goal

Tighten the held-out evaluation and profile decision boundary so a run profile
can be promoted only when the overall benchmark, per-capability benchmark
slices, and quality gates all pass, while async orchestration and semantic
duplicate detection remain deferred until their explicit scale triggers are met.

## Architecture

This plan builds on the opt-in reports from plan 0022. It keeps candidate
generation, candidate acceptance, duplicate admission, source governance,
sandbox admission, and the default synchronous CLI unchanged.

The change is a reporting-contract ratchet:

- `synthesis.evaluation` keeps owning held-out benchmark execution and adds
  capability-level thresholds and explicit expected-failure semantics for the
  missing-contact case.
- `synthesis.profile_decisions` keeps owning profile-level decisions and adds a
  separate promotion decision above the existing MVP quality floor.
- `synthesis.contracts` keeps owning schema validation and rejects malformed
  capability threshold and promotion decision records.

## Tech Stack

- Python standard library: `dataclasses`, `json`, `pathlib`, `tempfile`, and
  `unittest`.
- Existing modules: `synthesis.evaluation`, `synthesis.profile_decisions`,
  `synthesis.contracts`, `synthesis.verification`, and `synthesis.execution`.
- Existing scripts: `scripts/evaluation_report.py`,
  `scripts/profile_decision_report.py`, and `scripts/validate_docs.py`.
- Verification through `uv run python -m unittest` and
  `uv run python scripts/validate_docs.py`.

---

## Basis

- [../../PLANS.md](../../PLANS.md) had no active implementation plan after
  [../completed/0022-held-out-evaluation-and-profile-benchmarking.md](../completed/0022-held-out-evaluation-and-profile-benchmarking.md).
- The latest opt-in scale-probe evaluation artifacts under
  `artifacts/foundation-scale-probe-evaluation/` show:
  - `total_candidates: 25`;
  - `runtime_seconds: 0.03317574970424175`;
  - `async_orchestration.status: defer`;
  - `semantic_duplicate_detection.status: defer`;
  - `mvp_quality_floor.status: passed`;
  - held-out `pass_rate: 0.8`;
  - `missing_contact.pass_rate: 0.0`.
- [../deferred/0014-async-local-orchestration-with-durable-queues.md](../deferred/0014-async-local-orchestration-with-durable-queues.md)
  remains deferred until single runs exceed about 10 minutes, reach about 100+
  candidates, hit painful recovery costs, or require per-role/per-provider cost
  attribution.
- [../tech-debt/README.md](../tech-debt/README.md) keeps `TD-0002` semantic
  duplicate detection unresolved until dataset volume or curriculum benchmark
  signals justify it.
- [../../DATA.md](../../DATA.md) already documents `evaluation_report_v1` and
  `profile_decision_report_v1`, but the current profile decision is too coarse:
  an overall held-out pass rate can pass while a capability slice is completely
  failing.

## Why This Plan Now

Plan 0022 added the missing benchmark layer, and that benchmark immediately
exposed a weak decision boundary: the profile passes the overall MVP floor while
the missing-contact capability fails its only held-out task.

Starting async orchestration now would scale a quality signal that is only just
above the aggregate threshold. Implementing semantic duplicate detection now is
also premature because the profile has only 25 candidates, even though its exact
duplicate rate is already worth watching. The next narrow step is to make the
evaluation and promotion decisions stricter and more diagnostic before spending
engineering effort on scale infrastructure.

## Scope

- Define expected-outcome semantics for held-out tasks:
  - standard tasks pass when execution and verification pass;
  - expected-failure tasks pass only when they fail in a controlled, expected
    way;
  - unexpected exceptions or mismatched failure causes remain failures.
- Convert `heldout_contacts_missing_contact` from an accidental failed
  benchmark item into an explicit controlled-failure task.
- Add capability-level thresholds to `evaluation_report_v1`, preserving backward
  compatibility for reports that only carry the existing aggregate thresholds.
- Make `evaluation_report.decision.status` fail when any required capability
  slice misses its threshold.
- Add a profile-level `profile_promotion` decision to
  `profile_decision_report_v1`, separate from `mvp_quality_floor`.
- Add a semantic-duplicate watch signal without activating `TD-0002` at low
  volume:
  - keep `semantic_duplicate_detection.status: defer` until the existing volume
    threshold is met;
  - include watch rationale when the exact duplicate rate is at or above the
    configured exact-rate threshold but candidate count is below the volume
    threshold.
- Update canonical docs to describe capability thresholds, expected-failure
  held-out tasks, profile promotion, and the distinction between watch/defer and
  activate decisions.

## Out of Scope

- Implementing async orchestration, durable queues, cancellation, resumption, or
  per-role cost tracking from plan 0014.
- Implementing semantic duplicate detection, embeddings, vector stores, local
  similarity models, or near-duplicate admission gates from `TD-0002`.
- Changing candidate generation, candidate acceptance, exact duplicate
  admission, verifier semantics for normal generated candidates, source
  governance, sandbox admission, or default CLI output.
- Adding dashboards, REST APIs, external MCP servers, distributed workers,
  browser automation, model training, or downstream fine-tuning.
- Claiming model-quality improvement from synthetic data.

## Contract Design

### Held-out Task Outcomes

Add an explicit expectation field to `HeldoutTask`:

```python
@dataclass(frozen=True)
class HeldoutTask:
    task_id: str
    candidate: CandidateTask
    capability_tags: tuple[str, ...]
    expected_outcome: str = "passed"
    expected_failure_cause: str | None = None
```

Supported `expected_outcome` values:

- `passed`: current behavior. Execution and verification must pass.
- `controlled_failure`: execution or verification must fail with
  `expected_failure_cause`.

For the missing-contact task:

```python
HeldoutTask(
    task_id="heldout_contacts_missing_contact",
    capability_tags=("missing_contact",),
    expected_outcome="controlled_failure",
    expected_failure_cause="verification_failed",
    candidate=CandidateTask(...),
)
```

The resulting task record should be:

```json
{
  "task_id": "heldout_contacts_missing_contact",
  "capability_tags": ["missing_contact"],
  "status": "passed",
  "failure_cause": null,
  "expected_outcome": "controlled_failure",
  "observed_failure_cause": "verification_failed"
}
```

### Evaluation Thresholds

Extend `EvaluationThresholds`:

```python
@dataclass(frozen=True)
class EvaluationThresholds:
    mvp_min_heldout_pass_rate: float = 0.8
    max_regression_count: int = 0
    min_capability_pass_rates: Mapping[str, float] = field(
        default_factory=lambda: {
            "contact_lookup": 1.0,
            "state_change": 1.0,
            "branching": 1.0,
            "missing_contact": 1.0,
        }
    )
```

The serialized `thresholds` object should include:

```json
{
  "mvp_min_heldout_pass_rate": 0.8,
  "max_regression_count": 0,
  "min_capability_pass_rates": {
    "contact_lookup": 1.0,
    "state_change": 1.0,
    "branching": 1.0,
    "missing_contact": 1.0
  }
}
```

The evaluation decision should include capability threshold reasons:

```json
{
  "status": "passed",
  "reasons": [
    "pass_rate 1.0 is at or above mvp_min_heldout_pass_rate 0.8",
    "regressed 0 is at or below max_regression_count 0",
    "capability missing_contact pass_rate 1.0 is at or above minimum 1.0"
  ],
  "triggered_by": [
    "pass_rate",
    "regressed",
    "capability:contact_lookup",
    "capability:state_change",
    "capability:branching",
    "capability:missing_contact"
  ]
}
```

### Profile Promotion Decision

Extend `profile_decision_report_v1.decisions` with:

```json
{
  "profile_promotion": {
    "status": "passed",
    "reasons": [
      "mvp_quality_floor passed",
      "held-out evaluation passed",
      "async_orchestration remains deferred by scale thresholds",
      "semantic_duplicate_detection remains deferred by volume threshold"
    ],
    "triggered_by": [
      "mvp_quality_floor",
      "heldout_evaluation",
      "scale_deferral"
    ]
  }
}
```

Allowed statuses are:

- `passed`: profile can be treated as promotable for the current local,
  synchronous MVP scope.
- `failed`: quality or held-out evaluation failed.
- `blocked`: scale or duplicate decisions require implementation work before
  promotion.
- `insufficient_evidence`: required quality or evaluation fields are missing or
  malformed.

## File Map

- Modify `synthesis/evaluation.py`
  - Add expected-outcome fields to `HeldoutTask`.
  - Treat missing-contact as controlled expected failure.
  - Add capability pass-rate thresholds and decision reasons.
  - Preserve existing CLI and default report filename behavior.
- Modify `synthesis/contracts.py`
  - Validate optional `expected_outcome` and `observed_failure_cause` in
    evaluation task results.
  - Validate `thresholds.min_capability_pass_rates`.
  - Require and validate `decisions.profile_promotion` in profile decision
    reports while keeping existing decisions intact.
- Modify `synthesis/profile_decisions.py`
  - Add semantic duplicate watch rationale.
  - Add `_profile_promotion_decision()`.
  - Include held-out capability failures in promotion reasons through the
    existing evaluation summary.
- Modify `scripts/profile_decision_report.py`
  - No new CLI flags expected; ensure the report writer serializes the extended
    decision contract when optional evaluation input is supplied.
- Modify `tests/test_evaluation.py`
  - Cover controlled-failure missing-contact pass semantics.
  - Cover failed capability threshold decisions.
  - Cover serialized threshold contract.
- Modify `tests/test_profile_decisions.py`
  - Cover promotion passed, failed, blocked, insufficient-evidence, and semantic
    duplicate watch cases.
- Modify `tests/test_contracts.py`
  - Cover new evaluation task result fields, capability thresholds, and
    `profile_promotion` decision validation.
- Modify `docs/DATA.md`
  - Document expected-failure held-out tasks, capability thresholds, semantic
    duplicate watch rationale, and profile promotion.
- Modify `docs/BACKEND.md`
  - Document the updated opt-in evaluation/profile decision step and state that
    plan 0014 remains deferred.
- Modify `docs/ROADMAP.md`, `docs/PLANS.md`, and plan bucket indexes when this
  plan is completed.

## Implementation Tasks

### Task 1: Ratchet Held-out Evaluation Semantics

**Files:**

- Modify: `synthesis/evaluation.py`
- Modify: `tests/test_evaluation.py`
- Modify: `tests/test_contracts.py`

- [x] Add failing tests for controlled-failure missing-contact semantics.

  In `tests/test_evaluation.py`, change
  `test_generated_report_counts_slices_and_validates` expectations so the
  missing-contact task is counted as passed:

  ```python
  self.assertEqual(report["counts"]["passed"], 5)
  self.assertEqual(report["counts"]["failed"], 0)
  self.assertEqual(report["rates"]["pass_rate"], 1.0)
  self.assertEqual(report["capability_slices"]["missing_contact"]["passed"], 1)
  self.assertEqual(report["capability_slices"]["missing_contact"]["failed"], 0)
  task_result = {
      result["task_id"]: result for result in report["task_results"]
  }["heldout_contacts_missing_contact"]
  self.assertEqual(task_result["status"], "passed")
  self.assertEqual(task_result["expected_outcome"], "controlled_failure")
  self.assertEqual(task_result["observed_failure_cause"], "verification_failed")
  ```

- [x] Run the focused failing test.

  ```bash
  uv run python -m unittest tests.test_evaluation.HeldoutEvaluationTest.test_generated_report_counts_slices_and_validates
  ```

  Expected result before implementation: failure showing the report still counts
  `missing_contact` as failed.

- [x] Implement expected-outcome fields and controlled-failure handling.

  Add `expected_outcome` and `expected_failure_cause` to `HeldoutTask`, add
  `expected_outcome` and `observed_failure_cause` to `HeldoutTaskResult.export()`,
  and change `_run_suite()` so an expected `verification_failed` result for
  `heldout_contacts_missing_contact` is exported as a passed controlled failure.

- [x] Run the focused test again.

  ```bash
  uv run python -m unittest tests.test_evaluation.HeldoutEvaluationTest.test_generated_report_counts_slices_and_validates
  ```

  Expected result after implementation: pass.

### Task 2: Add Capability Thresholds to Evaluation Reports

**Files:**

- Modify: `synthesis/evaluation.py`
- Modify: `synthesis/contracts.py`
- Modify: `tests/test_evaluation.py`
- Modify: `tests/test_contracts.py`

- [x] Add a failing test that a capability threshold miss fails the evaluation
  decision.

  In `tests/test_evaluation.py`, add:

  ```python
  def test_capability_threshold_miss_fails_decision(self) -> None:
      from synthesis.evaluation import EvaluationThresholds, build_evaluation_report

      with tempfile.TemporaryDirectory() as tmpdir:
          manifest_path, quality_report_path = _write_inputs(Path(tmpdir))
          report = build_evaluation_report(
              manifest_path=manifest_path,
              quality_report_path=quality_report_path,
              thresholds=EvaluationThresholds(
                  min_capability_pass_rates={"missing_contact": 1.01}
              ),
          )

      self.assertEqual(report["decision"]["status"], "failed")
      self.assertIn(
          "capability missing_contact pass_rate 1.0 is below minimum 1.01",
          report["decision"]["reasons"],
      )
  ```

- [x] Add contract tests for `thresholds.min_capability_pass_rates`.

  Extend `_valid_evaluation_report()` in `tests/test_contracts.py` with
  `min_capability_pass_rates`, then add a test that rejects a non-numeric value:

  ```python
  report = _valid_evaluation_report()
  report["thresholds"]["min_capability_pass_rates"] = {"missing_contact": "high"}
  with self.assertRaisesRegex(ContractValidationError, "min_capability_pass_rates"):
      validate_evaluation_report_record(report)
  ```

- [x] Run the focused tests and verify they fail for missing fields or logic.

  ```bash
  uv run python -m unittest tests.test_evaluation tests.test_contracts
  ```

- [x] Implement `EvaluationThresholds.min_capability_pass_rates` and update
  `_decision()`.

  The decision should fail when any listed capability is absent or has a
  `pass_rate` below its threshold. Missing capability slices should produce
  `insufficient_evidence`, not `passed`.

- [x] Update `validate_evaluation_report_record()` to validate the optional
  threshold mapping.

  Keep old reports valid when `min_capability_pass_rates` is absent, but reject
  malformed keys or non-numeric threshold values when it is present.

- [x] Run the focused tests again.

  ```bash
  uv run python -m unittest tests.test_evaluation tests.test_contracts
  ```

  Expected result: pass.

### Task 3: Add Profile Promotion Decision

**Files:**

- Modify: `synthesis/profile_decisions.py`
- Modify: `synthesis/contracts.py`
- Modify: `tests/test_profile_decisions.py`
- Modify: `tests/test_contracts.py`

- [x] Add failing tests for promotion decisions.

  In `tests/test_profile_decisions.py`, add cases for:

  ```python
  self.assertEqual(report["decisions"]["profile_promotion"]["status"], "passed")
  ```

  when quality and evaluation both pass;

  ```python
  self.assertEqual(report["decisions"]["profile_promotion"]["status"], "failed")
  ```

  when `mvp_quality_floor` fails or the supplied evaluation report fails;

  ```python
  self.assertEqual(
      report["decisions"]["profile_promotion"]["status"],
      "insufficient_evidence",
  )
  ```

  when the supplied evaluation report is malformed.

- [x] Add a blocked promotion test for activated scale work.

  Build a profile decision report with `total=100` so async orchestration
  activates, then assert:

  ```python
  self.assertEqual(report["decisions"]["async_orchestration"]["status"], "activate")
  self.assertEqual(report["decisions"]["profile_promotion"]["status"], "blocked")
  ```

- [x] Update `tests/test_contracts.py` so valid profile decision reports include
  `profile_promotion`, and add a test that rejects an unsupported promotion
  status.

- [x] Run the focused tests and verify they fail before implementation.

  ```bash
  uv run python -m unittest tests.test_profile_decisions tests.test_contracts
  ```

- [x] Implement `_profile_promotion_decision()`.

  Rules:

  - `insufficient_evidence` if `mvp_quality_floor` or supplied evaluation is
    insufficient.
  - `failed` if `mvp_quality_floor` failed or supplied evaluation failed.
  - `blocked` if async orchestration or semantic duplicate detection is
    activated.
  - `passed` otherwise.

- [x] Add `profile_promotion` to the `decisions` object returned by
  `build_profile_decision_report()`.

- [x] Update `validate_profile_decision_report_record()` to require and validate
  `profile_promotion`.

- [x] Run the focused tests again.

  ```bash
  uv run python -m unittest tests.test_profile_decisions tests.test_contracts
  ```

  Expected result: pass.

### Task 4: Add Semantic Duplicate Watch Rationale

**Files:**

- Modify: `synthesis/profile_decisions.py`
- Modify: `tests/test_profile_decisions.py`

- [x] Add a failing test for low-volume duplicate watch behavior.

  Use 25 candidates and an exact duplicate rate at or above the configured
  threshold:

  ```python
  report = build_profile_decision_report(
      **_report_inputs(
          total=25,
          accepted=10,
          rejected=15,
          quality_duplicates=10,
      )
  )
  decision = report["decisions"]["semantic_duplicate_detection"]
  self.assertEqual(decision["status"], "defer")
  self.assertIn("exact_duplicate_rate", decision["triggered_by"])
  self.assertIn("watch", decision["reasons"][-1])
  ```

- [x] Run the focused test and verify it fails before implementation.

  ```bash
  uv run python -m unittest tests.test_profile_decisions.ProfileDecisionReportTest.test_semantic_duplicate_detection_activates_only_when_volume_and_rate_meet_thresholds
  ```

- [x] Update `_semantic_duplicate_decision()`.

  Preserve `status: defer` when volume is below threshold, but retain
  `exact_duplicate_rate` in `triggered_by` and add a watch reason when the rate
  threshold is met.

- [x] Run profile decision tests.

  ```bash
  uv run python -m unittest tests.test_profile_decisions
  ```

### Task 5: Update Canonical Docs

**Files:**

- Modify: `docs/DATA.md`
- Modify: `docs/BACKEND.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/PLANS.md`
- Modify: `docs/exec-plans/active/README.md`
- Modify after completion: move this plan to `docs/exec-plans/completed/`

- [x] Update `docs/DATA.md`.

  Document:

  - held-out expected outcomes;
  - optional `task_results[].expected_outcome`;
  - optional `task_results[].observed_failure_cause`;
  - `thresholds.min_capability_pass_rates`;
  - `decisions.profile_promotion`;
  - low-volume semantic duplicate watch semantics.

- [x] Update `docs/BACKEND.md`.

  State that opt-in profile decision reporting now separates MVP quality floor
  from profile promotion and still keeps 0014 deferred unless scale triggers are
  met.

- [x] Update `docs/ROADMAP.md`.

  Mark plan 0023 as the next quality-ratchet step before async orchestration.

- [x] After implementation is accepted, move this file from `active/` to
  `completed/`, set the completion date, and update `docs/PLANS.md` plus
  `docs/exec-plans/active/README.md`.

### Task 6: End-to-End Verification

**Files:**

- Runtime output under `artifacts/foundation-scale-probe-evaluation/`
- No source edits beyond implementation and docs files above.

- [x] Run the focused report command.

  ```bash
  uv run python main.py --run-profile tests/fixtures/run_profiles/foundation-scale-probe-25.json --write-evaluation-report --write-profile-decision-report --output-dir artifacts/foundation-scale-probe-evaluation
  ```

  Expected result:

  - `evaluation_report.json` exists;
  - `profile_decision_report.json` exists;
  - `evaluation_report.counts.passed == 5`;
  - `evaluation_report.capability_slices.missing_contact.pass_rate == 1.0`;
  - `profile_decision_report.decisions.profile_promotion.status == "passed"`;
  - `profile_decision_report.decisions.async_orchestration.status == "defer"`;
  - `profile_decision_report.decisions.semantic_duplicate_detection.status == "defer"`.

- [x] Run documentation validation.

  ```bash
  uv run python scripts/validate_docs.py
  ```

  Expected result: `Documentation validation passed.`

- [x] Run the full test suite.

  ```bash
  uv run python -m unittest
  ```

  Expected result: all tests pass.

## Acceptance Criteria

- `evaluation_report_v1` can distinguish normal pass tasks from controlled
  expected-failure tasks.
- `heldout_contacts_missing_contact` is a passing controlled-failure benchmark
  when the missing contact fails through the expected verifier path.
- Capability-level thresholds are serialized, validated, and enforced.
- A capability slice cannot fail completely while the evaluation decision still
  passes.
- `profile_decision_report_v1` contains `profile_promotion` in addition to the
  existing async, semantic duplicate, and MVP quality-floor decisions.
- Profile promotion can pass, fail, block, or report insufficient evidence with
  deterministic reasons.
- Low-volume exact duplicate pressure is visible as a watch rationale without
  activating semantic duplicate detection.
- Plan 0014 remains deferred unless scale triggers are met.
- `TD-0002` remains unresolved unless future volume or benchmark evidence
  justifies a separate semantic duplicate detection plan.
- Documentation validation and the full unit suite pass.

## Risks

- **Backward compatibility:** Existing `evaluation_report_v1` fixtures may not
  contain new optional fields. Keep new task-result fields optional in contract
  validation unless the current report writer emits them.
- **Semantic ambiguity:** Expected failure must mean controlled, expected failure,
  not arbitrary exception swallowing. Record `observed_failure_cause` so the
  pass is auditable.
- **Decision coupling:** Keep `mvp_quality_floor` as a production quality gate
  and `profile_promotion` as the higher-level release decision. Do not overload
  one status with both meanings.
- **Premature scale work:** Do not use this plan to implement async
  orchestration or semantic duplicate detection. It should make those future
  decisions better evidenced.
