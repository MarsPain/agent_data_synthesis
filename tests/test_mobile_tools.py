from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class MobileToolRegistryTest(unittest.TestCase):
    def _environment(self, tmpdir: str):
        from synthesis.mobile_environment import MobileMessagesEnvironment

        return MobileMessagesEnvironment.create_fixture(Path(tmpdir))

    def test_mobile_registry_exports_exact_tool_set(self) -> None:
        from synthesis.mobile_tools import build_mobile_tool_registry

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = build_mobile_tool_registry(self._environment(tmpdir))

            self.assertEqual(
                registry.tool_names(),
                [
                    "create_phone_reminder",
                    "draft_message_reply",
                    "search_phone_messages",
                ],
            )
            self.assertEqual(
                {tool["name"] for tool in registry.export()},
                {
                    "search_phone_messages",
                    "create_phone_reminder",
                    "draft_message_reply",
                },
            )

    def test_mobile_tools_validate_required_string_arguments(self) -> None:
        from synthesis.mobile_tools import build_mobile_tool_registry

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = build_mobile_tool_registry(self._environment(tmpdir))

            cases = (
                ("search_phone_messages", {"query": ""}, "query"),
                ("create_phone_reminder", {"title": ""}, "title"),
                (
                    "draft_message_reply",
                    {"thread_id": "", "body": "I will be late."},
                    "thread_id",
                ),
                (
                    "draft_message_reply",
                    {"thread_id": "thread_alex", "body": ""},
                    "body",
                ),
            )
            for tool_name, arguments, expected_message in cases:
                with self.subTest(tool=tool_name, field=expected_message):
                    with self.assertRaisesRegex(ValueError, expected_message):
                        registry.execute(tool_name, arguments)

    def test_mutating_mobile_tools_return_state_change_and_restore(self) -> None:
        from synthesis.mobile_tools import build_mobile_tool_registry

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = self._environment(tmpdir)
            registry = build_mobile_tool_registry(environment)
            checkpoint = registry.checkpoint_state()

            reminder = registry.execute(
                "create_phone_reminder",
                {
                    "title": "Send the project update",
                    "due_at": "tomorrow 9 AM",
                    "source_message_id": "msg_maya_project_update",
                },
            )
            draft = registry.execute(
                "draft_message_reply",
                {
                    "thread_id": "thread_alex",
                    "body": "I will be five minutes late.",
                },
            )

            self.assertEqual(reminder["state_change"]["entity"], "mobile_reminder")
            self.assertEqual(draft["state_change"]["entity"], "mobile_draft_reply")
            self.assertTrue(
                environment.has_reminder(
                    title="Send the project update",
                    due_at="tomorrow 9 AM",
                    source_message_id="msg_maya_project_update",
                )
            )

            registry.restore_state(checkpoint)

            self.assertFalse(
                environment.has_reminder(
                    title="Send the project update",
                    due_at="tomorrow 9 AM",
                    source_message_id="msg_maya_project_update",
                )
            )
            self.assertFalse(
                environment.has_draft_reply(
                    thread_id="thread_alex",
                    body="I will be five minutes late.",
                )
            )


if __name__ == "__main__":
    unittest.main()
