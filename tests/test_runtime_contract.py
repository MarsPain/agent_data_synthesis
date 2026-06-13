from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from synthesis.environments import ContactEnvironment
from synthesis.mobile_environment import MobileMessagesEnvironment


class RuntimeContractTest(unittest.TestCase):
    def test_contacts_fixture_exports_sanitized_runtime_metadata(self) -> None:
        from synthesis.contracts import validate_runtime_metadata_record

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = ContactEnvironment.create_fixture(Path(tmpdir))
            metadata = environment.runtime_metadata().export()

        validate_runtime_metadata_record(metadata)
        serialized = json.dumps(metadata, sort_keys=True)
        self.assertEqual(metadata["schema_version"], "runtime_metadata_v1")
        self.assertEqual(metadata["runtime_id"], "contacts_fixture")
        self.assertEqual(metadata["environment_id"], "contacts_fixture")
        self.assertEqual(metadata["state_backend"], "sqlite")
        self.assertEqual(metadata["checkpoint_strategy"], "sqlite_backup")
        self.assertEqual(metadata["reset_recipe"], "sqlite_fixture:contacts")
        self.assertNotIn("database_path", metadata)
        self.assertNotIn(tmpdir, serialized)
        self.assertNotIn("contacts.sqlite3", serialized)

    def test_mobile_fixture_exports_sanitized_runtime_metadata(self) -> None:
        from synthesis.contracts import validate_runtime_metadata_record

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = MobileMessagesEnvironment.create_fixture(Path(tmpdir))
            metadata = environment.runtime_metadata().export()

        validate_runtime_metadata_record(metadata)
        serialized = json.dumps(metadata, sort_keys=True).lower()
        self.assertEqual(metadata["schema_version"], "runtime_metadata_v1")
        self.assertEqual(metadata["runtime_id"], "mobile_messages_fixture")
        self.assertEqual(metadata["environment_id"], "mobile_messages_fixture")
        self.assertEqual(metadata["state_backend"], "sqlite")
        self.assertEqual(metadata["checkpoint_strategy"], "sqlite_backup")
        self.assertEqual(metadata["reset_recipe"], "sqlite_fixture:mobile_messages")
        self.assertNotIn("real_device", serialized)
        self.assertNotIn("device_id", serialized)
        self.assertNotIn(tmpdir.lower(), serialized)

    def test_contacts_and_mobile_satisfy_shared_runtime_protocol(self) -> None:
        from synthesis.runtime import EnvironmentRuntime

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            contacts = ContactEnvironment.create_fixture(root / "contacts")
            mobile = MobileMessagesEnvironment.create_fixture(root / "mobile")

            for environment in (contacts, mobile):
                with self.subTest(runtime_id=environment.environment_id):
                    self.assertIsInstance(environment, EnvironmentRuntime)
                    checkpoint = environment.checkpoint()
                    rebuilt = environment.rebuild(root / f"rebuilt_{environment.environment_id}")
                    self.assertIsInstance(rebuilt, EnvironmentRuntime)

                    environment.restore_checkpoint(checkpoint)
                    self.assertEqual(
                        environment.runtime_metadata().runtime_id,
                        rebuilt.runtime_metadata().runtime_id,
                    )

    def test_checkpoint_restore_preserves_domain_state_via_runtime_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            contacts = ContactEnvironment.create_fixture(root / "contacts")
            contacts_checkpoint = contacts.checkpoint()
            contacts.record_followup("Alice Zhang", "Send follow-up email.")
            self.assertTrue(contacts.has_followup("Alice Zhang", "Send follow-up email."))
            contacts.restore_checkpoint(contacts_checkpoint)
            self.assertFalse(contacts.has_followup("Alice Zhang", "Send follow-up email."))

            mobile = MobileMessagesEnvironment.create_fixture(root / "mobile")
            mobile_checkpoint = mobile.checkpoint()
            mobile.create_reminder(
                title="Send the project update",
                due_at="tomorrow 9 AM",
                source_message_id="msg_maya_project_update",
            )
            self.assertTrue(
                mobile.has_reminder(
                    title="Send the project update",
                    due_at="tomorrow 9 AM",
                    source_message_id="msg_maya_project_update",
                )
            )
            mobile.restore_checkpoint(mobile_checkpoint)
            self.assertFalse(
                mobile.has_reminder(
                    title="Send the project update",
                    due_at="tomorrow 9 AM",
                    source_message_id="msg_maya_project_update",
                )
            )

    def test_runtime_metadata_safety_rejects_profile_release_paths_prompts_and_secrets(self) -> None:
        from synthesis.contracts import ContractValidationError
        from synthesis.runtime import validate_runtime_metadata_safety

        forbidden_records = (
            {"dataset_version": "dataset_test"},
            {"dataset_release_status": "passed"},
            {"profile_decision": {"status": "passed"}},
            {"profile_purpose": "release_candidate"},
            {"profile_path": "/Users/H/profile.json"},
            {"database_path": "/tmp/contacts.sqlite3"},
            {"provider_prompt": "Generate a task"},
            {"provider_payload": {"messages": []}},
            {"headers": {"authorization": "Bearer secret-test-key"}},
            {"api_key": "secret-test-key"},
            {"environment": {"AGENT_DATA_API_KEY": "secret-test-key"}},
        )
        for record in forbidden_records:
            with self.subTest(record=record):
                with self.assertRaises(ContractValidationError):
                    validate_runtime_metadata_safety(record)


if __name__ == "__main__":
    unittest.main()
