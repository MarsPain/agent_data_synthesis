from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class WorkspaceToolRegistryTest(unittest.TestCase):
    def _environment(self, tmpdir: str):
        from synthesis.workspace_environment import WorkspaceTasksEnvironment

        return WorkspaceTasksEnvironment.create_fixture(Path(tmpdir))

    def test_workspace_registry_exports_exact_tool_set(self) -> None:
        from synthesis.workspace_tools import build_workspace_tool_registry

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = build_workspace_tool_registry(self._environment(tmpdir))

            self.assertEqual(
                registry.tool_names(),
                [
                    "add_workspace_comment",
                    "create_workspace_task",
                    "search_workspace_items",
                ],
            )
            self.assertEqual(
                {tool["name"] for tool in registry.export()},
                {
                    "search_workspace_items",
                    "create_workspace_task",
                    "add_workspace_comment",
                },
            )

    def test_workspace_tools_reject_missing_required_arguments(self) -> None:
        from synthesis.tools import ToolSchemaError
        from synthesis.workspace_tools import build_workspace_tool_registry

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = build_workspace_tool_registry(self._environment(tmpdir))

            cases = (
                ("search_workspace_items", {}, "query"),
                (
                    "create_workspace_task",
                    {"project_id": "project_alpha", "title": "New task"},
                    "priority",
                ),
                (
                    "add_workspace_comment",
                    {"task_id": "task_launch_plan"},
                    "comment",
                ),
            )
            for tool_name, arguments, missing_field in cases:
                with self.subTest(tool=tool_name, field=missing_field):
                    with self.assertRaisesRegex(ToolSchemaError, missing_field):
                        registry.execute(tool_name, arguments)

    def test_workspace_tools_reject_wrong_argument_types(self) -> None:
        from synthesis.tools import ToolSchemaError
        from synthesis.workspace_tools import build_workspace_tool_registry

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = build_workspace_tool_registry(self._environment(tmpdir))

            cases = (
                ("search_workspace_items", {"query": 123}, "query"),
                (
                    "create_workspace_task",
                    {
                        "project_id": "project_alpha",
                        "title": "New task",
                        "priority": ["high"],
                        "due_label": "this_week",
                    },
                    "priority",
                ),
                (
                    "add_workspace_comment",
                    {"task_id": "task_launch_plan", "comment": None},
                    "comment",
                ),
            )
            for tool_name, arguments, field_name in cases:
                with self.subTest(tool=tool_name, field=field_name):
                    with self.assertRaisesRegex(ToolSchemaError, field_name):
                        registry.execute(tool_name, arguments)

    def test_search_workspace_items_is_read_only_and_deterministic(self) -> None:
        from synthesis.workspace_tools import build_workspace_tool_registry

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = self._environment(tmpdir)
            registry = build_workspace_tool_registry(environment)
            checkpoint = registry.checkpoint_state()

            result = registry.execute(
                "search_workspace_items",
                {"query": "launch", "kind": "task"},
            )
            registry.restore_state(checkpoint)
            result_after_restore = registry.execute(
                "search_workspace_items",
                {"query": "launch", "kind": "task"},
            )

        self.assertEqual(result, result_after_restore)
        self.assertEqual(result["kind"], "task")
        self.assertEqual(result["item_id"], "task_launch_plan")
        self.assertNotIn(tmpdir, repr(result))

    def test_mutating_workspace_tools_return_sanitized_state_changes(self) -> None:
        from synthesis.workspace_tools import build_workspace_tool_registry

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = self._environment(tmpdir)
            registry = build_workspace_tool_registry(environment)
            checkpoint = registry.checkpoint_state()

            task = registry.execute(
                "create_workspace_task",
                {
                    "project_id": "project_alpha",
                    "title": "Prepare launch checklist",
                    "priority": "high",
                    "due_label": "this_week",
                },
            )
            comment = registry.execute(
                "add_workspace_comment",
                {
                    "task_id": str(task["task_id"]),
                    "comment": "Added launch checklist owner.",
                },
            )

            self.assertEqual(task["state_change"]["entity"], "workspace_task")
            self.assertEqual(comment["state_change"]["entity"], "workspace_comment")
            self.assertNotIn(tmpdir, repr(task))
            self.assertNotIn(tmpdir, repr(comment))
            self.assertNotIn("database_path", repr(task))
            self.assertNotIn("database_path", repr(comment))
            self.assertTrue(
                environment.has_workspace_task(
                    project_id="project_alpha",
                    title="Prepare launch checklist",
                    priority="high",
                    due_label="this_week",
                )
            )

            registry.restore_state(checkpoint)

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

    def test_workspace_side_effect_metadata_marks_only_mutating_tools(self) -> None:
        from synthesis.workspace_tools import build_workspace_tool_registry

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = build_workspace_tool_registry(self._environment(tmpdir))

            side_effects = {
                str(tool["name"]): str(tool["side_effects"])
                for tool in registry.export()
            }

        self.assertEqual(
            side_effects,
            {
                "search_workspace_items": "read_only",
                "create_workspace_task": "state_mutating",
                "add_workspace_comment": "state_mutating",
            },
        )


if __name__ == "__main__":
    unittest.main()
