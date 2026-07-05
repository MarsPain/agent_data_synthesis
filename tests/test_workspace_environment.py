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


if __name__ == "__main__":
    unittest.main()
