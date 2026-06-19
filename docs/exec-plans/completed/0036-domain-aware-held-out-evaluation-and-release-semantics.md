# Plan 0036: Domain-Aware Held-Out Evaluation and Release Semantics

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status

Planned on 2026-06-14. Completed on 2026-06-19.

## Goal

Make held-out evaluation, profile decisions, and dataset release admission
domain-aware so a contacts benchmark cannot validate a mobile dataset, and
mobile source-backed profiles can produce their own deterministic evaluation
evidence.

## Architecture

Plan 0035 generalized profile-local source ingestion across contacts and mobile
domains, but `synthesis.evaluation` still runs a contacts-only held-out suite.
This plan introduces a small domain-aware evaluation suite resolver, adds a
mobile held-out suite that uses the existing mobile runtime/tool/verifier
boundaries, and adds evidence-mismatch gates in profile decision and dataset
release reporting.

The change stays synchronous and repo-local. It does not add async
orchestration, semantic duplicate detection, external MCP servers, RL rollout
collection, or AWM runtime package extraction.

## Tech Stack

- Python standard library: `dataclasses`, `json`, `pathlib`, `tempfile`, and
  `unittest`.
- Existing modules: `synthesis.evaluation`, `synthesis.domain_pipeline`,
  `synthesis.seeds`, `synthesis.tasks`, `synthesis.mobile_tasks`,
  `synthesis.execution`, `synthesis.verification`,
  `synthesis.profile_decisions`, `synthesis.dataset_release`,
  `synthesis.contracts`, `synthesis.datasets`, `synthesis.run_profiles`,
  `main.py`, and `scripts/evaluation_report.py`.
- Existing tests to extend: `tests/test_evaluation.py`,
  `tests/test_contracts.py`, `tests/test_profile_decisions.py`,
  `tests/test_dataset_release.py`, `tests/test_cli.py`, and
  `tests/test_mobile_pipeline.py`.
- Verification through `uv run python scripts/validate_docs.py` and
  `uv run python -m unittest`.

## Basis

- [../completed/0022-held-out-evaluation-and-profile-benchmarking.md](../completed/0022-held-out-evaluation-and-profile-benchmarking.md)
  added `evaluation_report_v1` with a deterministic contacts held-out suite.
- [../completed/0023-evaluation-quality-ratchet-and-profile-promotion.md](../completed/0023-evaluation-quality-ratchet-and-profile-promotion.md)
  made held-out evaluation evidence a profile-promotion gate when available.
- [../completed/0024-profile-purpose-and-dataset-release-admission.md](../completed/0024-profile-purpose-and-dataset-release-admission.md)
  made release admission depend on profile decision and held-out evaluation
  evidence.
- [../completed/0026-dataset-release-coverage-and-admission-ratchet.md](../completed/0026-dataset-release-coverage-and-admission-ratchet.md)
  added release completeness gates so tiny release-candidate profiles cannot
  pass release admission solely through broad status fields.
- [../completed/0029-mobile-agent-second-domain-pipeline-probe.md](../completed/0029-mobile-agent-second-domain-pipeline-probe.md)
  added `mobile_messages_fixture` as a second deterministic domain.
- [../completed/0033-task-intent-policy-verifier-contract-split.md](../completed/0033-task-intent-policy-verifier-contract-split.md)
  split internal task intent, policy hints, expected outcome, and expected
  state checks for contacts and mobile tasks.
- [../completed/0035-domain-source-admission-interface.md](../completed/0035-domain-source-admission-interface.md)
  let contacts and mobile profiles use shared source governance plus
  domain-owned source importers.
- [../../generated/mobile-domain-pipeline-pressure.md](../../generated/mobile-domain-pipeline-pressure.md)
  records that source-governed mobile runs are now supported, while domain-aware
  release/evaluation evidence remains implicit.
- [../../BACKEND.md](../../BACKEND.md) currently says `--write-evaluation-report`
  runs deterministic contacts benchmark tasks.

## Why This Plan Now

After plan 0035, the pipeline can build source-governed contacts and mobile
datasets through the same central path. Runtime consumers also already support
both domains: episode quality, executable replay, and reward labels all count
`contacts_fixture` and `mobile_messages_fixture` evidence.

The remaining mismatch is above the runtime layer:

- `synthesis.evaluation.build_evaluation_report(...)` always selects
  `contacts_heldout_suite()`;
- `_run_suite(...)` directly constructs `ContactEnvironment` and the contacts
  tool registry;
- `profile_decisions` and `dataset_release` trust evaluation decision status
  without checking whether the held-out suite domain matches the manifest or
  run profile domain;
- a future mobile release candidate could be judged by contacts held-out
  evidence unless this boundary is fixed first.

This is the next highest-ROI slice because it strengthens the quality and
release semantics that every later domain, release pack, and reward/RL workflow
will depend on.

## Scope

- Add domain identity to evaluation suites and generated evaluation reports.
- Preserve existing contacts evaluation behavior for default and contacts
  profiles.
- Add a deterministic mobile held-out suite covering message lookup, reminder
  creation, draft reply, branch fallback, and controlled failure.
- Make `build_evaluation_report(...)` resolve the held-out suite from the
  manifest/run-profile domain unless a caller explicitly supplies a compatible
  domain.
- Execute held-out tasks through `synthesis.domain_pipeline` so contacts and
  mobile use the same domain bundle, scripted policy, runtime, registry, and
  verifier boundaries as the generation pipeline.
- Add contract validation for domain-aware evaluation report fields while
  accepting legacy contacts-only reports where needed by existing tests and
  stored artifacts.
- Add profile-decision and dataset-release gates that treat domain-mismatched
  evaluation evidence as `insufficient_evidence`, not passed.
- Update CLI behavior and tests so mobile source-backed profiles can write
  evaluation and profile-decision reports using a mobile held-out suite.
- Update canonical docs and pressure notes.

## Out of Scope

- A third domain.
- Controlled network source ingestion for mobile or arbitrary domains.
- External MCP environment servers or mobile MCP adapter support.
- Agentic RL rollout collection, reward model training, preference
  optimization, PPO/DPO/GRPO, or GPU/distributed infrastructure.
- Async orchestration, durable queues, cancellation, resumption, or per-role
  cost tracking from plan 0014.
- Semantic duplicate detection from `TD-0002`.
- Changing dataset sample/rejection schemas, release pack hashing semantics, or
  default CLI output when evaluation flags are absent.
- Creating a separate `awm_runtime` package or repository.

## Contracts

### Domain-Aware Evaluation Suite

Extend the in-memory suite records in `synthesis.evaluation`:

```python
@dataclass(frozen=True)
class HeldoutSuite:
    suite_id: str
    suite_version: str
    domain_id: str
    tasks: tuple[HeldoutTask, ...]
```

Rules:

- `domain_id` must initially be one of `contacts_fixture` or
  `mobile_messages_fixture`.
- `contacts_heldout_suite().domain_id` must be `contacts_fixture`.
- `mobile_messages_heldout_suite().domain_id` must be
  `mobile_messages_fixture`.
- `resolve_heldout_suite(domain_id)` must normalize `contacts` to
  `contacts_fixture`, return the matching suite, and raise `ValueError` for
  unsupported domains.

### `evaluation_report_v1` Domain Fields

Keep `schema_version: evaluation_report_v1` and add domain fields to newly
generated reports:

```json
{
  "schema_version": "evaluation_report_v1",
  "dataset_version": "dataset_profile_local_mobile_messages",
  "suite": {
    "suite_id": "mobile_messages_heldout_v1",
    "suite_version": "mobile_messages_heldout_v1",
    "domain_id": "mobile_messages_fixture",
    "task_count": 5
  },
  "profile": {
    "profile_id": "profile_local_mobile_messages",
    "profile_purpose": "diagnostic_probe",
    "generation_mode": "mobile_fixture",
    "domain": "mobile_messages_fixture"
  },
  "domain": {
    "domain_id": "mobile_messages_fixture",
    "source": "manifest.run_profile.seed.domain"
  }
}
```

Rules:

- New reports must include `suite.domain_id` and top-level `domain.domain_id`.
- `suite.domain_id` and `domain.domain_id` must match.
- If `profile.domain` is present, it must match `domain.domain_id` after
  normalizing `contacts` to `contacts_fixture`.
- Legacy reports without these fields may remain valid only when
  `suite.suite_id == "contacts_heldout_v1"`; validation must infer
  `contacts_fixture` for compatibility.
- Reports must not include task instructions, expected answers, expected state,
  tool arguments, raw observations, profile-local paths, source payloads,
  prompts, credentials, environment variables, or host paths.

### Mobile Held-Out Suite

Add `mobile_messages_heldout_suite()` with stable task ids:

- `heldout_mobile_lookup_maya`: lookup a message from Maya.
- `heldout_mobile_reminder_maya`: create a reminder from Maya's project update
  message.
- `heldout_mobile_draft_reply_alex`: draft a reply to Alex.
- `heldout_mobile_branch_fallback_delivery`: exercise the mobile branch
  fallback path.
- `heldout_mobile_missing_message`: controlled failure for a missing message.

Rules:

- The suite must use existing deterministic mobile fixture data and scripted
  mobile policy behavior.
- Capability tags must include at least `mobile_message_lookup`,
  `mobile_message_to_reminder`, `mobile_draft_reply`, `mobile_branching`, and
  `mobile_missing_message`.
- Controlled failure must count as a passed held-out task only when the
  observed sanitized failure cause matches the expected failure cause.
- State-changing mobile tasks must verify final state through the existing
  mobile state-check path.

### Domain Mismatch Gates

Add a shared helper or equivalent local logic:

```python
def evaluation_domain_id(evaluation_report: Mapping[str, Any]) -> str | None:
    ...


def manifest_domain_id(manifest: Mapping[str, Any]) -> str | None:
    ...
```

Rules:

- Manifest domain should be resolved from `manifest.run_profile.seed.domain`
  when present.
- If the manifest has no run profile domain, treat the domain as
  `contacts_fixture` for legacy foundation artifacts.
- `profile_decisions` must return `profile_promotion.status:
  insufficient_evidence` when supplied evaluation evidence has a domain that
  does not match the manifest/profile domain.
- `dataset_release` must return `dataset_release.status:
  insufficient_evidence` when evaluation evidence has a domain that does not
  match the manifest/profile domain.
- Domain mismatch reasons must be sanitized, e.g. `"evaluation domain
  contacts_fixture does not match manifest domain mobile_messages_fixture"`.

## File Map

- Modify `synthesis/evaluation.py`:
  add suite domain identity, mobile held-out suite, suite resolver, domain-aware
  report fields, and domain-pipeline-based suite execution.
- Modify `synthesis/contracts.py`:
  validate new evaluation domain fields, preserve legacy contacts report
  compatibility, and add tests for mismatches.
- Modify `synthesis/profile_decisions.py`:
  summarize evaluation domain, validate it against manifest/profile domain, and
  mark profile promotion insufficient when mismatched.
- Modify `synthesis/dataset_release.py`:
  validate evaluation domain against release artifact manifest domain before
  allowing held-out status to pass release admission.
- Modify `scripts/evaluation_report.py`:
  keep current flags stable and optionally expose `--domain` if useful for
  standalone report generation.
- Modify `main.py`:
  ensure `--write-evaluation-report` passes enough manifest/profile context for
  domain-aware suite selection without changing no-flag behavior.
- Extend `tests/test_evaluation.py`.
- Extend `tests/test_contracts.py`.
- Extend `tests/test_profile_decisions.py`.
- Extend `tests/test_dataset_release.py`.
- Extend `tests/test_cli.py`.
- Extend `tests/test_mobile_pipeline.py` only if the mobile held-out suite
  needs focused state-change regression coverage outside `tests/test_evaluation.py`.
- Update [../../BACKEND.md](../../BACKEND.md),
  [../../DATA.md](../../DATA.md), [../../ROADMAP.md](../../ROADMAP.md),
  [../../generated/mobile-domain-pipeline-pressure.md](../../generated/mobile-domain-pipeline-pressure.md),
  [../../PLANS.md](../../PLANS.md), and this plan when completed.

## Implementation Tasks

### Task 1: Add Domain-Aware Suite Contract Tests

**Files:**

- Modify: `tests/test_evaluation.py`
- Modify later: `synthesis/evaluation.py`

- [ ] Add a test proving contacts suite identity stays stable and gains a
  domain:

```python
def test_contacts_suite_has_domain_identity(self) -> None:
    from synthesis.evaluation import contacts_heldout_suite, resolve_heldout_suite

    suite = contacts_heldout_suite()

    self.assertEqual(suite.domain_id, "contacts_fixture")
    self.assertEqual(resolve_heldout_suite("contacts").suite_id, "contacts_heldout_v1")
    self.assertEqual(
        resolve_heldout_suite("contacts_fixture").domain_id,
        "contacts_fixture",
    )
```

- [ ] Add a failing test for the mobile suite:

```python
def test_mobile_suite_has_stable_ids_and_capability_tags(self) -> None:
    from synthesis.evaluation import mobile_messages_heldout_suite

    suite = mobile_messages_heldout_suite()

    self.assertEqual(suite.suite_id, "mobile_messages_heldout_v1")
    self.assertEqual(suite.domain_id, "mobile_messages_fixture")
    self.assertEqual(
        [task.task_id for task in suite.tasks],
        [
            "heldout_mobile_lookup_maya",
            "heldout_mobile_reminder_maya",
            "heldout_mobile_draft_reply_alex",
            "heldout_mobile_branch_fallback_delivery",
            "heldout_mobile_missing_message",
        ],
    )
    observed_tags = sorted({tag for task in suite.tasks for tag in task.capability_tags})
    self.assertEqual(
        observed_tags,
        [
            "mobile_branching",
            "mobile_draft_reply",
            "mobile_message_lookup",
            "mobile_message_to_reminder",
            "mobile_missing_message",
        ],
    )
```

- [ ] Add a resolver rejection test:

```python
def test_resolve_heldout_suite_rejects_unsupported_domain(self) -> None:
    from synthesis.evaluation import resolve_heldout_suite

    with self.assertRaisesRegex(ValueError, "unsupported held-out evaluation domain"):
        resolve_heldout_suite("calendar_fixture")
```

- [ ] Run:

```bash
uv run python -m unittest tests.test_evaluation
```

- [ ] Confirm the new tests fail because the suite domain fields, resolver, and
  mobile suite do not exist.

### Task 2: Implement Suite Domain Identity and Mobile Held-Out Tasks

**Files:**

- Modify: `synthesis/evaluation.py`
- Modify: `tests/test_evaluation.py`

- [ ] Add `domain_id` to `HeldoutSuite`.

- [ ] Add `resolve_heldout_suite(domain_id: str) -> HeldoutSuite`:

```python
def resolve_heldout_suite(domain_id: str) -> HeldoutSuite:
    normalized = "contacts_fixture" if domain_id == "contacts" else domain_id
    if normalized == "contacts_fixture":
        return contacts_heldout_suite()
    if normalized == "mobile_messages_fixture":
        return mobile_messages_heldout_suite()
    raise ValueError(f"unsupported held-out evaluation domain: {domain_id}")
```

- [ ] Update `contacts_heldout_suite()` to return `domain_id="contacts_fixture"`.

- [ ] Add `mobile_messages_heldout_suite()` using existing
  `synthesis.mobile_tasks` deterministic candidate patterns. The mobile tasks
  must be `CandidateTask` values with:
  - `constraints["heldout"] == True`;
  - `constraints["task_type"]` set to the matching mobile task type;
  - `seed_ids == ("heldout_mobile_messages_seed_v1",)`;
  - expected state for reminder and draft-reply tasks.

- [ ] Run:

```bash
uv run python -m unittest tests.test_evaluation
```

- [ ] Confirm suite identity tests pass. Some report-generation tests may still
  use contacts-only execution and should continue passing.

### Task 3: Route Evaluation Execution Through Domain Pipeline

**Files:**

- Modify: `synthesis/evaluation.py`
- Modify: `tests/test_evaluation.py`
- Modify if needed: `tests/test_mobile_pipeline.py`

- [ ] Add a failing test that builds a mobile evaluation report from a mobile
  manifest:

```python
def test_mobile_report_counts_slices_and_validates(self) -> None:
    from synthesis.contracts import validate_evaluation_report_record
    from synthesis.evaluation import build_evaluation_report

    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path, quality_report_path = _write_mobile_inputs(Path(tmpdir))

        report = build_evaluation_report(
            manifest_path=manifest_path,
            quality_report_path=quality_report_path,
        )

    self.assertEqual(report["suite"]["suite_id"], "mobile_messages_heldout_v1")
    self.assertEqual(report["suite"]["domain_id"], "mobile_messages_fixture")
    self.assertEqual(report["domain"]["domain_id"], "mobile_messages_fixture")
    self.assertEqual(report["counts"]["total"], 5)
    self.assertEqual(report["counts"]["passed"], 5)
    self.assertEqual(report["counts"]["failed"], 0)
    self.assertEqual(report["capability_slices"]["mobile_message_lookup"]["passed"], 1)
    self.assertEqual(report["capability_slices"]["mobile_message_to_reminder"]["passed"], 1)
    self.assertEqual(report["capability_slices"]["mobile_draft_reply"]["passed"], 1)
    self.assertEqual(report["capability_slices"]["mobile_missing_message"]["passed"], 1)
    validate_evaluation_report_record(report)
```

- [ ] Add `_write_mobile_inputs(tmp_path: Path)` in `tests/test_evaluation.py`.
  It should write a manifest with:
  - `dataset_version: "dataset_mobile_test"`;
  - `environment_versions: ["mobile_messages_fixture_v1"]`;
  - `run_profile.schema_version: "run_profile_v2"`;
  - `run_profile.profile_id: "profile_local_mobile_messages"`;
  - `run_profile.generation_mode: "mobile_fixture"`;
  - `run_profile.seed.domain: "mobile_messages_fixture"`;
  - `run_profile.source.kind: "local_mobile_messages_json"`.

- [ ] Replace `_run_suite(suite)` internals with domain-pipeline execution:
  - create a seed for the suite domain;
  - call `build_domain_pipeline_bundle(seed, output_dir)`;
  - for each held-out task, generate the scripted solution through the bundle
    policy path or execute the task through the same execution/verifier helpers
    used by that domain;
  - verify expected final answer and expected state using the existing verifier
    path;
  - preserve controlled-failure semantics.

- [ ] Keep contacts held-out report output stable except for added domain fields.

- [ ] Run:

```bash
uv run python -m unittest tests.test_evaluation tests.test_mobile_pipeline
```

- [ ] Confirm contacts and mobile evaluation tests pass.

### Task 4: Add Domain Fields to Evaluation Report Validation

**Files:**

- Modify: `synthesis/contracts.py`
- Modify: `tests/test_contracts.py`
- Modify: `tests/test_evaluation.py`
- Modify: `tests/test_profile_decisions.py`
- Modify: `tests/test_dataset_release.py`

- [ ] Add a contract test for a new mobile `evaluation_report_v1` record with:
  - `suite.domain_id == "mobile_messages_fixture"`;
  - `domain.domain_id == "mobile_messages_fixture"`;
  - `profile.domain == "mobile_messages_fixture"`.

- [ ] Add a contract test that rejects mismatched suite/report domains:

```python
def test_evaluation_report_rejects_mismatched_domain_fields(self) -> None:
    from synthesis.contracts import ContractValidationError, validate_evaluation_report_record

    report = _valid_evaluation_report()
    report["suite"]["domain_id"] = "contacts_fixture"
    report["domain"] = {"domain_id": "mobile_messages_fixture", "source": "test"}

    with self.assertRaisesRegex(ContractValidationError, "domain"):
        validate_evaluation_report_record(report)
```

- [ ] Add a legacy compatibility test: a valid contacts report without
  `suite.domain_id` and top-level `domain` still validates when
  `suite.suite_id == "contacts_heldout_v1"`.

- [ ] Implement validation:
  - accept only `contacts_fixture` and `mobile_messages_fixture`;
  - infer legacy `contacts_fixture` only for contacts suite reports;
  - require new reports for non-contacts domains to include domain fields;
  - reject secret/path/source payload material as current validation already
    does.

- [ ] Run:

```bash
uv run python -m unittest tests.test_contracts tests.test_evaluation tests.test_profile_decisions tests.test_dataset_release
```

- [ ] Confirm existing report fixtures and new domain-aware report fixtures pass.

### Task 5: Add Profile-Decision Domain Mismatch Gate

**Files:**

- Modify: `synthesis/profile_decisions.py`
- Modify: `tests/test_profile_decisions.py`

- [ ] Add a failing test where a mobile manifest/profile receives a contacts
  evaluation report. Assert:
  - `report["evaluation"]["domain_id"] == "contacts_fixture"`;
  - `decisions.profile_promotion.status == "insufficient_evidence"`;
  - reasons include a sanitized domain mismatch message.

- [ ] Add a passing test where a mobile manifest/profile receives a mobile
  evaluation report and existing profile-promotion thresholds pass.

- [ ] Implement helpers in `synthesis.profile_decisions` or a small shared
  location:

```python
def _manifest_domain_id(manifest: Mapping[str, Any]) -> str:
    run_profile = manifest.get("run_profile")
    if isinstance(run_profile, Mapping):
        seed = run_profile.get("seed")
        if isinstance(seed, Mapping):
            domain = seed.get("domain")
            if isinstance(domain, str) and domain.strip():
                return "contacts_fixture" if domain == "contacts" else domain
    return "contacts_fixture"
```

- [ ] Summarize evaluation domain in the profile decision report:

```json
"evaluation": {
  "decision_status": "passed",
  "pass_rate": 1.0,
  "regressed": 0,
  "domain_id": "mobile_messages_fixture",
  "suite_id": "mobile_messages_heldout_v1"
}
```

- [ ] Make profile promotion insufficient when evaluation domain mismatches the
  manifest domain. Do not change legacy no-evaluation behavior.

- [ ] Run:

```bash
uv run python -m unittest tests.test_profile_decisions tests.test_evaluation
```

- [ ] Confirm profile decision tests pass.

### Task 6: Add Dataset Release Domain Mismatch Gate

**Files:**

- Modify: `synthesis/dataset_release.py`
- Modify: `tests/test_dataset_release.py`

- [ ] Add a failing test where:
  - profile purpose is `release_candidate`;
  - profile promotion passed;
  - release completeness passed;
  - evaluation decision passed;
  - evaluation domain is `contacts_fixture`;
  - manifest domain is `mobile_messages_fixture`.

  Assert `decisions.dataset_release.status == "insufficient_evidence"` and
  `triggered_by` includes `"evaluation_domain"`.

- [ ] Add a passing test where the same mobile release candidate uses a mobile
  evaluation report and all existing release gates pass.

- [ ] Implement domain mismatch detection before held-out status can pass
  release admission. The release decision should return:

```python
{
    "status": "insufficient_evidence",
    "reasons": [
        "evaluation domain contacts_fixture does not match manifest domain mobile_messages_fixture"
    ],
    "triggered_by": ["evaluation_domain"],
}
```

- [ ] Preserve existing contacts release-candidate behavior.

- [ ] Run:

```bash
uv run python -m unittest tests.test_dataset_release tests.test_profile_decisions
```

- [ ] Confirm dataset release tests pass.

### Task 7: Wire CLI and Standalone Script Behavior

**Files:**

- Modify: `main.py`
- Modify: `scripts/evaluation_report.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_evaluation.py`

- [ ] Add a CLI test for mobile profile evaluation:

```python
def test_main_can_write_evaluation_report_for_mobile_source_profile(self) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "mobile-evaluation"

        result = subprocess.run(
            [
                sys.executable,
                "main.py",
                "--run-profile",
                "tests/fixtures/run_profiles/profile-local-mobile-messages.json",
                "--write-evaluation-report",
                "--output-dir",
                str(output_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads((output_dir / "evaluation_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["suite"]["domain_id"], "mobile_messages_fixture")
        self.assertEqual(report["decision"]["status"], "passed")
```

- [ ] Add a CLI test for mobile profile evaluation plus profile decision:
  assert profile promotion uses mobile held-out evidence and passes or remains
  ineligible according to profile purpose, but does not report a domain
  mismatch.

- [ ] Add a standalone script test if `scripts/evaluation_report.py` gains
  `--domain`; otherwise confirm it derives domain from the manifest just like
  `main.py`.

- [ ] Keep default `uv run python main.py` behavior unchanged: no evaluation
  report is written unless explicitly requested.

- [ ] Run:

```bash
uv run python -m unittest tests.test_cli tests.test_evaluation
```

- [ ] Confirm CLI tests pass.

### Task 8: Update Documentation and Pressure Notes

**Files:**

- Modify: `docs/BACKEND.md`
- Modify: `docs/DATA.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/generated/mobile-domain-pipeline-pressure.md`
- Modify: `docs/PLANS.md`
- Modify when completed:
  `docs/exec-plans/completed/0036-domain-aware-held-out-evaluation-and-release-semantics.md`

- [ ] Update `docs/BACKEND.md`:
  - replace contacts-only wording for `--write-evaluation-report`;
  - document domain-aware suite selection;
  - document profile decision and dataset release domain mismatch gates.

- [ ] Update `docs/DATA.md`:
  - document `evaluation_report_v1.suite.domain_id`;
  - document top-level `evaluation_report_v1.domain`;
  - document legacy contacts report compatibility if needed;
  - state that evaluation evidence must match the manifest/profile domain for
    profile promotion and release admission.

- [ ] Update `docs/ROADMAP.md`:
  - add this completed/active Stage 4 item after plan 0035;
  - keep async orchestration, semantic duplicate detection, external MCP,
    Agentic RL, and runtime extraction deferred.

- [ ] Update `docs/generated/mobile-domain-pipeline-pressure.md`:
  - move domain-aware held-out evaluation from unresolved pressure to resolved
    narrowly when completed;
  - keep Agentic RL rollout, external MCP, semantic duplicate detection,
    controlled network import for non-contacts domains, async orchestration, and
    runtime package extraction unresolved.

- [ ] Update `docs/PLANS.md` and active/completed buckets according to final
  plan status.

- [ ] Run:

```bash
uv run python scripts/validate_docs.py
```

- [ ] Confirm documentation validation passes.

### Task 9: Full Regression and Completion Evidence

**Files:**

- No new files expected.
- Update this plan's status/evidence section when implementation completes.

- [ ] Run focused tests:

```bash
uv run python -m unittest tests.test_evaluation tests.test_contracts tests.test_profile_decisions tests.test_dataset_release tests.test_cli tests.test_mobile_pipeline
```

- [ ] Run full unit suite:

```bash
uv run python -m unittest
```

- [ ] Run docs validation:

```bash
uv run python scripts/validate_docs.py
```

- [ ] Run a contacts evaluation command:

```bash
uv run python main.py --run-profile tests/fixtures/run_profiles/foundation-scale-probe-25.json --write-evaluation-report --write-profile-decision-report --output-dir artifacts/foundation-domain-aware-evaluation
```

- [ ] Confirm `evaluation_report.json` uses
  `suite.domain_id == "contacts_fixture"` and profile decisions remain stable.

- [ ] Run a mobile source-backed evaluation command:

```bash
uv run python main.py --run-profile tests/fixtures/run_profiles/profile-local-mobile-messages.json --write-evaluation-report --write-profile-decision-report --output-dir artifacts/mobile-domain-aware-evaluation
```

- [ ] Confirm `evaluation_report.json` uses
  `suite.domain_id == "mobile_messages_fixture"` and `decision.status ==
  "passed"`.

- [ ] Record validation output in this plan's completion evidence before moving
  it to `../completed/`.

## Validation

Required before completion:

```bash
uv run python scripts/validate_docs.py
uv run python -m unittest
uv run python main.py --run-profile tests/fixtures/run_profiles/foundation-scale-probe-25.json --write-evaluation-report --write-profile-decision-report --output-dir artifacts/foundation-domain-aware-evaluation
uv run python main.py --run-profile tests/fixtures/run_profiles/profile-local-mobile-messages.json --write-evaluation-report --write-profile-decision-report --output-dir artifacts/mobile-domain-aware-evaluation
```

Focused suite while developing:

```bash
uv run python -m unittest tests.test_evaluation tests.test_contracts tests.test_profile_decisions tests.test_dataset_release tests.test_cli tests.test_mobile_pipeline
```

## Acceptance Criteria

- Default `uv run python main.py` remains synchronous and does not write
  evaluation, profile-decision, or release artifacts unless explicitly
  requested.
- Existing contacts evaluation reports still pass, with domain fields added to
  newly generated reports.
- Mobile source-backed profiles can write validated `evaluation_report.json`
  using a mobile held-out suite.
- `evaluation_report_v1` records expose sanitized domain identity without raw
  instructions, expected answers, state, observations, source payloads, profile
  paths, prompts, credentials, or host paths.
- Profile promotion cannot pass when evaluation evidence belongs to a different
  domain from the manifest/profile.
- Dataset release admission cannot pass when evaluation evidence belongs to a
  different domain from the manifest/profile.
- Release and profile decision reports preserve legacy behavior when no
  evaluation report is supplied.
- Async orchestration, semantic duplicate detection, external MCP servers,
  Agentic RL rollout collection, and AWM runtime package extraction remain
  deferred.

## Risks

- Adding domain fields to `evaluation_report_v1` can break consumers that assume
  the old shape. Keep schema version stable and allow legacy contacts reports
  where the suite id is unambiguous.
- Running held-out evaluation through `synthesis.domain_pipeline` can produce
  small differences from the previous contacts-only direct execution path. Keep
  contacts report counts, task ids, and capability slices stable.
- Mobile held-out tasks may accidentally duplicate deterministic generation
  tasks too closely. Treat this plan as domain coverage and release-semantics
  hardening, not downstream generalization proof.
- Domain mismatch checks can become too permissive if manifest domain inference
  silently defaults to contacts for new profiles. Default only for legacy
  artifacts without run-profile seed metadata.
- Evaluation reports can be mistaken for release proof. Keep docs explicit:
  held-out evaluation is one input to profile/release decisions, not downstream
  model-quality evidence.
