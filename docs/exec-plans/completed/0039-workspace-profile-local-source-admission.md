# Plan 0039: Workspace Profile-Local Source Admission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add profile-local JSON source admission for the
`workspace_tasks_fixture` domain while preserving the default fixture-only
workspace path and all current public artifact schemas.

**Architecture:** Reuse the existing profile-local source governance path:
`run_profile_v2.source` declares a local JSON source, `synthesis.domain_sources`
resolves a domain-owned importer, and the importer builds a
`WorkspaceEnvironmentInput` that `synthesis.domain_pipeline` passes into the
workspace environment. Workspace source parsing stays in a new
workspace-owned module; shared governance, source events, manifests, replay,
reward labels, evaluation, and release/profile consumers remain generic.

**Tech Stack:** Python dataclasses, JSON parsing, SQLite fixture environments,
`unittest`, existing `uv run python ...` validation commands.

---

## Status

Completed on 2026-07-05.

Validation evidence:

- `uv run python -m unittest tests.test_run_profiles tests.test_domain_sources tests.test_source_governance tests.test_workspace_environment tests.test_workspace_pipeline`
  - 60 tests passed.
- `uv run python -m unittest tests.test_episode_replay tests.test_reward_labels tests.test_evaluation tests.test_profile_decisions tests.test_dataset_release`
  - 70 tests passed.
- `uv run python -m unittest`
  - 461 tests passed.
- `uv run python scripts/validate_docs.py`
  - documentation validation passed.
- `uv run python main.py --run-profile tests/fixtures/run_profiles/profile-local-workspace-tasks.json --write-episode-replay-report --write-reward-label-report --output-dir artifacts/profile-local-workspace`
  - exited 0 with `accepted=4`, `rejected=0`, replay decision `passed`, and
    reward-label decision `passed`.
- `uv run python main.py --run-profile tests/fixtures/run_profiles/profile-local-workspace-tasks.json --write-evaluation-report --write-profile-decision-report --output-dir artifacts/profile-local-workspace-evaluation`
  - exited 0 with `accepted=4`, `rejected=0`, evaluation decision `passed`,
    and profile promotion `passed`.
- `rg "workspace-tasks-profile|Launch owners, target dates|Assign launch checklist owner" ...`
  over manifest, source-events, quality, replay, reward, evaluation, and
  profile-decision reports returned no matches.

## Why This Plan

Plans 0037 and 0038 completed the third deterministic workspace domain and
retired the runtime compatibility shims. The runtime and consumer boundaries now
support contacts, mobile messages, and workspace tasks consistently.

One intentional gap remains: contacts and mobile messages can be populated from
profile-local governed JSON sources, but `workspace_tasks_fixture` is still
fixture-only. `synthesis.domain_pipeline` currently rejects workspace
`domain_environment_input` with `workspace_tasks_fixture source input is not
supported`, and `synthesis.run_profiles.SOURCE_KINDS` does not include a
workspace source kind.

Closing that gap is the next narrow domain-pack pressure test. It strengthens
the three-domain source-admission contract without activating async
orchestration, semantic duplicate detection, external workspace APIs, external
MCP servers, browser automation, or real user data access.

## Scope

- Add a profile-local workspace JSON source kind:
  `local_workspace_tasks_json`.
- Add a workspace-owned source importer that converts governed JSON bytes into
  `WorkspaceEnvironmentInput`.
- Add internal contract validation for `workspace_tasks_environment_input_v1`.
- Add source provenance fields to `WorkspaceEnvironmentInput` and workspace
  environment metadata in the same sanitized style used by contacts and mobile.
- Let `build_domain_pipeline_bundle(...)` accept `WorkspaceEnvironmentInput`
  for `workspace_tasks_fixture`.
- Add workspace source fixtures and a `run_profile_v2` fixture.
- Add tests proving source governance events, manifests, samples, replay,
  reward labels, evaluation, and profile decisions still work for source-backed
  workspace runs.
- Update docs and plan indexes so active work points at this plan.

## Out of Scope

- External workspace SaaS connectors or real workspace data access.
- Browser automation, external MCP servers, or external tool discovery.
- Controlled network-backed workspace ingestion.
- Async orchestration, distributed workers, cancellation, durable queues, or
  semantic duplicate detection.
- Reward-model training, Agentic RL rollout collection, or model publishing.
- Changing default `uv run python main.py` behavior.
- Changing public dataset, manifest, quality, evaluation, replay,
  reward-label, release, adapter, or runtime artifact schemas.

## File Map

- Create: `synthesis/workspace_sources.py`
  - Workspace-owned parser/importer for `local_workspace_tasks_json`.
- Modify: `synthesis/workspace_environment.py`
  - Add source fields to `WorkspaceEnvironmentInput`.
  - Add `WorkspaceTasksEnvironment.create_from_input(...)`.
  - Preserve source provenance in metadata/reset recipe without leaking paths or
    raw source content.
- Modify: `synthesis/contracts.py`
  - Add `validate_workspace_tasks_environment_input_record(...)`.
  - Add `local_workspace_tasks_json` to run-profile source-kind contracts.
- Modify: `synthesis/domain_sources.py`
  - Register `WorkspaceTasksSourceImporter`.
- Modify: `synthesis/domain_pipeline.py`
  - Accept `WorkspaceEnvironmentInput` for `workspace_tasks_fixture`.
- Modify: `synthesis/run_profiles.py`
  - Add `local_workspace_tasks_json` to `SOURCE_KINDS` and workspace domain
    compatibility.
- Add: `tests/fixtures/run_profiles/workspace-tasks-profile.json`
  - Local governed workspace source payload.
- Add: `tests/fixtures/run_profiles/profile-local-workspace-tasks.json`
  - `run_profile_v2` fixture pointing at the workspace source payload.
- Modify: `tests/test_workspace_environment.py`
  - Validate source-backed workspace input and metadata behavior.
- Modify: `tests/test_domain_sources.py`
  - Cover workspace source importer resolution, import success, and sanitized
    rejection.
- Modify: `tests/test_run_profiles.py`
  - Cover workspace source kind loading, sanitized metadata, and mismatch rules.
- Modify: `tests/test_workspace_pipeline.py`
  - Cover source-backed workspace domain bundle behavior.
- Modify: `tests/test_source_governance.py`
  - Cover source-backed workspace pipeline artifacts and source event redaction.
- Modify: `tests/test_episode_replay.py`, `tests/test_reward_labels.py`, and
  `tests/test_cli.py` for source-backed workspace report regressions.
- Modify: `README.md`, `docs/DESIGN.md`, `docs/BACKEND.md`, `docs/DATA.md`,
  `docs/ROADMAP.md`.
  - Describe workspace profile-local source support as local JSON only.
- Modify: `docs/PLANS.md`, `docs/exec-plans/active/README.md`.
  - Track this plan as active.

## Data Contract

The accepted workspace source payload shape is:

```json
{
  "projects": [
    {"project_id": "project_alpha", "name": "Alpha Launch", "status": "active"}
  ],
  "tasks": [
    {
      "task_id": "task_launch_plan",
      "project_id": "project_alpha",
      "title": "Finalize launch plan",
      "priority": "high",
      "due_label": "this_week",
      "status": "open",
      "created_at": "1970-01-01T00:00:00Z"
    }
  ],
  "documents": [
    {
      "document_id": "doc_launch_brief",
      "project_id": "project_alpha",
      "title": "Launch Brief",
      "body": "Launch owners, target dates, and rollout criteria."
    }
  ],
  "comments": [
    {
      "comment_id": "comment_task_launch_plan_owner",
      "task_id": "task_launch_plan",
      "body": "Assign launch checklist owner before review.",
      "created_at": "1970-01-01T00:00:00Z"
    }
  ]
}
```

The internal exported environment-input record shape is:

```python
{
    "schema_version": "workspace_tasks_environment_input_v1",
    "projects": [project.export() for project in self.projects],
    "tasks": [task.export() for task in self.tasks],
    "documents": [document.export() for document in self.documents],
    "comments": [comment.export() for comment in self.comments],
    "source_bundle_id": self.source_bundle_id,
    "source_policy_hash": self.source_policy_hash,
}
```

Validation rules:

- `projects`, `tasks`, `documents`, and `comments` must be lists.
- Every project must have non-empty `project_id`, `name`, and `status`.
- Every task must have non-empty `task_id`, `project_id`, `title`, `priority`,
  `due_label`, `status`, and `created_at`.
- Every document must have non-empty `document_id`, `project_id`, `title`, and
  `body`.
- Every comment must have non-empty `comment_id`, `task_id`, `body`, and
  `created_at`.
- Each task and document `project_id` must reference a declared project.
- Each comment `task_id` must reference a declared task.
- `source_policy_hash`, when present, must match `sha256:<64 lowercase hex>`.
- Validation errors must not include raw payload content, source filenames, or
  host paths.

## Implementation Tasks

### Task 1: Add Workspace Source Fixture and Run-Profile Red Tests

**Files:**
- Add: `tests/fixtures/run_profiles/workspace-tasks-profile.json`
- Add: `tests/fixtures/run_profiles/profile-local-workspace-tasks.json`
- Modify: `tests/test_run_profiles.py`
- Modify: `tests/test_domain_sources.py`

- [ ] Add `tests/fixtures/run_profiles/workspace-tasks-profile.json`:

```json
{
  "projects": [
    {"project_id": "project_alpha", "name": "Alpha Launch", "status": "active"},
    {"project_id": "project_beta", "name": "Beta Research", "status": "active"}
  ],
  "tasks": [
    {
      "task_id": "task_launch_plan",
      "project_id": "project_alpha",
      "title": "Finalize launch plan",
      "priority": "high",
      "due_label": "this_week",
      "status": "open",
      "created_at": "1970-01-01T00:00:00Z"
    },
    {
      "task_id": "task_metrics_review",
      "project_id": "project_alpha",
      "title": "Review launch metrics dashboard",
      "priority": "medium",
      "due_label": "next_week",
      "status": "open",
      "created_at": "1970-01-01T00:00:00Z"
    },
    {
      "task_id": "task_research_notes",
      "project_id": "project_beta",
      "title": "Summarize customer research notes",
      "priority": "medium",
      "due_label": "later",
      "status": "open",
      "created_at": "1970-01-01T00:00:00Z"
    }
  ],
  "documents": [
    {
      "document_id": "doc_launch_brief",
      "project_id": "project_alpha",
      "title": "Launch Brief",
      "body": "Launch owners, target dates, and rollout criteria."
    },
    {
      "document_id": "doc_research_summary",
      "project_id": "project_beta",
      "title": "Research Summary",
      "body": "Customer feedback themes and open questions."
    }
  ],
  "comments": [
    {
      "comment_id": "comment_task_launch_plan_owner",
      "task_id": "task_launch_plan",
      "body": "Assign launch checklist owner before review.",
      "created_at": "1970-01-01T00:00:00Z"
    },
    {
      "comment_id": "comment_task_research_notes_source",
      "task_id": "task_research_notes",
      "body": "Link research notes to the summary document.",
      "created_at": "1970-01-01T00:00:00Z"
    }
  ]
}
```

- [ ] Add `tests/fixtures/run_profiles/profile-local-workspace-tasks.json`:

```json
{
  "schema_version": "run_profile_v2",
  "profile_id": "profile_local_workspace_tasks",
  "dataset_version": "dataset_profile_local_workspace_tasks",
  "profile_purpose": "diagnostic_probe",
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
  "generation": {"mode": "workspace_fixture"},
  "features": {},
  "source": {
    "kind": "local_workspace_tasks_json",
    "source_id": "source_profile_workspace_tasks_v1",
    "path": "workspace-tasks-profile.json",
    "license_label": "cc-by-4.0",
    "max_bytes": 65536
  }
}
```

- [ ] In `tests/test_run_profiles.py`, add:

```python
    def test_v2_profile_loads_local_workspace_source_with_sanitized_metadata(self) -> None:
        from synthesis.run_profiles import load_run_profile

        profile = load_run_profile(
            Path("tests/fixtures/run_profiles/profile-local-workspace-tasks.json")
        )

        self.assertEqual(profile.schema_version, "run_profile_v2")
        self.assertIsNotNone(profile.source)
        assert profile.source is not None
        self.assertEqual(profile.seed.domain, "workspace_tasks_fixture")
        self.assertEqual(profile.source.kind, "local_workspace_tasks_json")
        self.assertEqual(
            profile.source.source_id,
            "source_profile_workspace_tasks_v1",
        )
        self.assertEqual(profile.source.relative_path, "workspace-tasks-profile.json")
        self.assertEqual(profile.source.resolved_path.name, "workspace-tasks-profile.json")
        self.assertNotIn("workspace-tasks-profile.json", json.dumps(profile.sanitized_metadata()))
        self.assertNotIn("Finalize launch plan", json.dumps(profile.sanitized_metadata()))

        metadata = profile.sanitized_metadata(
            source_summary={
                "kind": "local_workspace_tasks_json",
                "source_id": "source_profile_workspace_tasks_v1",
                "content_hash": "sha256:" + "1" * 64,
                "license_label": "cc-by-4.0",
                "source_policy_hash": "sha256:" + "2" * 64,
            }
        )
        self.assertEqual(metadata["source"]["kind"], "local_workspace_tasks_json")
        self.assertNotIn("path", metadata["source"])
```

- [ ] In `tests/test_run_profiles.py`, update
  `test_v2_source_rejects_domain_source_kind_mismatches` so the mismatch set
  includes the new cross-domain cases and no longer treats
  `("workspace_tasks_fixture", "local_workspace_tasks_json")` as invalid:

```python
        mismatches = (
            ("contacts", "local_mobile_messages_json"),
            ("contacts", "local_workspace_tasks_json"),
            ("mobile_messages_fixture", "local_contacts_json"),
            ("mobile_messages_fixture", "local_workspace_tasks_json"),
            ("workspace_tasks_fixture", "local_contacts_json"),
            ("workspace_tasks_fixture", "local_mobile_messages_json"),
        )
```

- [ ] In `tests/test_domain_sources.py`, add the failing importer test:

```python
    def test_workspace_importer_uses_shared_profile_local_governance(self) -> None:
        from synthesis.domain_sources import (
            ProfileLocalDomainSourceRequest,
            build_profile_local_domain_source_input,
            resolve_domain_source_importer,
        )
        from synthesis.workspace_environment import WorkspaceEnvironmentInput

        importer = resolve_domain_source_importer(
            "workspace_tasks_fixture",
            "local_workspace_tasks_json",
        )
        source_import = build_profile_local_domain_source_input(
            ProfileLocalDomainSourceRequest(
                domain_id="workspace_tasks_fixture",
                kind="local_workspace_tasks_json",
                source_id="source_profile_workspace_tasks_v1",
                path=Path("tests/fixtures/run_profiles/workspace-tasks-profile.json"),
                license_label="cc-by-4.0",
                max_bytes=65536,
            ),
            importer=importer,
        )

        self.assertEqual(source_import.domain_id, "workspace_tasks_fixture")
        self.assertEqual(source_import.source_kind, "local_workspace_tasks_json")
        self.assertIsInstance(source_import.environment_input, WorkspaceEnvironmentInput)
        self.assertEqual(source_import.source_summary["kind"], "local_workspace_tasks_json")
        exported = json.dumps(source_import.events, sort_keys=True)
        self.assertNotIn("workspace-tasks-profile.json", exported)
        self.assertNotIn("Finalize launch plan", exported)
        self.assertNotIn("Launch owners", exported)
```

- [ ] Run:

```bash
uv run python -m unittest tests.test_run_profiles tests.test_domain_sources
```

- [ ] Expected result before implementation:
  - `test_v2_profile_loads_local_workspace_source_with_sanitized_metadata`
    fails because `local_workspace_tasks_json` is not in `SOURCE_KINDS`.
  - `test_workspace_importer_uses_shared_profile_local_governance` fails
    because `resolve_domain_source_importer(...)` has no workspace importer.

### Task 2: Add Workspace Environment Input Contract

**Files:**
- Modify: `synthesis/contracts.py`
- Modify: `tests/test_workspace_environment.py`

- [ ] In `tests/test_workspace_environment.py`, add a contract-valid export
  test:

```python
    def test_workspace_environment_input_export_is_contract_valid(self) -> None:
        from synthesis.contracts import validate_workspace_tasks_environment_input_record
        from synthesis.workspace_environment import (
            WorkspaceCommentRecord,
            WorkspaceDocumentRecord,
            WorkspaceEnvironmentInput,
            WorkspaceProjectRecord,
            WorkspaceTaskRecord,
        )

        environment_input = WorkspaceEnvironmentInput(
            projects=(WorkspaceProjectRecord("project_alpha", "Alpha Launch", "active"),),
            tasks=(
                WorkspaceTaskRecord(
                    "task_launch_plan",
                    "project_alpha",
                    "Finalize launch plan",
                    "high",
                    "this_week",
                ),
            ),
            documents=(
                WorkspaceDocumentRecord(
                    "doc_launch_brief",
                    "project_alpha",
                    "Launch Brief",
                    "Launch owners, target dates, and rollout criteria.",
                ),
            ),
            comments=(
                WorkspaceCommentRecord(
                    "comment_task_launch_plan_owner",
                    "task_launch_plan",
                    "Assign launch checklist owner before review.",
                ),
            ),
            source_bundle_id="bundle_source_workspace_tasks_v1",
            source_policy_hash="sha256:" + "1" * 64,
        )

        validate_workspace_tasks_environment_input_record(environment_input.export())
```

- [ ] In `tests/test_workspace_environment.py`, add invalid-reference tests:

```python
    def test_workspace_environment_input_contract_rejects_invalid_references(self) -> None:
        from synthesis.contracts import (
            ContractValidationError,
            validate_workspace_tasks_environment_input_record,
        )

        valid = _valid_workspace_environment_input()
        invalid_records = (
            (
                {
                    **valid,
                    "tasks": [
                        {
                            **valid["tasks"][0],
                            "project_id": "missing_project",
                        }
                    ],
                },
                "project_id",
            ),
            (
                {
                    **valid,
                    "comments": [
                        {
                            **valid["comments"][0],
                            "task_id": "missing_task",
                        }
                    ],
                },
                "task_id",
            ),
            ({**valid, "source_policy_hash": "not-a-hash"}, "source_policy_hash"),
        )
        for record, expected in invalid_records:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(ContractValidationError, expected):
                    validate_workspace_tasks_environment_input_record(record)
```

- [ ] Add a test helper at the bottom of `tests/test_workspace_environment.py`:

```python
def _valid_workspace_environment_input() -> dict[str, object]:
    return {
        "schema_version": "workspace_tasks_environment_input_v1",
        "projects": [
            {"project_id": "project_alpha", "name": "Alpha Launch", "status": "active"}
        ],
        "tasks": [
            {
                "task_id": "task_launch_plan",
                "project_id": "project_alpha",
                "title": "Finalize launch plan",
                "priority": "high",
                "due_label": "this_week",
                "status": "open",
                "created_at": "1970-01-01T00:00:00Z",
            }
        ],
        "documents": [
            {
                "document_id": "doc_launch_brief",
                "project_id": "project_alpha",
                "title": "Launch Brief",
                "body": "Launch owners, target dates, and rollout criteria.",
            }
        ],
        "comments": [
            {
                "comment_id": "comment_task_launch_plan_owner",
                "task_id": "task_launch_plan",
                "body": "Assign launch checklist owner before review.",
                "created_at": "1970-01-01T00:00:00Z",
            }
        ],
        "source_bundle_id": "bundle_source_workspace_tasks_v1",
        "source_policy_hash": "sha256:" + "1" * 64,
    }
```

- [ ] Run:

```bash
uv run python -m unittest tests.test_workspace_environment
```

- [ ] Expected result before implementation: failure because
  `validate_workspace_tasks_environment_input_record` does not exist and
  `WorkspaceEnvironmentInput` does not accept source fields.

- [ ] In `synthesis/workspace_environment.py`, extend
  `WorkspaceEnvironmentInput`:

```python
@dataclass(frozen=True)
class WorkspaceEnvironmentInput:
    projects: tuple[WorkspaceProjectRecord, ...]
    tasks: tuple[WorkspaceTaskRecord, ...]
    documents: tuple[WorkspaceDocumentRecord, ...]
    comments: tuple[WorkspaceCommentRecord, ...]
    source_bundle_id: str | None = None
    source_policy_hash: str | None = None

    def export(self) -> dict[str, object]:
        return {
            "schema_version": "workspace_tasks_environment_input_v1",
            "projects": [project.export() for project in self.projects],
            "tasks": [task.export() for task in self.tasks],
            "documents": [document.export() for document in self.documents],
            "comments": [comment.export() for comment in self.comments],
            "source_bundle_id": self.source_bundle_id,
            "source_policy_hash": self.source_policy_hash,
        }
```

- [ ] In `synthesis/contracts.py`, add
  `validate_workspace_tasks_environment_input_record(record: Mapping[str, Any])`
  near the existing environment-input validators. Use explicit checks for
  required keys, lists, non-empty string fields, cross references, and optional
  source hash format. The implementation must call `_require_mapping`,
  `_require_list`, `_require_non_empty_string`, and `_require_sha256` helpers
  already used by adjacent validators where available.

- [ ] In `synthesis/contracts.py`, add
  `"local_workspace_tasks_json"` to `RUN_PROFILE_SOURCE_KINDS`.

- [ ] Re-run:

```bash
uv run python -m unittest tests.test_workspace_environment
```

- [ ] Expected result after implementation: workspace environment tests pass.

### Task 3: Implement Workspace Source Importer

**Files:**
- Add: `synthesis/workspace_sources.py`
- Modify: `synthesis/domain_sources.py`
- Test: `tests/test_domain_sources.py`

- [ ] Create `synthesis/workspace_sources.py` with this public importer shape:

```python
from __future__ import annotations

import json

from synthesis.contracts import (
    ContractValidationError,
    validate_workspace_tasks_environment_input_record,
)
from synthesis.workspace_environment import (
    WorkspaceCommentRecord,
    WorkspaceDocumentRecord,
    WorkspaceEnvironmentInput,
    WorkspaceProjectRecord,
    WorkspaceTaskRecord,
)


class WorkspaceTasksSourceImporter:
    domain_id = "workspace_tasks_fixture"
    source_kind = "local_workspace_tasks_json"

    def build_environment_input(
        self,
        content: bytes,
        *,
        source_bundle_id: str,
        source_policy_hash: str,
    ) -> WorkspaceEnvironmentInput:
        try:
            document = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("environment source JSON is invalid") from exc
        if not isinstance(document, dict):
            raise ValueError("environment source payload must be an object")

        environment_input = WorkspaceEnvironmentInput(
            projects=_projects_from_payload(document.get("projects")),
            tasks=_tasks_from_payload(document.get("tasks")),
            documents=_documents_from_payload(document.get("documents")),
            comments=_comments_from_payload(document.get("comments")),
            source_bundle_id=source_bundle_id,
            source_policy_hash=source_policy_hash,
        )
        try:
            validate_workspace_tasks_environment_input_record(environment_input.export())
        except ContractValidationError as exc:
            raise ValueError("environment source payload is invalid") from exc
        return environment_input
```

- [ ] In the same file, add parser helpers:

```python
def _projects_from_payload(value: object) -> tuple[WorkspaceProjectRecord, ...]:
    return tuple(
        WorkspaceProjectRecord(
            project_id=str(project.get("project_id", "")) if isinstance(project, dict) else "",
            name=str(project.get("name", "")) if isinstance(project, dict) else "",
            status=str(project.get("status", "")) if isinstance(project, dict) else "",
        )
        for project in _list_or_empty(value)
    )


def _tasks_from_payload(value: object) -> tuple[WorkspaceTaskRecord, ...]:
    return tuple(
        WorkspaceTaskRecord(
            task_id=str(task.get("task_id", "")) if isinstance(task, dict) else "",
            project_id=str(task.get("project_id", "")) if isinstance(task, dict) else "",
            title=str(task.get("title", "")) if isinstance(task, dict) else "",
            priority=str(task.get("priority", "")) if isinstance(task, dict) else "",
            due_label=str(task.get("due_label", "")) if isinstance(task, dict) else "",
            status=str(task.get("status", "open")) if isinstance(task, dict) else "open",
            created_at=(
                str(task.get("created_at", "1970-01-01T00:00:00Z"))
                if isinstance(task, dict)
                else "1970-01-01T00:00:00Z"
            ),
        )
        for task in _list_or_empty(value)
    )


def _documents_from_payload(value: object) -> tuple[WorkspaceDocumentRecord, ...]:
    return tuple(
        WorkspaceDocumentRecord(
            document_id=(
                str(document.get("document_id", ""))
                if isinstance(document, dict)
                else ""
            ),
            project_id=(
                str(document.get("project_id", ""))
                if isinstance(document, dict)
                else ""
            ),
            title=str(document.get("title", "")) if isinstance(document, dict) else "",
            body=str(document.get("body", "")) if isinstance(document, dict) else "",
        )
        for document in _list_or_empty(value)
    )


def _comments_from_payload(value: object) -> tuple[WorkspaceCommentRecord, ...]:
    return tuple(
        WorkspaceCommentRecord(
            comment_id=(
                str(comment.get("comment_id", ""))
                if isinstance(comment, dict)
                else ""
            ),
            task_id=str(comment.get("task_id", "")) if isinstance(comment, dict) else "",
            body=str(comment.get("body", "")) if isinstance(comment, dict) else "",
            created_at=(
                str(comment.get("created_at", "1970-01-01T00:00:00Z"))
                if isinstance(comment, dict)
                else "1970-01-01T00:00:00Z"
            ),
        )
        for comment in _list_or_empty(value)
    )


def _list_or_empty(value: object) -> list[object]:
    return value if isinstance(value, list) else []
```

- [ ] In `synthesis/domain_sources.py`, import and register the importer:

```python
from synthesis.workspace_sources import WorkspaceTasksSourceImporter
```

```python
        (
            "workspace_tasks_fixture",
            "local_workspace_tasks_json",
        ): WorkspaceTasksSourceImporter(),
```

- [ ] Add a sanitized rejection test to `tests/test_domain_sources.py`:

```python
    def test_workspace_profile_local_source_rejects_payload_without_leaking_content(self) -> None:
        from synthesis.domain_sources import (
            ProfileLocalDomainSourceRequest,
            build_profile_local_domain_source_input,
            resolve_domain_source_importer,
        )
        from synthesis.sources import ControlledSourceFetchError

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "workspace.json"
            path.write_text(
                json.dumps(
                    {
                        "projects": [
                            {
                                "project_id": "project_alpha",
                                "name": "Alpha Launch",
                                "status": "active",
                            }
                        ],
                        "tasks": [
                            {
                                "task_id": "task_bad",
                                "project_id": "missing_project",
                                "title": "Leaky raw workspace task",
                                "priority": "high",
                                "due_label": "today",
                            }
                        ],
                        "documents": [],
                        "comments": [],
                    }
                ),
                encoding="utf-8",
            )
            importer = resolve_domain_source_importer(
                "workspace_tasks_fixture",
                "local_workspace_tasks_json",
            )

            with self.assertRaisesRegex(
                ControlledSourceFetchError,
                "environment source",
            ) as raised:
                build_profile_local_domain_source_input(
                    ProfileLocalDomainSourceRequest(
                        domain_id="workspace_tasks_fixture",
                        kind="local_workspace_tasks_json",
                        source_id="source_workspace_bad",
                        path=path,
                        license_label="cc-by-4.0",
                        max_bytes=65536,
                    ),
                    importer=importer,
                )

        exported = json.dumps(raised.exception.events, sort_keys=True)
        self.assertNotIn(str(path), exported)
        self.assertNotIn("workspace.json", exported)
        self.assertNotIn("Leaky raw workspace task", exported)
```

- [ ] Run:

```bash
uv run python -m unittest tests.test_domain_sources
```

- [ ] Expected result: domain source tests pass, including sanitized workspace
  import success and rejection.

### Task 4: Enable Source-Backed Workspace Environment and Domain Bundle

**Files:**
- Modify: `synthesis/workspace_environment.py`
- Modify: `synthesis/domain_pipeline.py`
- Modify: `tests/test_workspace_environment.py`
- Modify: `tests/test_workspace_pipeline.py`

- [ ] In `tests/test_workspace_environment.py`, add source-backed environment
  behavior:

```python
    def test_create_from_input_persists_workspace_records_and_source_metadata(self) -> None:
        from synthesis.workspace_environment import (
            WorkspaceEnvironmentInput,
            WorkspaceProjectRecord,
            WorkspaceTaskRecord,
            WorkspaceTasksEnvironment,
        )

        environment_input = WorkspaceEnvironmentInput(
            projects=(WorkspaceProjectRecord("project_custom", "Custom Workspace", "active"),),
            tasks=(
                WorkspaceTaskRecord(
                    "task_custom_plan",
                    "project_custom",
                    "Prepare custom launch plan",
                    "high",
                    "today",
                ),
            ),
            documents=(),
            comments=(),
            source_bundle_id="bundle_source_workspace_tasks_v1",
            source_policy_hash="sha256:" + "1" * 64,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = WorkspaceTasksEnvironment.create_from_input(
                Path(tmpdir),
                environment_input,
                source_provenance={"source_policy_hash": "sha256:" + "1" * 64},
            )
            result = environment.search_workspace_items(query="custom", kind="task")
            metadata = environment.metadata()

        self.assertEqual(result["item_id"], "task_custom_plan")
        self.assertEqual(metadata.source_provenance["source_policy_hash"], "sha256:" + "1" * 64)
        self.assertEqual(
            metadata.reset_recipe["source_bundle_id"],
            "bundle_source_workspace_tasks_v1",
        )
        self.assertEqual(
            metadata.reset_recipe["source_policy_hash"],
            "sha256:" + "1" * 64,
        )
        self.assertNotIn(tmpdir, repr(metadata.reset_recipe))
```

- [ ] In `synthesis/workspace_environment.py`, import the validator:

```python
from synthesis.contracts import validate_workspace_tasks_environment_input_record
```

- [ ] In `synthesis/workspace_environment.py`, add
  `WorkspaceTasksEnvironment.create_from_input(...)`:

```python
    @classmethod
    def create_from_input(
        cls,
        output_dir: Path,
        environment_input: WorkspaceEnvironmentInput,
        *,
        source_provenance: dict[str, object] | None = None,
    ) -> "WorkspaceTasksEnvironment":
        validate_workspace_tasks_environment_input_record(environment_input.export())
        output_dir.mkdir(parents=True, exist_ok=True)
        database_path = output_dir / "workspace_tasks.sqlite3"
        if database_path.exists():
            database_path.unlink()
        environment = cls(
            database_path,
            source_provenance=source_provenance,
            source_input=environment_input,
        )
        with closing(environment.connect()) as connection:
            with connection:
                _create_schema(connection)
                _insert_workspace_input(connection, environment_input)
        return environment
```

- [ ] Update `WorkspaceTasksEnvironment.__init__(...)`:

```python
    def __init__(
        self,
        database_path: Path,
        *,
        source_provenance: dict[str, object] | None = None,
        source_input: WorkspaceEnvironmentInput | None = None,
    ) -> None:
        self.database_path = database_path
        self.source_provenance = source_provenance
        self.source_input = source_input
```

- [ ] Update `WorkspaceTasksEnvironment.metadata(...)` so source-backed
  environments include sanitized source fields:

```python
        reset_recipe: dict[str, object] = {
            "type": "sqlite_fixture",
            "fixture": "workspace_tasks",
            "database": self.database_path.name,
            "tables": [
                "workspace_projects",
                "workspace_tasks",
                "workspace_documents",
                "workspace_comments",
            ],
        }
        if self.source_input is not None:
            reset_recipe.update(
                {
                    "source_bundle_id": self.source_input.source_bundle_id,
                    "source_policy_hash": self.source_input.source_policy_hash,
                }
            )
        return EnvironmentMetadata(
            environment_id=self.environment_id,
            version=self.version,
            reset_recipe=reset_recipe,
            source_provenance=self.source_provenance,
        )
```

- [ ] Update `WorkspaceTasksEnvironment.rebuild(...)` to preserve the current
  deterministic fixture behavior. Source-backed replay rebuild remains driven by
  descriptor seeds and does not serialize raw source payloads:

```python
    def rebuild(self, output_dir: Path) -> "WorkspaceTasksEnvironment":
        return type(self).create_fixture(output_dir)
```

- [ ] In `tests/test_workspace_pipeline.py`, add source input bundle behavior:

```python
    def test_domain_bundle_can_build_workspace_from_source_input(self) -> None:
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.workspace_environment import (
            WorkspaceEnvironmentInput,
            WorkspaceProjectRecord,
            WorkspaceTaskRecord,
        )

        environment_input = WorkspaceEnvironmentInput(
            projects=(WorkspaceProjectRecord("project_custom", "Custom Workspace", "active"),),
            tasks=(
                WorkspaceTaskRecord(
                    "task_custom_plan",
                    "project_custom",
                    "Prepare custom launch plan",
                    "high",
                    "today",
                ),
            ),
            documents=(),
            comments=(),
            source_bundle_id="bundle_source_workspace_tasks_v1",
            source_policy_hash="sha256:" + "1" * 64,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle = build_domain_pipeline_bundle(
                workspace_seed(),
                Path(tmpdir),
                source_provenance={"source_policy_hash": "sha256:" + "1" * 64},
                domain_environment_input=environment_input,
            )
            result = bundle.environment.search_workspace_items(query="custom", kind="task")

        self.assertEqual(result["item_id"], "task_custom_plan")
```

- [ ] In `synthesis/domain_pipeline.py`, import `WorkspaceEnvironmentInput`:

```python
from synthesis.workspace_environment import WorkspaceEnvironmentInput, WorkspaceTasksEnvironment
```

- [ ] Replace the workspace source rejection branch with type validation and
  input forwarding:

```python
    if seed.domain == "workspace_tasks_fixture":
        if (
            domain_environment_input is not None
            and not isinstance(domain_environment_input, WorkspaceEnvironmentInput)
        ):
            raise ValueError(
                "workspace_tasks_fixture source input must be WorkspaceEnvironmentInput"
            )
        return _build_workspace_bundle(
            output_dir,
            source_provenance=source_provenance,
            workspace_environment_input=domain_environment_input,
            enable_mcp_adapter=enable_mcp_adapter,
        )
```

- [ ] Update `_build_workspace_bundle(...)` to accept
  `source_provenance` and `workspace_environment_input`, then choose between
  `WorkspaceTasksEnvironment.create_fixture(...)` and
  `WorkspaceTasksEnvironment.create_from_input(...)`.

- [ ] Run:

```bash
uv run python -m unittest tests.test_workspace_environment tests.test_workspace_pipeline
```

- [ ] Expected result: workspace environment and pipeline tests pass.

### Task 5: Wire Run Profiles and Source Governance Pipeline

**Files:**
- Modify: `synthesis/run_profiles.py`
- Modify: `tests/test_run_profiles.py`
- Modify: `tests/test_source_governance.py`

- [ ] In `synthesis/run_profiles.py`, add the new source kind:

```python
SOURCE_KINDS = {
    "local_contacts_json",
    "local_mobile_messages_json",
    "local_workspace_tasks_json",
}
```

- [ ] In `_validate_source_domain_compatibility(...)`, add workspace support:

```python
    allowed = {
        "contacts_fixture": {"local_contacts_json"},
        "mobile_messages_fixture": {"local_mobile_messages_json"},
        "workspace_tasks_fixture": {"local_workspace_tasks_json"},
    }
```

- [ ] In `tests/test_source_governance.py`, add source-backed workspace pipeline
  coverage:

```python
    def test_profile_local_workspace_source_runs_pipeline_with_sanitized_events(self) -> None:
        from synthesis.domain_sources import (
            ProfileLocalDomainSourceRequest,
            build_profile_local_domain_source_input,
            resolve_domain_source_importer,
        )
        from synthesis.pipeline import run_foundation_pipeline
        from tests.test_workspace_pipeline import workspace_seed

        importer = resolve_domain_source_importer(
            "workspace_tasks_fixture",
            "local_workspace_tasks_json",
        )
        source_input = build_profile_local_domain_source_input(
            ProfileLocalDomainSourceRequest(
                domain_id="workspace_tasks_fixture",
                kind="local_workspace_tasks_json",
                source_id="source_profile_workspace_tasks_v1",
                path=Path("tests/fixtures/run_profiles/workspace-tasks-profile.json"),
                license_label="cc-by-4.0",
                max_bytes=65536,
            ),
            importer=importer,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_foundation_pipeline(
                Path(tmpdir),
                dataset_version="dataset_profile_local_workspace_tasks",
                seed=workspace_seed(),
                source_bundle=source_input.source_bundle,
                domain_environment_input=source_input.environment_input,
                source_events=source_input.events,
                enable_source_audit=True,
            )

            self.assertEqual(result.accepted_count, 4)
            self.assertIsNotNone(result.source_events_path)
            sample = json.loads(result.samples_path.read_text(encoding="utf-8").splitlines()[0])
            provenance = sample["lineage"]["source_provenance"]
            self.assertEqual(provenance["source_ids"], ["source_profile_workspace_tasks_v1"])
            self.assertEqual(provenance["source_kinds"], ["local_file"])
            self.assertEqual(
                sample["environment"]["reset_recipe"]["source_bundle_id"],
                source_input.environment_input.source_bundle_id,
            )
            exported = (
                result.samples_path.read_text(encoding="utf-8")
                + result.rejections_path.read_text(encoding="utf-8")
                + result.manifest_path.read_text(encoding="utf-8")
                + result.source_events_path.read_text(encoding="utf-8")
            )
            self.assertNotIn("workspace-tasks-profile.json", exported)
            self.assertNotIn("Launch owners, target dates", exported)
```

- [ ] Run:

```bash
uv run python -m unittest tests.test_run_profiles tests.test_source_governance tests.test_domain_sources
```

- [ ] Expected result: run-profile, source-governance, and domain-source tests
  pass.

### Task 6: Add CLI-Level Source-Backed Workspace Regression

**Files:**
- Modify: `tests/test_cli.py`
- Test fixture: `tests/fixtures/run_profiles/profile-local-workspace-tasks.json`

- [ ] In `tests/test_cli.py`, add a focused CLI regression next to
  `test_main_can_run_profile_local_mobile_messages_source`:

```python
    def test_main_can_run_profile_local_workspace_tasks_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "workspace-profile-local"

            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--run-profile",
                    "tests/fixtures/run_profiles/profile-local-workspace-tasks.json",
                    "--write-episode-quality-report",
                    "--write-episode-replay-report",
                    "--write-reward-label-report",
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((output_dir / "source_events.jsonl").exists(), result.stdout)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["accepted_count"], 4)
            self.assertEqual(
                manifest["run_profile"]["source"]["kind"],
                "local_workspace_tasks_json",
            )
            self.assertEqual(
                manifest["run_profile"]["source"]["source_id"],
                "source_profile_workspace_tasks_v1",
            )
            quality_report = json.loads(
                (output_dir / "episode_quality_report.json").read_text(encoding="utf-8")
            )
            replay_report = json.loads(
                (output_dir / "episode_replay_report.json").read_text(encoding="utf-8")
            )
            reward_report = json.loads(
                (output_dir / "reward_label_report.json").read_text(encoding="utf-8")
            )
            self.assertGreater(
                quality_report["observed"]["runtime_counts"]["workspace_tasks_fixture"],
                0,
            )
            self.assertGreater(
                replay_report["observed"]["runtime_counts"]["workspace_tasks_fixture"],
                0,
            )
            self.assertGreater(
                reward_report["observed"]["runtime_counts"]["workspace_tasks_fixture"],
                0,
            )
            exported_metadata = (
                (output_dir / "manifest.json").read_text(encoding="utf-8")
                + (output_dir / "source_events.jsonl").read_text(encoding="utf-8")
                + (output_dir / "quality_report.json").read_text(encoding="utf-8")
                + (output_dir / "episode_quality_report.json").read_text(encoding="utf-8")
                + (output_dir / "episode_replay_report.json").read_text(encoding="utf-8")
                + (output_dir / "reward_label_report.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("workspace-tasks-profile.json", exported_metadata)
            self.assertNotIn("Launch owners, target dates", exported_metadata)
            self.assertIn("accepted=4", result.stdout)
```

- [ ] Run:

```bash
uv run python -m unittest tests.test_workspace_pipeline tests.test_cli tests.test_foundation_pipeline
```

- [ ] Expected result: source-backed workspace profile runs through the same
  deterministic synchronous pipeline and produces accepted candidates plus
  source-event evidence.

### Task 7: Consumer Regression for Source-Backed Workspace Evidence

**Files:**
- Modify: `tests/test_episode_replay.py`
- Modify: `tests/test_reward_labels.py`
- Modify: `tests/test_evaluation.py` or `tests/test_profile_decisions.py` only
  if no existing command-level coverage checks these reports for the source
  profile.

- [ ] Add or extend a test that builds source-backed workspace episodes and
  verifies replay still passes without workspace-specific consumer allowlists.
  Use the same helper pattern as existing workspace tests:

```python
    def test_source_backed_workspace_replay_uses_descriptor_boundary(self) -> None:
        from synthesis.episode_replay import build_episode_replay_report

        episodes = (_source_backed_workspace_episode("candidate_workspace_launch_checklist_task"),)

        report = build_episode_replay_report(
            dataset_version="dataset_source_backed_workspace_replay",
            episodes=episodes,
        )

        self.assertEqual(report["decision"]["status"], "passed")
        self.assertEqual(
            report["observed"]["runtime_counts"],
            {"workspace_tasks_fixture": 1},
        )
```

- [ ] Add or extend a reward-label test for the same source-backed workspace
  episode:

```python
    def test_source_backed_workspace_reward_labels_remain_usable(self) -> None:
        from synthesis.episode_quality import build_episode_quality_report
        from synthesis.episode_replay import build_episode_replay_report
        from synthesis.reward_labels import build_reward_labels

        episodes = (_source_backed_workspace_episode("candidate_workspace_launch_checklist_task"),)
        labels = build_reward_labels(
            episodes=episodes,
            episode_quality_report=build_episode_quality_report(
                dataset_version="dataset_source_backed_workspace_reward",
                episodes=episodes,
            ),
            episode_replay_report=build_episode_replay_report(
                dataset_version="dataset_source_backed_workspace_reward",
                episodes=episodes,
            ),
        )

        self.assertEqual(labels[0]["runtime_id"], "workspace_tasks_fixture")
        self.assertEqual(labels[0]["label_status"], "usable")
```

- [ ] If adding `_source_backed_workspace_episode(...)`, keep it test-local and
  build it by:
  - importing `build_profile_local_domain_source_input(...)`;
  - resolving `local_workspace_tasks_json`;
  - building a `workspace_seed()` bundle with `domain_environment_input`;
  - executing the existing scripted policy;
  - exporting `awm_runtime.build_episode_log(...)`.

- [ ] Run:

```bash
uv run python -m unittest tests.test_episode_replay tests.test_reward_labels
```

- [ ] Expected result: replay and reward-label tests pass without adding
  workspace-specific logic to consumer modules.

### Task 8: Documentation and Plan Index Updates

**Files:**
- Modify: `README.md`
- Modify: `docs/DESIGN.md`
- Modify: `docs/BACKEND.md`
- Modify: `docs/DATA.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/PLANS.md`
- Modify: `docs/exec-plans/active/README.md`

- [ ] Update `README.md`:
  - Mention that profile-local JSON sources are supported for contacts, mobile
    messages, and workspace tasks.
  - Add the source-backed workspace profile command to "Common Runs":

```bash
uv run python main.py --run-profile tests/fixtures/run_profiles/profile-local-workspace-tasks.json --write-episode-replay-report --write-reward-label-report --output-dir artifacts/profile-local-workspace
```

- [ ] Update `docs/DESIGN.md`:
  - Change workspace from fixture-only to local profile-source capable.
  - State that workspace source ingestion is local JSON only and still excludes
    external workspace APIs, browser profiles, credentials, and real user data.

- [ ] Update `docs/BACKEND.md`:
  - Add `synthesis.workspace_sources` to proposed module boundaries.
  - Replace the current statement that workspace source input is unsupported.
  - Keep controlled network ingestion contacts-only.

- [ ] Update `docs/DATA.md`:
  - Add `workspace_tasks_environment_input_v1`.
  - Add `local_workspace_tasks_json` to run-profile source kinds.
  - Document the workspace source payload shape and sanitization rules.

- [ ] Update `docs/ROADMAP.md`:
  - Record this plan as the post-0038 workspace source-admission step.
  - Keep async orchestration and semantic duplicate detection deferred under
    their existing trigger conditions.

- [ ] Update `docs/PLANS.md` and `docs/exec-plans/active/README.md`:
  - Track this plan as active.

- [ ] Run:

```bash
uv run python scripts/validate_docs.py
```

- [ ] Expected result: documentation validation passes.

### Task 9: Full Regression and Representative Commands

**Files:**
- Runtime outputs under `artifacts/`.

- [ ] Run focused source/workspace tests:

```bash
uv run python -m unittest tests.test_run_profiles tests.test_domain_sources tests.test_source_governance tests.test_workspace_environment tests.test_workspace_pipeline
```

- [ ] Run focused consumer tests:

```bash
uv run python -m unittest tests.test_episode_replay tests.test_reward_labels tests.test_evaluation tests.test_profile_decisions tests.test_dataset_release
```

- [ ] Run full suite:

```bash
uv run python -m unittest
```

- [ ] Run docs validation:

```bash
uv run python scripts/validate_docs.py
```

- [ ] Run representative source-backed workspace replay/reward command:

```bash
uv run python main.py --run-profile tests/fixtures/run_profiles/profile-local-workspace-tasks.json --write-episode-replay-report --write-reward-label-report --output-dir artifacts/profile-local-workspace
```

- [ ] Expected result:
  - command exits 0;
  - `accepted=4`;
  - `rejected=0`;
  - `source_events.jsonl` exists;
  - `episode_replay_report.json` decision is `passed`;
  - `reward_label_report.json` decision is `passed`;
  - no source filename, host path, or raw workspace body appears in source
    events, manifest source metadata, or report summaries.

- [ ] Run representative source-backed workspace evaluation/profile command:

```bash
uv run python main.py --run-profile tests/fixtures/run_profiles/profile-local-workspace-tasks.json --write-evaluation-report --write-profile-decision-report --output-dir artifacts/profile-local-workspace-evaluation
```

- [ ] Expected result:
  - command exits 0;
  - `accepted=4`;
  - `rejected=0`;
  - evaluation decision is `passed`;
  - profile promotion is `passed`;
  - async orchestration and semantic duplicate detection remain `defer`.

### Task 10: Complete Plan Lifecycle

**Files:**
- Move: `docs/exec-plans/active/0039-workspace-profile-local-source-admission.md`
  to `docs/exec-plans/completed/0039-workspace-profile-local-source-admission.md`
- Modify: `docs/PLANS.md`
- Modify: `docs/exec-plans/active/README.md`
- Modify: `docs/exec-plans/completed/README.md`
- Modify: `AGENTS.md`
- Modify: `docs/README.md`

- [ ] After implementation and validation, update this plan status to:

```markdown
Completed on 2026-07-05.
```

- [ ] Add validation evidence under the status section, including focused tests,
  full `unittest`, docs validation, and the two representative workspace source
  commands.

- [ ] Move this plan from `active/` to `completed/`.

- [ ] Update `docs/PLANS.md`:
  - remove this plan from Active;
  - add it to Completed;
  - keep plan 0014 and `TD-0002` deferred unless their documented triggers are
    met.

- [ ] Update `docs/exec-plans/active/README.md` and
  `docs/exec-plans/completed/README.md`.

- [ ] Update `AGENTS.md` and `docs/README.md` latest completed work pointers.

- [ ] Run:

```bash
uv run python scripts/validate_docs.py
```

- [ ] Expected result: all plan lifecycle links remain valid.

## Acceptance Criteria

- `run_profile_v2` accepts `local_workspace_tasks_json` only for
  `workspace_tasks_fixture`.
- Contacts cannot use workspace source kinds; mobile cannot use workspace source
  kinds; workspace cannot use contacts or mobile source kinds.
- `WorkspaceTasksSourceImporter` converts governed local JSON bytes into
  `WorkspaceEnvironmentInput`.
- `WorkspaceTasksEnvironment.create_from_input(...)` creates a deterministic
  SQLite workspace environment from source-backed input.
- Workspace source provenance appears only as sanitized source ids, bundle ids,
  policy hashes, license labels, and source kinds.
- No artifact leaks local source filenames, absolute paths, raw workspace
  document bodies, or raw task/comment content through source events or
  high-level report summaries.
- Source-backed workspace runs produce the same candidate count and existing
  public artifact schemas as fixture-backed workspace runs.
- Replay, reward labels, evaluation, profile decisions, release/profile
  consumers, local adapters, and runtime descriptors remain generic and do not
  add workspace-specific allowlists.
- Controlled network source ingestion remains contacts-only.
- Async orchestration, semantic duplicate detection, external MCP servers,
  external workspace APIs, browser automation, reward-model training, Agentic
  RL, and separate `awm_runtime` publishing remain deferred.

## Validation

- `uv run python -m unittest tests.test_run_profiles tests.test_domain_sources`
- `uv run python -m unittest tests.test_workspace_environment`
- `uv run python -m unittest tests.test_workspace_environment tests.test_workspace_pipeline`
- `uv run python -m unittest tests.test_run_profiles tests.test_source_governance tests.test_domain_sources`
- `uv run python -m unittest tests.test_workspace_pipeline tests.test_cli tests.test_foundation_pipeline`
- `uv run python -m unittest tests.test_episode_replay tests.test_reward_labels`
- `uv run python -m unittest tests.test_run_profiles tests.test_domain_sources tests.test_source_governance tests.test_workspace_environment tests.test_workspace_pipeline`
- `uv run python -m unittest tests.test_episode_replay tests.test_reward_labels tests.test_evaluation tests.test_profile_decisions tests.test_dataset_release`
- `uv run python -m unittest`
- `uv run python scripts/validate_docs.py`
- `uv run python main.py --run-profile tests/fixtures/run_profiles/profile-local-workspace-tasks.json --write-episode-replay-report --write-reward-label-report --output-dir artifacts/profile-local-workspace`
- `uv run python main.py --run-profile tests/fixtures/run_profiles/profile-local-workspace-tasks.json --write-evaluation-report --write-profile-decision-report --output-dir artifacts/profile-local-workspace-evaluation`
