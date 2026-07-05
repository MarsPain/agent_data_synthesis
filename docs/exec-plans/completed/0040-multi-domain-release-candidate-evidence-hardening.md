# Plan 0040: Multi-Domain Release Candidate Evidence Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make contacts, mobile messages, and workspace tasks all support
explicit release-candidate evidence paths with domain-aware release completeness
thresholds and end-to-end release artifact coverage.

**Architecture:** Keep release admission as a sanitized report consumer over
existing manifest, quality, evaluation, and profile-decision artifacts. Add
domain-owned release-candidate fixtures and deterministic candidate coverage
where a domain currently produces too little release evidence; keep release
completeness thresholds explicit and domain-aware instead of deriving them from
observed slices.

**Tech Stack:** Python dataclasses, deterministic fixture generators,
`unittest`, JSON run-profile fixtures, existing `uv run python ...` validation
commands.

---

## Status

Completed on 2026-07-05.

Validation evidence:

- `uv run python -m unittest tests.test_dataset_release`
  - 15 tests passed after confirming mobile/workspace undercoverage failed
    before implementation.
- `uv run python -m unittest tests.test_run_profiles`
  - 22 tests passed after adding mobile/workspace release-candidate fixtures.
- `uv run python -m unittest tests.test_mobile_pipeline tests.test_workspace_pipeline`
  - 21 tests passed after adding fifth deterministic mobile/workspace
    candidates.
- `uv run python -m unittest tests.test_cli`
  - 49 tests passed after adding mobile/workspace release artifact smoke tests
    and release-pack verification coverage.
- `uv run python -m unittest tests.test_dataset_release tests.test_run_profiles tests.test_mobile_pipeline tests.test_workspace_pipeline tests.test_cli tests.test_source_governance`
  - 123 tests passed.
- `uv run python -m unittest`
  - 468 tests passed.
- `uv run python scripts/validate_docs.py`
  - documentation validation passed.
- `uv run python main.py --run-profile tests/fixtures/run_profiles/mobile-messages-release-candidate.json --write-evaluation-report --write-profile-decision-report --write-dataset-release-report --write-dataset-release-pack --write-release-quality-audit --write-dataset-release-card --output-dir artifacts/mobile-release-candidate`
  - exited 0 with `accepted=5`, `rejected=0`, and all release artifacts
    written.
- `uv run python scripts/verify_dataset_release.py --output-dir artifacts/mobile-release-candidate`
  - exited 0 with verification status `passed`.
- `uv run python main.py --run-profile tests/fixtures/run_profiles/workspace-tasks-release-candidate.json --write-evaluation-report --write-profile-decision-report --write-dataset-release-report --write-dataset-release-pack --write-release-quality-audit --write-dataset-release-card --output-dir artifacts/workspace-release-candidate`
  - exited 0 with `accepted=5`, `rejected=0`, and all release artifacts
    written.
- `uv run python scripts/verify_dataset_release.py --output-dir artifacts/workspace-release-candidate`
  - exited 0 with verification status `passed`.

## Why This Plan

Plans 0037, 0038, and 0039 proved the third workspace domain, retired the
runtime compatibility shims, and added workspace profile-local source admission.
The repository now has three deterministic domains that can produce replay,
reward-label, evaluation, and profile-decision evidence.

The remaining product gap is narrower: the public release-candidate evidence
path is still centered on the contacts foundation profile. `README.md` exposes
a release pack command for `foundation-release-candidate.json`, while mobile
and workspace profiles are diagnostic probes. `synthesis.dataset_release` has
domain mismatch checks for mobile and workspace, but non-contacts release
completeness thresholds currently mirror whatever slices were observed. That
means undercovered non-contacts release candidates can pass completeness without
an explicit domain coverage standard.

This plan turns the three supported domains into first-class local release
candidate paths without activating async orchestration, semantic duplicate
detection, external MCP servers, real user data ingestion, reward-model
training, or Agentic RL.

## Scope

- Add explicit release completeness threshold declarations for:
  - `contacts_fixture`
  - `mobile_messages_fixture`
  - `workspace_tasks_fixture`
- Add release-candidate run-profile fixtures for mobile and workspace.
- Add enough deterministic mobile and workspace candidates for each domain to
  meet the existing `min_accepted_samples = 5` release completeness floor.
- Add unit tests proving undercovered mobile/workspace release candidates are
  `insufficient_evidence`.
- Add CLI smoke tests proving mobile and workspace release candidates can write:
  - `evaluation_report.json`
  - `profile_decision_report.json`
  - `dataset_release_report.json`
  - `dataset_release_pack.json`
  - `release_quality_audit.json`
  - `dataset_release_card.md`
- Update canonical docs and root commands so the release-candidate path is
  described as three-domain evidence rather than contacts-only evidence.
- Preserve all existing public artifact schemas.

## Out of Scope

- Async orchestration, durable queues, cancellation, distributed workers, or
  per-role async cost tracking from plan 0014.
- Semantic duplicate detection from `TD-0002`.
- Fourth-domain work.
- External MCP servers, browser automation, SaaS connectors, remote filesystem
  access, or real user data access.
- Controlled network ingestion for mobile or workspace.
- Reward-model training, policy optimization, Agentic RL rollout collection, or
  model publishing.
- Changing default `uv run python main.py` behavior.
- Changing `samples.jsonl`, `rejections.jsonl`, manifest, quality, evaluation,
  replay, reward-label, release-pack, quality-audit, or release-card schemas.

## File Map

- Modify: `synthesis/dataset_release.py`
  - Replace observed-slice-derived non-contacts thresholds with explicit
    domain-aware release completeness thresholds.
- Modify: `tests/test_dataset_release.py`
  - Add undercoverage tests for mobile and workspace release candidates.
  - Assert explicit threshold values for all three releaseable domains.
- Modify: `tests/test_contracts.py`
  - Keep dataset release report examples aligned with the threshold contract.
- Add: `tests/fixtures/run_profiles/mobile-messages-release-candidate.json`
  - Mobile release-candidate profile using `mobile_fixture`.
- Add: `tests/fixtures/run_profiles/workspace-tasks-release-candidate.json`
  - Workspace release-candidate profile using `workspace_fixture`.
- Modify: `synthesis/mobile_tasks.py`
  - Add one deterministic mobile candidate so release-candidate runs reach at
    least five accepted samples.
- Modify: `synthesis/workspace_tasks.py`
  - Add one deterministic workspace candidate so release-candidate runs reach
    at least five accepted samples.
- Modify: `tests/test_mobile_pipeline.py`
  - Assert the mobile fixture release candidate has five accepted candidates and
    preserves task-type coverage.
- Modify: `tests/test_workspace_pipeline.py`
  - Assert the workspace fixture release candidate has five accepted candidates
    and preserves task-type coverage.
- Modify: `tests/test_cli.py`
  - Add mobile and workspace end-to-end release artifact smoke tests.
- Modify: `README.md`
  - Add mobile and workspace release-candidate commands.
- Modify: `docs/DATA.md`
  - Document domain-aware release completeness thresholds.
- Modify: `docs/ROADMAP.md`
  - Record this three-domain release-candidate hardening step.
- Modify: `docs/product-specs/framework-mvp.md`
  - Update MVP acceptance from contacts-focused release evidence to three-domain
    local release evidence.
- Modify: `docs/PLANS.md`, `docs/exec-plans/active/README.md`,
  `docs/README.md`
  - Track this plan as active.

## Data Contract

Release completeness remains part of `dataset_release_report_v1` and keeps the
same shape:

```python
{
    "thresholds": {
        "min_accepted_samples": 5,
        "max_rejection_rate": 0.2,
        "required_task_types": [...],
        "required_tool_combinations": [...],
    },
    "observed": {
        "accepted": 5,
        "rejected": 0,
        "rejection_rate": 0.0,
        "task_types": [...],
        "tool_combinations": [...],
    },
    "decision": {
        "status": "passed",
        "reasons": [...],
        "triggered_by": [
            "accepted",
            "rejection_rate",
            "task_type_coverage",
            "tool_combination_coverage",
        ],
    },
}
```

Threshold values become explicit by domain:

```python
DOMAIN_RELEASE_COMPLETENESS_THRESHOLDS = {
    "contacts_fixture": ReleaseCompletenessThresholds(
        min_accepted_samples=5,
        max_rejection_rate=0.2,
        required_task_types=(
            "lookup_contact_email",
            "contact_followup",
            "contact_branch_fallback",
        ),
        required_tool_combinations=(
            "lookup_contact_email",
            "lookup_contact_email+record_contact_followup",
        ),
    ),
    "mobile_messages_fixture": ReleaseCompletenessThresholds(
        min_accepted_samples=5,
        max_rejection_rate=0.2,
        required_task_types=(
            "mobile_message_lookup",
            "mobile_message_to_reminder",
            "mobile_draft_reply",
            "mobile_branch_fallback",
        ),
        required_tool_combinations=(
            "search_phone_messages",
            "search_phone_messages+create_phone_reminder",
            "search_phone_messages+draft_message_reply",
        ),
    ),
    "workspace_tasks_fixture": ReleaseCompletenessThresholds(
        min_accepted_samples=5,
        max_rejection_rate=0.2,
        required_task_types=(
            "workspace_item_lookup",
            "workspace_task_creation",
            "workspace_comment_update",
            "workspace_branch_fallback",
        ),
        required_tool_combinations=(
            "search_workspace_items",
            "search_workspace_items+create_workspace_task",
            "search_workspace_items+add_workspace_comment",
        ),
    ),
}
```

Unknown domains should still avoid false release claims. For unknown domain ids,
`_release_completeness_thresholds(...)` should use the existing conservative
observed-slice fallback so current malformed/unsupported-domain paths continue
to validate reports without inventing cross-domain requirements.

## Implementation Tasks

### Task 1: Add Domain-Aware Release Threshold Red Tests

**Files:**
- Modify: `tests/test_dataset_release.py`

- [ ] Add this test for mobile undercoverage:

```python
    def test_mobile_release_candidate_missing_required_slices_is_insufficient(self) -> None:
        from synthesis.dataset_release import build_dataset_release_report

        report = build_dataset_release_report(
            manifest=_mobile_manifest(
                profile_purpose="release_candidate",
                accepted_count=6,
                rejected_count=0,
            ),
            quality_report=_quality_report(
                accepted=6,
                rejected=0,
                task_types=("mobile_message_lookup",),
                tool_combinations=("search_phone_messages",),
            ),
            evaluation_report=_domain_evaluation_report(
                status="passed",
                domain_id="mobile_messages_fixture",
                suite_id="mobile_messages_heldout_v1",
            ),
            profile_decision_report=_profile_decision_report(
                profile_promotion_status="passed"
            ),
        )

        completeness = report["release_completeness"]
        self.assertEqual(completeness["decision"]["status"], "insufficient_evidence")
        self.assertEqual(
            set(completeness["thresholds"]["required_task_types"]),
            {
                "mobile_message_lookup",
                "mobile_message_to_reminder",
                "mobile_draft_reply",
                "mobile_branch_fallback",
            },
        )
        self.assertIn(
            "task_type_coverage",
            completeness["decision"]["triggered_by"],
        )
        self.assertIn(
            "tool_combination_coverage",
            completeness["decision"]["triggered_by"],
        )
```

- [ ] Add this test for workspace undercoverage:

```python
    def test_workspace_release_candidate_missing_required_slices_is_insufficient(self) -> None:
        from synthesis.dataset_release import build_dataset_release_report

        report = build_dataset_release_report(
            manifest=_workspace_manifest(
                profile_purpose="release_candidate",
                accepted_count=6,
                rejected_count=0,
            ),
            quality_report=_quality_report(
                accepted=6,
                rejected=0,
                task_types=("workspace_item_lookup",),
                tool_combinations=("search_workspace_items",),
            ),
            evaluation_report=_domain_evaluation_report(
                status="passed",
                domain_id="workspace_tasks_fixture",
                suite_id="workspace_tasks_heldout_v1",
            ),
            profile_decision_report=_profile_decision_report(
                profile_promotion_status="passed"
            ),
        )

        completeness = report["release_completeness"]
        self.assertEqual(completeness["decision"]["status"], "insufficient_evidence")
        self.assertEqual(
            set(completeness["thresholds"]["required_task_types"]),
            {
                "workspace_item_lookup",
                "workspace_task_creation",
                "workspace_comment_update",
                "workspace_branch_fallback",
            },
        )
        self.assertIn(
            "task_type_coverage",
            completeness["decision"]["triggered_by"],
        )
        self.assertIn(
            "tool_combination_coverage",
            completeness["decision"]["triggered_by"],
        )
```

- [ ] Run the focused tests and confirm they fail before implementation:

```bash
uv run python -m unittest tests.test_dataset_release
```

Expected before implementation: the new undercoverage tests fail because
non-contacts thresholds are derived from observed slices.

### Task 2: Implement Explicit Domain Release Thresholds

**Files:**
- Modify: `synthesis/dataset_release.py`
- Modify: `tests/test_dataset_release.py`

- [ ] Replace `RELEASE_COMPLETENESS_THRESHOLDS` with a contacts-specific
constant plus the domain map:

```python
CONTACTS_RELEASE_COMPLETENESS_THRESHOLDS = ReleaseCompletenessThresholds(
    min_accepted_samples=5,
    max_rejection_rate=0.2,
    required_task_types=(
        "lookup_contact_email",
        "contact_followup",
        "contact_branch_fallback",
    ),
    required_tool_combinations=(
        "lookup_contact_email",
        "lookup_contact_email+record_contact_followup",
    ),
)

DOMAIN_RELEASE_COMPLETENESS_THRESHOLDS: dict[str, ReleaseCompletenessThresholds] = {
    "contacts_fixture": CONTACTS_RELEASE_COMPLETENESS_THRESHOLDS,
    "mobile_messages_fixture": ReleaseCompletenessThresholds(
        min_accepted_samples=5,
        max_rejection_rate=0.2,
        required_task_types=(
            "mobile_message_lookup",
            "mobile_message_to_reminder",
            "mobile_draft_reply",
            "mobile_branch_fallback",
        ),
        required_tool_combinations=(
            "search_phone_messages",
            "search_phone_messages+create_phone_reminder",
            "search_phone_messages+draft_message_reply",
        ),
    ),
    "workspace_tasks_fixture": ReleaseCompletenessThresholds(
        min_accepted_samples=5,
        max_rejection_rate=0.2,
        required_task_types=(
            "workspace_item_lookup",
            "workspace_task_creation",
            "workspace_comment_update",
            "workspace_branch_fallback",
        ),
        required_tool_combinations=(
            "search_workspace_items",
            "search_workspace_items+create_workspace_task",
            "search_workspace_items+add_workspace_comment",
        ),
    ),
}
```

- [ ] Replace `_release_completeness_thresholds(...)` with:

```python
def _release_completeness_thresholds(
    domain_id: str | None,
    *,
    task_types: list[str],
    tool_combinations: list[str],
) -> ReleaseCompletenessThresholds:
    normalized_domain = "contacts_fixture" if domain_id in {None, "contacts"} else domain_id
    if normalized_domain in DOMAIN_RELEASE_COMPLETENESS_THRESHOLDS:
        return DOMAIN_RELEASE_COMPLETENESS_THRESHOLDS[normalized_domain]
    return ReleaseCompletenessThresholds(
        min_accepted_samples=CONTACTS_RELEASE_COMPLETENESS_THRESHOLDS.min_accepted_samples,
        max_rejection_rate=CONTACTS_RELEASE_COMPLETENESS_THRESHOLDS.max_rejection_rate,
        required_task_types=tuple(task_types),
        required_tool_combinations=tuple(tool_combinations),
    )
```

- [ ] In `tests/test_dataset_release.py`, update the existing mobile pass test
so it uses mobile task types and tool combinations:

```python
            quality_report=_quality_report(
                accepted=6,
                rejected=1,
                task_types=(
                    "mobile_message_lookup",
                    "mobile_message_to_reminder",
                    "mobile_draft_reply",
                    "mobile_branch_fallback",
                ),
                tool_combinations=(
                    "search_phone_messages",
                    "search_phone_messages > create_phone_reminder",
                    "search_phone_messages > draft_message_reply",
                ),
            ),
```

- [ ] Run:

```bash
uv run python -m unittest tests.test_dataset_release
```

Expected: all dataset release tests pass.

### Task 3: Add Mobile and Workspace Release-Candidate Profiles

**Files:**
- Add: `tests/fixtures/run_profiles/mobile-messages-release-candidate.json`
- Add: `tests/fixtures/run_profiles/workspace-tasks-release-candidate.json`
- Modify: `tests/test_run_profiles.py`

- [ ] Add `tests/fixtures/run_profiles/mobile-messages-release-candidate.json`:

```json
{
  "schema_version": "run_profile_v1",
  "profile_id": "mobile_messages_release_candidate",
  "dataset_version": "dataset_mobile_messages_release_candidate",
  "profile_purpose": "release_candidate",
  "seed": {
    "seed_id": "seed_mobile_messages_v1",
    "domain": "mobile_messages_fixture",
    "description": "Synthetic phone messages, reminders, and draft replies.",
    "task_taxonomy": [
      "mobile_message_lookup",
      "mobile_message_to_reminder",
      "mobile_draft_reply",
      "mobile_branch_fallback"
    ]
  },
  "generation": {
    "mode": "mobile_fixture"
  },
  "features": {
    "enable_branching": false,
    "enable_task_expansion": false,
    "enable_refinement": false,
    "enable_mcp_adapter": false,
    "enable_sandbox_fixture": false,
    "enable_source_governance_fixture": false
  }
}
```

- [ ] Add `tests/fixtures/run_profiles/workspace-tasks-release-candidate.json`:

```json
{
  "schema_version": "run_profile_v1",
  "profile_id": "workspace_tasks_release_candidate",
  "dataset_version": "dataset_workspace_tasks_release_candidate",
  "profile_purpose": "release_candidate",
  "seed": {
    "seed_id": "seed_workspace_tasks_v1",
    "domain": "workspace_tasks_fixture",
    "description": "Synthetic workspace projects, tasks, documents, and comments.",
    "task_taxonomy": [
      "workspace_item_lookup",
      "workspace_task_creation",
      "workspace_comment_update",
      "workspace_branch_fallback"
    ]
  },
  "generation": {
    "mode": "workspace_fixture"
  },
  "features": {
    "enable_branching": false,
    "enable_task_expansion": false,
    "enable_refinement": false,
    "enable_mcp_adapter": false,
    "enable_sandbox_fixture": false,
    "enable_source_governance_fixture": false
  }
}
```

- [ ] Add a focused run-profile loading test:

```python
    def test_load_release_candidate_profiles_for_mobile_and_workspace(self) -> None:
        from synthesis.run_profiles import load_run_profile

        mobile = load_run_profile(
            Path("tests/fixtures/run_profiles/mobile-messages-release-candidate.json")
        )
        workspace = load_run_profile(
            Path("tests/fixtures/run_profiles/workspace-tasks-release-candidate.json")
        )

        self.assertEqual(mobile.profile_purpose, "release_candidate")
        self.assertEqual(mobile.generation_mode, "mobile_fixture")
        self.assertEqual(workspace.profile_purpose, "release_candidate")
        self.assertEqual(workspace.generation_mode, "workspace_fixture")
```

- [ ] Run:

```bash
uv run python -m unittest tests.test_run_profiles
```

Expected: all run-profile tests pass.

### Task 4: Add Fifth Deterministic Candidate per Non-Contacts Domain

**Files:**
- Modify: `synthesis/mobile_tasks.py`
- Modify: `synthesis/workspace_tasks.py`
- Modify: `tests/test_mobile_pipeline.py`
- Modify: `tests/test_workspace_pipeline.py`

- [ ] In `synthesis/mobile_tasks.py`, add this candidate to
`generate_mobile_fixture_candidates(...)` before the branch fallback candidate:

```python
        CandidateTask(
            candidate_id="candidate_mobile_delivery_code_lookup",
            instruction="Find the delivery pickup code in the phone inbox.",
            constraints={
                "domain": "mobile_messages_fixture",
                "task_type": "mobile_message_lookup",
                "required_tools": ["search_phone_messages"],
            },
            difficulty=_difficulty(tool_count=1, state_changes=0),
            tool_name="search_phone_messages",
            arguments={"query": "pickup code", "participant": "Delivery"},
            expected_answer="4821",
            seed_ids=(seed.seed_id,),
        ),
```

- [ ] In `synthesis/workspace_tasks.py`, add this candidate to
`generate_workspace_fixture_candidates(...)` after the launch lookup candidate:

```python
        CandidateTask(
            candidate_id="candidate_workspace_launch_brief_lookup",
            instruction="Find the workspace document with the launch brief.",
            constraints={
                "domain": "workspace_tasks_fixture",
                "task_type": "workspace_item_lookup",
                "required_tools": ["search_workspace_items"],
            },
            difficulty=_difficulty(tool_count=1, state_changes=0),
            tool_name="search_workspace_items",
            arguments={"query": "Launch Brief", "kind": "document"},
            expected_answer="doc_launch_brief",
            seed_ids=(seed.seed_id,),
        ),
```

- [ ] Add this test to `tests/test_mobile_pipeline.py`:

```python
    def test_mobile_release_candidate_fixture_has_release_sample_floor(self) -> None:
        from synthesis.mobile_tasks import generate_mobile_fixture_candidates
        from synthesis.seeds import DomainSeed

        seed = DomainSeed(
            seed_id="seed_mobile_messages_v1",
            domain="mobile_messages_fixture",
            description="Synthetic phone messages, reminders, and draft replies.",
            task_taxonomy=(
                "mobile_message_lookup",
                "mobile_message_to_reminder",
                "mobile_draft_reply",
                "mobile_branch_fallback",
            ),
        )
        candidates = generate_mobile_fixture_candidates(seed)

        self.assertGreaterEqual(len(candidates), 5)
        self.assertTrue(
            {
                "mobile_message_lookup",
                "mobile_message_to_reminder",
                "mobile_draft_reply",
                "mobile_branch_fallback",
            }.issubset({candidate.constraints["task_type"] for candidate in candidates})
        )
```

- [ ] Add this test to `tests/test_workspace_pipeline.py`:

```python
    def test_workspace_release_candidate_fixture_has_release_sample_floor(self) -> None:
        from synthesis.seeds import DomainSeed
        from synthesis.workspace_tasks import generate_workspace_fixture_candidates

        seed = DomainSeed(
            seed_id="seed_workspace_tasks_v1",
            domain="workspace_tasks_fixture",
            description="Synthetic workspace projects, tasks, documents, and comments.",
            task_taxonomy=(
                "workspace_item_lookup",
                "workspace_task_creation",
                "workspace_comment_update",
                "workspace_branch_fallback",
            ),
        )
        candidates = generate_workspace_fixture_candidates(seed)

        self.assertGreaterEqual(len(candidates), 5)
        self.assertTrue(
            {
                "workspace_item_lookup",
                "workspace_task_creation",
                "workspace_comment_update",
                "workspace_branch_fallback",
            }.issubset({candidate.constraints["task_type"] for candidate in candidates})
        )
```

- [ ] Run:

```bash
uv run python -m unittest tests.test_mobile_pipeline tests.test_workspace_pipeline
```

Expected: all mobile and workspace pipeline tests pass.

### Task 5: Add End-to-End Release Artifact CLI Coverage

**Files:**
- Modify: `tests/test_cli.py`

- [ ] Add a helper near existing release CLI tests:

```python
    def _assert_release_artifact_set(self, output_dir: Path) -> None:
        manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
        for artifact_name in (
            "evaluation_report",
            "profile_decision_report",
            "dataset_release_report",
            "dataset_release_pack",
            "release_quality_audit",
            "dataset_release_card",
        ):
            self.assertIn(artifact_name, manifest["artifacts"])
            self.assertTrue((output_dir / manifest["artifacts"][artifact_name]).exists())

        release_report = json.loads(
            (output_dir / "dataset_release_report.json").read_text(encoding="utf-8")
        )
        self.assertEqual(release_report["decisions"]["dataset_release"]["status"], "passed")
        self.assertEqual(
            release_report["release_completeness"]["decision"]["status"],
            "passed",
        )
```

- [ ] Add this mobile release CLI test:

```python
    def test_mobile_release_candidate_profile_can_write_release_artifact_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "mobile-release"
            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/mobile-messages-release-candidate.json",
                    "--write-evaluation-report",
                    "--write-profile-decision-report",
                    "--write-dataset-release-report",
                    "--write-dataset-release-pack",
                    "--write-release-quality-audit",
                    "--write-dataset-release-card",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self._assert_release_artifact_set(output_dir)
```

- [ ] Add this workspace release CLI test:

```python
    def test_workspace_release_candidate_profile_can_write_release_artifact_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "workspace-release"
            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/workspace-tasks-release-candidate.json",
                    "--write-evaluation-report",
                    "--write-profile-decision-report",
                    "--write-dataset-release-report",
                    "--write-dataset-release-pack",
                    "--write-release-quality-audit",
                    "--write-dataset-release-card",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self._assert_release_artifact_set(output_dir)
```

- [ ] Run:

```bash
uv run python -m unittest tests.test_cli
```

Expected: all CLI tests pass. If the new helper conflicts with an existing
method name, rename it to `_assert_domain_release_artifact_set`.

### Task 6: Update Release Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/DATA.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/product-specs/framework-mvp.md`

- [ ] In `README.md`, replace the single release-candidate example with three
commands:

```bash
# Release-candidate evidence packs
uv run python main.py --run-profile tests/fixtures/run_profiles/foundation-release-candidate.json --write-evaluation-report --write-profile-decision-report --write-dataset-release-report --write-dataset-release-pack --write-release-quality-audit --write-dataset-release-card --output-dir artifacts/foundation-release-candidate
uv run python main.py --run-profile tests/fixtures/run_profiles/mobile-messages-release-candidate.json --write-evaluation-report --write-profile-decision-report --write-dataset-release-report --write-dataset-release-pack --write-release-quality-audit --write-dataset-release-card --output-dir artifacts/mobile-release-candidate
uv run python main.py --run-profile tests/fixtures/run_profiles/workspace-tasks-release-candidate.json --write-evaluation-report --write-profile-decision-report --write-dataset-release-report --write-dataset-release-pack --write-release-quality-audit --write-dataset-release-card --output-dir artifacts/workspace-release-candidate
uv run python scripts/verify_dataset_release.py --output-dir artifacts/foundation-release-candidate
uv run python scripts/verify_dataset_release.py --output-dir artifacts/mobile-release-candidate
uv run python scripts/verify_dataset_release.py --output-dir artifacts/workspace-release-candidate
```

- [ ] In `docs/DATA.md`, replace the release completeness threshold paragraph
with domain-aware wording:

```markdown
Current release completeness thresholds are domain-aware. All supported local
release-candidate domains require at least `5` accepted samples and at most
`0.2` rejection rate. Contacts require `lookup_contact_email`,
`contact_followup`, and `contact_branch_fallback` task-type coverage. Mobile
requires `mobile_message_lookup`, `mobile_message_to_reminder`,
`mobile_draft_reply`, and `mobile_branch_fallback`. Workspace requires
`workspace_item_lookup`, `workspace_task_creation`, `workspace_comment_update`,
and `workspace_branch_fallback`. Required tool-combination coverage is
descriptor-compatible and domain-specific; dataset release reports store the
exact threshold list used in `release_completeness.thresholds`.
```

- [ ] In `docs/ROADMAP.md`, add a completed Stage 4 bullet after plan 0039:

```markdown
- Harden release-candidate evidence across all three deterministic domains.
  Implemented in plan 0040 with explicit domain-aware release completeness
  thresholds, mobile/workspace release-candidate profiles, deterministic sample
  floor coverage, and end-to-end release artifact smoke tests without
  activating async orchestration or semantic duplicate detection.
```

- [ ] In `docs/product-specs/framework-mvp.md`, update MVP acceptance bullets to
say:

```markdown
- Supports deterministic foundation, contacts scale-probe, and profile-local
  governed source profiles before async orchestration is activated.
- Supports local release-candidate evidence packs for contacts, mobile
  messages, and workspace tasks through explicit evaluation, profile decision,
  dataset release, release pack, release audit, and release card artifacts.
```

- [ ] Run:

```bash
uv run python scripts/validate_docs.py
```

Expected: documentation validation passed.

### Task 7: Full Validation and Completion Handoff

**Files:**
- Modify: `docs/exec-plans/active/0040-multi-domain-release-candidate-evidence-hardening.md`
- Modify after completion: `docs/PLANS.md`
- Move after completion:
  `docs/exec-plans/active/0040-multi-domain-release-candidate-evidence-hardening.md`
  to `docs/exec-plans/completed/0040-multi-domain-release-candidate-evidence-hardening.md`

- [ ] Run the focused suites:

```bash
uv run python -m unittest tests.test_dataset_release tests.test_run_profiles tests.test_mobile_pipeline tests.test_workspace_pipeline tests.test_cli
```

Expected: all focused tests pass.

- [ ] Run the full suite:

```bash
uv run python -m unittest
```

Expected: all tests pass.

- [ ] Run docs validation:

```bash
uv run python scripts/validate_docs.py
```

Expected: documentation validation passed.

- [ ] Run representative release commands:

```bash
uv run python main.py --run-profile tests/fixtures/run_profiles/mobile-messages-release-candidate.json --write-evaluation-report --write-profile-decision-report --write-dataset-release-report --write-dataset-release-pack --write-release-quality-audit --write-dataset-release-card --output-dir artifacts/mobile-release-candidate
uv run python scripts/verify_dataset_release.py --output-dir artifacts/mobile-release-candidate
uv run python main.py --run-profile tests/fixtures/run_profiles/workspace-tasks-release-candidate.json --write-evaluation-report --write-profile-decision-report --write-dataset-release-report --write-dataset-release-pack --write-release-quality-audit --write-dataset-release-card --output-dir artifacts/workspace-release-candidate
uv run python scripts/verify_dataset_release.py --output-dir artifacts/workspace-release-candidate
```

Expected: each `main.py` command exits 0 with `accepted >= 5`, dataset release
decision `passed`, and release completeness `passed`; each verification command
exits 0.

- [ ] Update this plan's status section with completion date and validation
evidence.
- [ ] Move this file to `docs/exec-plans/completed/`.
- [ ] Update `docs/PLANS.md`, `docs/exec-plans/active/README.md`, and
`docs/README.md` so no active plan remains unless a later plan has been chosen.

## Acceptance Criteria

- Contacts release-candidate behavior remains passing.
- Mobile and workspace release-candidate profiles exist and load as
  `profile_purpose: release_candidate`.
- Mobile and workspace deterministic fixture runs produce at least five accepted
  samples and cover required release task types and tool combinations.
- Dataset release completeness uses explicit domain-aware thresholds for all
  three supported domains.
- Undercovered mobile/workspace release-candidate reports return
  `insufficient_evidence`, not `passed`.
- Mobile and workspace CLI release runs can write and verify release packs,
  release quality audits, and release cards.
- No new async orchestration, semantic duplicate detection, external MCP, real
  user data, reward training, or RL behavior is introduced.
- Public artifact schemas remain unchanged.
- `uv run python -m unittest` and `uv run python scripts/validate_docs.py` pass.

## Risks

- Adding extra deterministic candidates can break ordering-sensitive tests.
  Mitigate by asserting task-type coverage rather than exact candidate order
  except where curriculum ordering is already part of a test.
- Domain-aware thresholds can drift from actual deterministic generators.
  Mitigate with CLI release smoke tests that exercise real artifacts.
- Release-pack tests may become slow if duplicated too heavily. Keep the new
  end-to-end tests to one mobile and one workspace smoke path.
- Documentation can overclaim downstream model quality. Keep wording limited to
  local release evidence and avoid claiming downstream improvement.

## Review Checklist

- Release thresholds are explicit for contacts, mobile, and workspace.
- Non-contacts thresholds are not inferred from observed slices.
- New profiles are release candidates, not diagnostic probes.
- New candidates are deterministic, synthetic, and do not read external data.
- Release artifacts are opt-in and do not change default output.
- Docs and README commands match actual fixture filenames.
- Async orchestration and semantic duplicate detection remain deferred.
