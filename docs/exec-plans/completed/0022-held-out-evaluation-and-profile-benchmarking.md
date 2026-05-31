# Plan 0022: Held-out Evaluation and Profile Benchmarking

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

## Status

Planned on 2026-05-31. Completed on 2026-05-31.

## Goal

Add an opt-in held-out evaluation layer that benchmarks a generated dataset or
run profile against independent deterministic tasks, producing a sanitized
`evaluation_report.json` artifact that can inform profile decisions before async
orchestration, semantic duplicate detection, or larger-scale generation are
activated.

## Architecture

This plan adds a reporting and evaluation boundary above existing dataset
artifacts. It does not change candidate generation, candidate acceptance,
verifier semantics, source governance, sandbox admission, profile attribution,
or default synchronous CLI behavior.

The first implementation should use a deterministic contacts held-out suite. The
suite is separate from generated candidates and scale probes: it is a small,
fixed benchmark of expected capabilities, executed through the same local
environment, tool registry, policy execution, and verifier contracts. The report
records pass/fail results, capability slices, regressions against an optional
parent evaluation report, and sanitized dataset/profile identity.

## Tech Stack

- Python standard library: `dataclasses`, `json`, `pathlib`, `time`, and
  `unittest`.
- Existing modules: `synthesis.environments`, `synthesis.tools`,
  `synthesis.execution`, `synthesis.verification`, `synthesis.datasets`,
  `synthesis.contracts`, and `synthesis.profile_decisions`.
- Existing validation through `scripts/validate_docs.py` and
  `uv run python -m unittest`.

---

## Basis

- [../../PLANS.md](../../PLANS.md) has no active implementation plan before this
  plan.
- [../deferred/0014-async-local-orchestration-with-durable-queues.md](../deferred/0014-async-local-orchestration-with-durable-queues.md)
  remains deferred until single runs exceed about 10 minutes or 100+
  candidates.
- [../tech-debt/README.md](../tech-debt/README.md) keeps `TD-0002` semantic
  duplicate detection unresolved until dataset volume or curriculum-benchmark
  signals justify implementation.
- [0020-profile-decision-gates-and-benchmark-reporting.md](0020-profile-decision-gates-and-benchmark-reporting.md)
  added profile decision reports, but those decisions currently rely on
  internal production artifacts: success rate, executable rate, exact duplicate
  rate, infrastructure/source-policy rejection rates, runtime, and profile
  slices.
- [0021-candidate-isolation-and-deterministic-merge.md](0021-candidate-isolation-and-deterministic-merge.md)
  made candidate processing deterministic and isolated enough that an evaluation
  runner can reuse existing environment, tool, policy, and verifier boundaries
  without mutating dataset assembly behavior.
- [../../PRODUCT_SENSE.md](../../PRODUCT_SENSE.md) defines the north-star metric
  as accepted verified trajectories per dollar at a target quality floor, and it
  lists downstream improvement on held-out Agent tasks as a supporting metric.
- [../../DATA.md](../../DATA.md) states that new dataset versions should be
  compared to parent versions using quality metrics, coverage, cost, and
  held-out task performance when available.

## Why This Plan Now

The project can already produce accepted samples and profile decision reports,
but those reports are still production-line evidence. They answer whether the
generated candidates passed internal gates. They do not answer whether the
dataset/profile is improving on a stable independent benchmark.

This plan adds that missing benchmark layer before the project spends effort on
scale infrastructure. Async orchestration makes runs faster and recoverable;
semantic duplicate detection reduces near-duplicate data. Both are easier to
prioritize once there is a stable evaluation report showing whether current
generation quality is actually improving or regressing.

## Scope

- Define a deterministic held-out evaluation contract with:
  - suite id, suite version, dataset version, optional sanitized run-profile
    summary, and optional parent evaluation input;
  - fixed held-out task records that are not sourced from generated candidates;
  - capability tags such as `contact_lookup`, `state_change`, `branching`, and
    `missing_contact`;
  - per-task pass/fail records with sanitized failure causes;
  - aggregate pass rate, failure counts, capability slices, and regression
    counts against an optional parent evaluation report.
- Add `synthesis.evaluation` as the domain-specific held-out evaluation module.
- Add `scripts/evaluation_report.py` as a thin CLI over the report builder.
- Add a `main.py` opt-in flag, likely `--write-evaluation-report`, that writes
  `evaluation_report.json` after the normal synchronous pipeline completes.
- Add manifest artifact plumbing only when an evaluation report is explicitly
  requested.
- Extend profile decision reporting so it can read an optional evaluation report
  and include held-out evaluation status in the MVP quality-floor rationale.
- Keep all report data sanitized: no raw local profile paths, raw contacts
  payload rows, contact emails beyond existing synthetic fixture values, prompts,
  provider payloads, headers, API keys, or arbitrary profile JSON.
- Update canonical docs and plan indexes for the active plan and implemented
  artifact contract.

## Out of Scope

- Training or fine-tuning a downstream model.
- Claiming downstream model improvement from synthetic data.
- Implementing async orchestration, durable queues, cancellation, resumption, or
  per-role async cost tracking from plan 0014.
- Implementing semantic duplicate detection from `TD-0002`.
- Adding embeddings, vector stores, local models, dashboards, REST APIs, browser
  automation, external queues, distributed workers, or monitoring exporters.
- Enabling external MCP servers, generated environment/tool/verifier handlers,
  arbitrary file ingestion, or user-provided executable packages.
- Changing candidate acceptance behavior, duplicate gate semantics, existing
  quality report schema, source governance policy, sandbox admission policy, or
  default CLI output.

## Evaluation Contract

`evaluation_report.json` should use `schema_version: evaluation_report_v1`.

```json
{
  "schema_version": "evaluation_report_v1",
  "dataset_version": "dataset_foundation_scale_probe_25",
  "suite": {
    "suite_id": "contacts_heldout_v1",
    "suite_version": "contacts_heldout_v1",
    "task_count": 5
  },
  "profile": {
    "schema_version": "run_profile_v1",
    "profile_id": "foundation_scale_probe_25",
    "generation_mode": "deterministic_scale_probe",
    "config_hash": "sha256:..."
  },
  "inputs": {
    "manifest_path": "manifest.json",
    "quality_report_path": "quality_report.json",
    "parent_evaluation_report_path": null
  },
  "counts": {
    "total": 5,
    "passed": 4,
    "failed": 1,
    "regressed": 0,
    "improved": 0,
    "unchanged": 5
  },
  "rates": {
    "pass_rate": 0.8
  },
  "capability_slices": {
    "contact_lookup": {"total": 2, "passed": 2, "failed": 0, "pass_rate": 1.0},
    "state_change": {"total": 1, "passed": 1, "failed": 0, "pass_rate": 1.0},
    "branching": {"total": 1, "passed": 1, "failed": 0, "pass_rate": 1.0},
    "missing_contact": {"total": 1, "passed": 0, "failed": 1, "pass_rate": 0.0}
  },
  "task_results": [
    {
      "task_id": "heldout_contacts_lookup_alice",
      "capability_tags": ["contact_lookup"],
      "status": "passed",
      "failure_cause": null
    }
  ],
  "thresholds": {
    "mvp_min_heldout_pass_rate": 0.8,
    "max_regression_count": 0
  },
  "decision": {
    "status": "passed",
    "reasons": [
      "pass_rate 0.8 is at or above mvp_min_heldout_pass_rate 0.8",
      "regressed 0 is at or below max_regression_count 0"
    ],
    "triggered_by": ["pass_rate", "regressed"]
  }
}
```

The exact held-out task count may change during implementation, but the first
suite must include at least:

- a successful single-step contact lookup;
- a successful state-changing follow-up task;
- a successful branching/fallback task;
- a negative or missing-contact case that verifies controlled failure behavior;
- one task whose expected result differs from the scale-probe duplicate pattern
  so the suite is not merely replaying generated candidate fixtures.

Decision status rules:

- `decision.status` is `passed` when held-out pass rate is at or above
  `mvp_min_heldout_pass_rate` and regression count is at or below
  `max_regression_count`.
- `decision.status` is `failed` when either threshold is missed.
- `decision.status` is `insufficient_evidence` when required counts, rates, or
  task results are absent or malformed.
- Parent comparison is optional. Without a parent report, regression/improvement
  counts should be `0` and `unchanged` should equal total task count only when
  every task has a current result; the report should record that no parent
  comparison was supplied.

## File Map

- Create `synthesis/evaluation.py`:
  - define `HeldoutTask`, `HeldoutTaskResult`, `EvaluationThresholds`, and
    report-building functions;
  - define the deterministic contacts held-out suite;
  - execute held-out tasks through existing environment, registry, policy, and
    verifier boundaries;
  - build sanitized `evaluation_report_v1` mappings;
  - load optional parent evaluation reports and compute task-level regressions.
- Create `scripts/evaluation_report.py`:
  - parse `--manifest`, `--quality-report`, optional
    `--parent-evaluation-report`, and optional `--output`;
  - call `synthesis.evaluation`;
  - write `evaluation_report.json`.
- Modify `synthesis/contracts.py`:
  - allow `manifest.artifacts.evaluation_report`;
  - add `validate_evaluation_report_record()`.
- Modify `synthesis/datasets.py`:
  - add a narrow helper to attach `evaluation_report` to manifest artifacts
    after an opt-in report is written.
- Modify `synthesis/profile_decisions.py`:
  - optionally load and summarize `evaluation_report.json`;
  - include held-out pass/fail evidence in the MVP quality-floor decision when
    an evaluation report is supplied;
  - keep existing behavior unchanged when no evaluation report is supplied.
- Modify `scripts/profile_decision_report.py`:
  - accept optional `--evaluation-report`.
- Modify `main.py`:
  - add `--write-evaluation-report`;
  - write the report after `run_foundation_pipeline()` completes;
  - attach the report to manifest artifacts only for opt-in runs;
  - pass the evaluation report path into profile decision reporting when both
    reports are requested.
- Add `tests/test_evaluation.py`:
  - cover held-out suite construction, deterministic execution, report
    validation, capability slices, parent regression comparison, sanitization,
    and CLI writing.
- Modify `tests/test_contracts.py`:
  - cover evaluation report validation and manifest artifact admission.
- Modify `tests/test_cli.py`:
  - cover `--write-evaluation-report` for deterministic profile runs;
  - cover combined `--write-evaluation-report` and
    `--write-profile-decision-report` behavior.
- Modify `tests/test_profile_decisions.py`:
  - cover optional held-out evidence in the MVP quality-floor decision;
  - prove legacy reports without evaluation input remain stable.
- Update docs after implementation:
  - [../../DATA.md](../../DATA.md) with `evaluation_report_v1`;
  - [../../BACKEND.md](../../BACKEND.md) with the opt-in evaluation step;
  - [../../ROADMAP.md](../../ROADMAP.md) with the completed held-out evaluation
    step before async orchestration;
  - [../../PLANS.md](../../PLANS.md), [README.md](../../../README.md), and
    [AGENTS.md](../../../AGENTS.md) when the plan is completed.

## Implementation Tasks

### Task 1: Define Evaluation Contracts and Validator

- [x] Add `validate_evaluation_report_record()` to `synthesis.contracts`.
- [x] Allow `evaluation_report` in manifest artifact validation.
- [x] Add tests in `tests/test_contracts.py` for:
  - a minimal valid `evaluation_report_v1`;
  - malformed schema version rejection;
  - invalid counts/rates rejection;
  - invalid task result status rejection;
  - manifest artifact admission for `evaluation_report`.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_contracts
  ```

  Expected result: contract tests pass.

### Task 2: Build the Deterministic Held-out Suite

- [x] Create `synthesis/evaluation.py` with immutable records for held-out tasks,
  task results, thresholds, and report inputs.
- [x] Add a `contacts_heldout_v1` suite with at least the five required task
  types listed in the Evaluation Contract section.
- [x] Execute suite tasks through the existing contacts environment and tool
  registry. Reuse existing policy and verifier contracts where possible instead
  of adding a second execution model.
- [x] Add tests in `tests/test_evaluation.py` proving:
  - suite ids and task ids are stable;
  - every task has at least one capability tag;
  - report counts equal task result totals;
  - capability slices are deterministic;
  - report validation accepts the generated report.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_evaluation
  ```

  Expected result: evaluation tests pass.

### Task 3: Add Parent Evaluation Comparison

- [x] Add optional parent evaluation loading and comparison in
  `synthesis.evaluation`.
- [x] Compare matching task ids by current and parent status.
- [x] Count `regressed` when a parent-passed task now fails.
- [x] Count `improved` when a parent-failed task now passes.
- [x] Count `unchanged` when matching task ids keep the same status.
- [x] Keep missing parent task ids visible in sanitized comparison details
  without failing report generation.
- [x] Add tests for regressed, improved, unchanged, and missing-parent-task
  cases.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_evaluation
  ```

  Expected result: parent comparison tests pass.

### Task 4: Add the Standalone Evaluation CLI

- [x] Create `scripts/evaluation_report.py`.
- [x] Accept `--manifest`, `--quality-report`, optional
  `--parent-evaluation-report`, and optional `--output`.
- [x] Write `evaluation_report.json` next to the manifest when `--output` is
  omitted.
- [x] Ensure the CLI writes sanitized relative artifact input names, not absolute
  local paths.
- [x] Add tests proving the CLI writes a valid report and rejects malformed input
  paths with a non-zero exit code.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_evaluation
  ```

  Expected result: CLI tests pass.

### Task 5: Wire Opt-in Pipeline Reporting

- [x] Add a helper in `synthesis.datasets` to attach
  `evaluation_report.json` to manifest artifacts after the report is written.
- [x] Add `--write-evaluation-report` to `main.py`.
- [x] Record evaluation report path in stdout only when the flag is supplied.
- [x] Preserve default `uv run python main.py` output and manifest artifacts
  when the flag is absent.
- [x] Add CLI tests for:
  - default run does not write `evaluation_report.json`;
  - deterministic profile run with `--write-evaluation-report` writes and
    references the report;
  - profile-local source runs do not leak local paths or source payloads into
    the report.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_cli tests.test_evaluation
  ```

  Expected result: CLI and evaluation tests pass.

### Task 6: Feed Evaluation Evidence into Profile Decisions

- [x] Add optional evaluation-report input to `synthesis.profile_decisions`.
- [x] Keep existing profile decision output stable when no evaluation report is
  supplied.
- [x] When an evaluation report is supplied, include held-out pass rate,
  regression count, and evaluation decision status in the observed section or a
  dedicated `evaluation` section.
- [x] Update the MVP quality-floor decision so a failed evaluation report causes
  `mvp_quality_floor.status == "failed"` even when internal success and
  executable rates pass.
- [x] Add tests for:
  - evaluation-passed report keeps MVP passed;
  - evaluation-failed report fails MVP;
  - malformed evaluation report produces `insufficient_evidence`;
  - legacy reports remain byte-for-byte stable where existing tests assert
    fields.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_profile_decisions tests.test_evaluation
  ```

  Expected result: profile decision tests pass.

### Task 7: Update Canonical Docs and Plan State

- [x] Update `docs/DATA.md` with the implemented `evaluation_report_v1`
  contract.
- [x] Update `docs/BACKEND.md` with the opt-in evaluation-report step after
  dataset artifact writing and before optional profile decision reporting.
- [x] Update `docs/ROADMAP.md` to mark held-out evaluation implemented before
  async orchestration.
- [x] Update `docs/README.md`, `docs/PLANS.md`, and execution-plan bucket
  indexes when this plan moves from active to completed.
- [x] Run:

  ```bash
  uv run python scripts/validate_docs.py
  uv run python -m unittest
  ```

  Expected result: documentation validation and the full unit suite pass.

## Validation

- `uv run python scripts/validate_docs.py`
- `uv run python -m unittest`
- `uv run python main.py --run-profile tests/fixtures/run_profiles/foundation-scale-probe-25.json --write-evaluation-report --write-profile-decision-report --output-dir artifacts/foundation-scale-probe-evaluation`

Expected smoke behavior:

- `evaluation_report.json` exists.
- `manifest.json` references `artifacts.evaluation_report`.
- `profile_decision_report.json` includes held-out evaluation evidence when the
  evaluation report is requested.
- The default command without `--write-evaluation-report` does not write or
  reference evaluation artifacts.

## Acceptance Criteria

- Default local synthesis remains synchronous and does not write evaluation
  artifacts unless explicitly requested.
- The deterministic contacts held-out suite is independent from generated
  candidates and scale-probe duplicate patterns.
- `evaluation_report.json` is validated, sanitized, deterministic, and
  manifest-referenced only for opt-in runs.
- Capability-level held-out slices are present and stable.
- Optional parent evaluation comparison identifies regressions and improvements
  by held-out task id.
- Profile decision reports can incorporate held-out evaluation evidence without
  changing legacy no-evaluation behavior.
- Source governance, sandbox policy, role guardrails, MCP adapter behavior, and
  generated-code restrictions remain unchanged.
- Documentation validation and the unit suite pass.

## Risks

- The held-out suite can accidentally duplicate generation fixtures too closely.
  Keep task ids, instructions, and expected failure cases distinct from the
  deterministic scale probe.
- A small deterministic suite can create false confidence. Treat it as the first
  quality benchmark, not proof of downstream model improvement.
- Feeding evaluation evidence into profile decisions can break existing report
  consumers. Preserve legacy behavior when no evaluation report is supplied.
- Evaluation code can duplicate candidate execution logic. Reuse existing
  environment, registry, policy, and verifier boundaries wherever practical.
- Reports can leak local paths or source payloads. Serialize artifact basenames,
  hashes, ids, and summary counts only.

## Notes

This plan creates the first independent benchmark layer for synthesis quality.
It is intentionally small and deterministic so it can guide future decisions
about async orchestration, semantic duplicate detection, larger profiles, and
eventual downstream model evaluation without prematurely adding scale
infrastructure.
