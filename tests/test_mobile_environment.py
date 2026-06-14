from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


class MobileMessagesEnvironmentTest(unittest.TestCase):
    def test_mobile_environment_input_export_is_contract_valid(self) -> None:
        from synthesis.contracts import validate_mobile_messages_environment_input_record
        from synthesis.mobile_environment import (
            MessageRecord,
            MessageThreadRecord,
            MobileMessagesEnvironmentInput,
        )

        environment_input = MobileMessagesEnvironmentInput(
            threads=(MessageThreadRecord("thread_maya", "Maya"),),
            messages=(
                MessageRecord(
                    message_id="msg_maya_project_update",
                    thread_id="thread_maya",
                    sender="Maya",
                    body="Can you remind me to send the project update tomorrow at 9 AM?",
                    received_at="2026-06-12T08:00:00Z",
                ),
            ),
            source_bundle_id="bundle_source_mobile_messages_v1",
            source_policy_hash="sha256:" + "1" * 64,
        )

        validate_mobile_messages_environment_input_record(environment_input.export())

    def test_mobile_environment_can_create_from_source_input(self) -> None:
        from synthesis.mobile_environment import (
            MessageRecord,
            MessageThreadRecord,
            MobileMessagesEnvironment,
            MobileMessagesEnvironmentInput,
        )

        environment_input = MobileMessagesEnvironmentInput(
            threads=(MessageThreadRecord("thread_maya", "Maya"),),
            messages=(
                MessageRecord(
                    message_id="msg_maya_project_update",
                    thread_id="thread_maya",
                    sender="Maya",
                    body="Can you remind me to send the project update tomorrow at 9 AM?",
                    received_at="2026-06-12T08:00:00Z",
                ),
            ),
            source_bundle_id="bundle_source_mobile_messages_v1",
            source_policy_hash="sha256:" + "1" * 64,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = MobileMessagesEnvironment.create_from_input(
                Path(tmpdir),
                environment_input,
                source_provenance={"source_policy_hash": "sha256:" + "1" * 64},
            )
            match = environment.search_messages(query="project update", participant="Maya")

        self.assertEqual(match["message_id"], "msg_maya_project_update")
        self.assertEqual(
            environment.metadata().source_provenance["source_policy_hash"],
            "sha256:" + "1" * 64,
        )

    def test_fixture_creates_tables_and_deterministic_data(self) -> None:
        from synthesis.mobile_environment import MobileMessagesEnvironment

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = MobileMessagesEnvironment.create_fixture(Path(tmpdir))

            with closing(sqlite3.connect(environment.database_path)) as connection:
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                thread_count = connection.execute(
                    "SELECT COUNT(*) FROM message_threads"
                ).fetchone()[0]
                message_count = connection.execute(
                    "SELECT COUNT(*) FROM messages"
                ).fetchone()[0]

            self.assertEqual(
                tables,
                {"message_threads", "messages", "reminders", "draft_replies"},
            )
            self.assertGreaterEqual(thread_count, 3)
            self.assertGreaterEqual(message_count, 3)

    def test_search_messages_filters_by_query_and_participant(self) -> None:
        from synthesis.mobile_environment import MobileMessagesEnvironment

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = MobileMessagesEnvironment.create_fixture(Path(tmpdir))

            result = environment.search_messages(
                query="project update",
                participant="Maya",
            )

            self.assertEqual(result["message_id"], "msg_maya_project_update")
            self.assertEqual(result["thread_id"], "thread_maya")
            self.assertEqual(result["participant"], "Maya")
            self.assertIn("project update", result["snippet"])

    def test_create_reminder_and_state_inspection(self) -> None:
        from synthesis.mobile_environment import MobileMessagesEnvironment

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = MobileMessagesEnvironment.create_fixture(Path(tmpdir))

            result = environment.create_reminder(
                title="Send the project update",
                due_at="tomorrow 9 AM",
                source_message_id="msg_maya_project_update",
            )

            self.assertEqual(result["reminder_id"], "reminder_msg_maya_project_update")
            self.assertEqual(result["state_change"]["entity"], "mobile_reminder")
            self.assertTrue(
                environment.has_reminder(
                    title="Send the project update",
                    due_at="tomorrow 9 AM",
                    source_message_id="msg_maya_project_update",
                )
            )

    def test_draft_reply_and_state_inspection(self) -> None:
        from synthesis.mobile_environment import MobileMessagesEnvironment

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = MobileMessagesEnvironment.create_fixture(Path(tmpdir))

            result = environment.draft_reply(
                thread_id="thread_alex",
                body="I will be five minutes late.",
            )

            self.assertEqual(result["draft_id"], "draft_thread_alex")
            self.assertEqual(result["state_change"]["entity"], "mobile_draft_reply")
            self.assertTrue(
                environment.has_draft_reply(
                    thread_id="thread_alex",
                    body="I will be five minutes late.",
                )
            )

    def test_checkpoint_restore_rolls_back_mutations(self) -> None:
        from synthesis.mobile_environment import MobileMessagesEnvironment

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = MobileMessagesEnvironment.create_fixture(Path(tmpdir))
            checkpoint = environment.checkpoint()

            environment.create_reminder(
                title="Send the project update",
                due_at="tomorrow 9 AM",
                source_message_id="msg_maya_project_update",
            )
            environment.draft_reply(
                thread_id="thread_alex",
                body="I will be five minutes late.",
            )

            environment.restore_checkpoint(checkpoint)

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

    def test_metadata_is_sanitized(self) -> None:
        from synthesis.mobile_environment import MobileMessagesEnvironment

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = MobileMessagesEnvironment.create_fixture(Path(tmpdir))

            metadata = environment.metadata()

            self.assertEqual(metadata.environment_id, "mobile_messages_fixture")
            self.assertEqual(metadata.version, "env_mobile_messages_v1")
            self.assertEqual(metadata.reset_recipe["type"], "sqlite_fixture")
            self.assertEqual(metadata.reset_recipe["database"], "mobile_messages.sqlite3")
            self.assertNotIn(str(tmpdir), repr(metadata.reset_recipe))

    def test_mobile_environment_input_contract_rejects_invalid_references(self) -> None:
        from synthesis.contracts import (
            ContractValidationError,
            validate_mobile_messages_environment_input_record,
        )

        invalid_records = (
            ({"threads": []}, "threads must contain at least one"),
            ({"messages": []}, "messages must contain at least one"),
            (
                {
                    "messages": [
                        {
                            "message_id": "msg_unknown",
                            "thread_id": "missing_thread",
                            "sender": "Maya",
                            "body": "Body",
                            "received_at": "2026-06-12T08:00:00Z",
                        }
                    ]
                },
                "messages.0.thread_id",
            ),
            (
                {
                    "reminders": [
                        {
                            "reminder_id": "reminder_missing",
                            "title": "Follow up",
                            "due_at": None,
                            "source_message_id": "missing_message",
                            "created_at": "1970-01-01T00:00:00Z",
                        }
                    ]
                },
                "reminders.0.source_message_id",
            ),
            (
                {
                    "draft_replies": [
                        {
                            "draft_id": "draft_missing",
                            "thread_id": "missing_thread",
                            "body": "Reply",
                            "created_at": "1970-01-01T00:00:00Z",
                        }
                    ]
                },
                "draft_replies.0.thread_id",
            ),
            ({"source_policy_hash": "not-a-hash"}, "source_policy_hash"),
        )

        for override, message in invalid_records:
            with self.subTest(message=message):
                record = _valid_mobile_environment_input()
                record.update(override)
                with self.assertRaisesRegex(ContractValidationError, message):
                    validate_mobile_messages_environment_input_record(record)


def _valid_mobile_environment_input() -> dict[str, object]:
    return {
        "schema_version": "mobile_messages_environment_input_v1",
        "threads": [{"thread_id": "thread_maya", "participant": "Maya"}],
        "messages": [
            {
                "message_id": "msg_maya_project_update",
                "thread_id": "thread_maya",
                "sender": "Maya",
                "body": "Can you remind me to send the project update tomorrow at 9 AM?",
                "received_at": "2026-06-12T08:00:00Z",
            }
        ],
        "reminders": [],
        "draft_replies": [],
        "source_bundle_id": "bundle_source_mobile_messages_v1",
        "source_policy_hash": "sha256:" + "1" * 64,
    }


if __name__ == "__main__":
    unittest.main()
