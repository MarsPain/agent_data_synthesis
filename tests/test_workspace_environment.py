from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


class WorkspaceTasksEnvironmentTest(unittest.TestCase):
    def test_fixture_creates_deterministic_workspace_records(self) -> None:
        from synthesis.workspace_environment import WorkspaceTasksEnvironment

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = WorkspaceTasksEnvironment.create_fixture(Path(tmpdir))

            with closing(sqlite3.connect(environment.database_path)) as connection:
                project_count = connection.execute(
                    "SELECT COUNT(*) FROM workspace_projects"
                ).fetchone()[0]
                task_count = connection.execute(
                    "SELECT COUNT(*) FROM workspace_tasks"
                ).fetchone()[0]
                document_count = connection.execute(
                    "SELECT COUNT(*) FROM workspace_documents"
                ).fetchone()[0]
                comment_count = connection.execute(
                    "SELECT COUNT(*) FROM workspace_comments"
                ).fetchone()[0]

            self.assertGreaterEqual(project_count, 2)
            self.assertGreaterEqual(task_count, 3)
            self.assertGreaterEqual(document_count, 2)
            self.assertGreaterEqual(comment_count, 2)

    def test_search_workspace_items_returns_sanitized_task_summary(self) -> None:
        from synthesis.workspace_environment import WorkspaceTasksEnvironment

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = WorkspaceTasksEnvironment.create_fixture(Path(tmpdir))

            result = environment.search_workspace_items(query="launch", kind="task")

        self.assertEqual(result["kind"], "task")
        self.assertEqual(result["item_id"], "task_launch_plan")
        self.assertEqual(result["project_id"], "project_alpha")
        self.assertIn("launch", str(result["summary"]).lower())
        self.assertNotIn(tmpdir, repr(result))
        self.assertNotIn("database_path", repr(result))

    def test_task_and_comment_creation_are_inspectable(self) -> None:
        from synthesis.workspace_environment import WorkspaceTasksEnvironment

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = WorkspaceTasksEnvironment.create_fixture(Path(tmpdir))

            task = environment.create_workspace_task(
                project_id="project_alpha",
                title="Prepare launch checklist",
                priority="high",
                due_label="this_week",
            )
            comment = environment.add_workspace_comment(
                task_id=str(task["task_id"]),
                comment="Added launch checklist owner.",
            )

            self.assertEqual(task["state_change"]["entity"], "workspace_task")
            self.assertEqual(comment["state_change"]["entity"], "workspace_comment")
            self.assertTrue(
                environment.has_workspace_task(
                    project_id="project_alpha",
                    title="Prepare launch checklist",
                    priority="high",
                    due_label="this_week",
                )
            )
            self.assertTrue(
                environment.has_workspace_comment(
                    task_id=str(task["task_id"]),
                    comment="Added launch checklist owner.",
                )
            )

    def test_checkpoint_restore_rolls_back_created_task_and_comment(self) -> None:
        from synthesis.workspace_environment import WorkspaceTasksEnvironment

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = WorkspaceTasksEnvironment.create_fixture(Path(tmpdir))
            checkpoint = environment.checkpoint()
            task = environment.create_workspace_task(
                project_id="project_alpha",
                title="Prepare launch checklist",
                priority="high",
                due_label="this_week",
            )
            environment.add_workspace_comment(
                task_id=str(task["task_id"]),
                comment="Added launch checklist owner.",
            )

            environment.restore_checkpoint(checkpoint)

            self.assertFalse(
                environment.has_workspace_task(
                    project_id="project_alpha",
                    title="Prepare launch checklist",
                    priority="high",
                    due_label="this_week",
                )
            )
            self.assertFalse(
                environment.has_workspace_comment(
                    task_id=str(task["task_id"]),
                    comment="Added launch checklist owner.",
                )
            )

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

    def test_metadata_and_runtime_metadata_are_sanitized(self) -> None:
        from awm_runtime import validate_runtime_metadata_safety
        from synthesis.contracts import validate_runtime_metadata_record
        from synthesis.workspace_environment import WorkspaceTasksEnvironment

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = WorkspaceTasksEnvironment.create_fixture(Path(tmpdir))

            metadata = environment.metadata()
            runtime_metadata = environment.runtime_metadata().export()

        self.assertEqual(metadata.environment_id, "workspace_tasks_fixture")
        self.assertEqual(metadata.version, "env_workspace_tasks_v1")
        self.assertEqual(metadata.reset_recipe["type"], "sqlite_fixture")
        self.assertEqual(metadata.reset_recipe["database"], "workspace_tasks.sqlite3")
        self.assertNotIn(tmpdir, repr(metadata.reset_recipe))

        validate_runtime_metadata_record(runtime_metadata)
        validate_runtime_metadata_safety(runtime_metadata)
        self.assertEqual(runtime_metadata["runtime_id"], "workspace_tasks_fixture")
        self.assertEqual(runtime_metadata["environment_id"], "workspace_tasks_fixture")
        forbidden_fragments = (
            "dataset",
            "profile",
            "release",
            "provider",
            "raw_payload",
            "source_payload",
            tmpdir,
        )
        for fragment in forbidden_fragments:
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, repr(runtime_metadata).lower())


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


if __name__ == "__main__":
    unittest.main()
