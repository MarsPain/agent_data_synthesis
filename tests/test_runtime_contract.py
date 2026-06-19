from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from synthesis.environments import ContactEnvironment
from synthesis.mobile_environment import MobileMessagesEnvironment


class RuntimeContractTest(unittest.TestCase):
    def test_runtime_descriptor_exports_capability_contract(self) -> None:
        from synthesis.runtime import RuntimeCapabilityDescriptor
        from synthesis.seeds import DomainSeed

        descriptor = RuntimeCapabilityDescriptor(
            runtime_id="fake_runtime",
            runtime_version="runtime_fake_v1",
            domain_id="fake_domain",
            supports_rebuild=True,
            supports_checkpoint_restore=True,
            supports_episode_replay=True,
            supports_reward_labels=True,
            supports_local_adapter=False,
            state_changing_tools=("fake_write",),
            task_taxonomy=("fake_lookup",),
            rebuild_seed=DomainSeed(
                seed_id="seed_fake_v1",
                domain="fake_runtime",
                description="Fake runtime used by registry contract tests.",
                task_taxonomy=("fake_lookup",),
            ),
            descriptor_metadata={"adapter_support": "none"},
        )

        self.assertEqual(descriptor.runtime_id, "fake_runtime")
        self.assertEqual(descriptor.domain_id, "fake_domain")
        self.assertTrue(descriptor.supports_episode_replay)
        self.assertTrue(descriptor.supports_reward_labels)
        self.assertFalse(descriptor.supports_local_adapter)
        self.assertEqual(descriptor.state_changing_tools, ("fake_write",))

    def test_runtime_descriptor_safety_rejects_profile_release_paths_prompts_and_secrets(
        self,
    ) -> None:
        from synthesis.contracts import ContractValidationError
        from synthesis.runtime import RuntimeCapabilityDescriptor

        forbidden_metadata = (
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
            {"raw_source": {"contacts": []}},
        )
        for metadata in forbidden_metadata:
            with self.subTest(metadata=metadata):
                with self.assertRaises(ContractValidationError):
                    RuntimeCapabilityDescriptor(
                        runtime_id="fake_runtime",
                        runtime_version="runtime_fake_v1",
                        domain_id="fake_domain",
                        supports_rebuild=False,
                        supports_checkpoint_restore=False,
                        supports_episode_replay=False,
                        supports_reward_labels=False,
                        supports_local_adapter=False,
                        state_changing_tools=(),
                        task_taxonomy=("fake_lookup",),
                        descriptor_metadata=metadata,
                    )

    def test_default_runtime_registry_contains_contacts_and_mobile_descriptors(self) -> None:
        from synthesis.runtime import registered_runtime_ids, runtime_descriptor

        self.assertEqual(
            registered_runtime_ids(),
            ("contacts_fixture", "mobile_messages_fixture"),
        )

        contacts = runtime_descriptor("contacts_fixture")
        self.assertEqual(contacts.domain_id, "contacts_fixture")
        self.assertTrue(contacts.supports_episode_replay)
        self.assertTrue(contacts.supports_reward_labels)
        self.assertTrue(contacts.supports_local_adapter)
        self.assertIn("record_contact_followup", contacts.state_changing_tools)

        mobile = runtime_descriptor("mobile_messages_fixture")
        self.assertEqual(mobile.domain_id, "mobile_messages_fixture")
        self.assertTrue(mobile.supports_episode_replay)
        self.assertTrue(mobile.supports_reward_labels)
        self.assertFalse(mobile.supports_local_adapter)
        self.assertIn("create_phone_reminder", mobile.state_changing_tools)

    def test_runtime_registry_rejects_unknown_and_duplicate_runtime_ids(self) -> None:
        from synthesis.contracts import ContractValidationError
        from synthesis.runtime import (
            RuntimeCapabilityDescriptor,
            RuntimeRegistry,
            registered_runtime_ids,
            runtime_descriptor,
        )

        descriptor = RuntimeCapabilityDescriptor(
            runtime_id="fake_runtime",
            runtime_version="runtime_fake_v1",
            domain_id="fake_domain",
            supports_rebuild=False,
            supports_checkpoint_restore=False,
            supports_episode_replay=False,
            supports_reward_labels=True,
            supports_local_adapter=False,
            state_changing_tools=("fake_write",),
            task_taxonomy=("fake_lookup",),
        )

        registry = RuntimeRegistry((descriptor,))
        self.assertEqual(registered_runtime_ids(registry), ("fake_runtime",))
        self.assertIs(runtime_descriptor("fake_runtime", registry), descriptor)
        with self.assertRaises(KeyError):
            runtime_descriptor("missing_runtime", registry)
        with self.assertRaises(ContractValidationError):
            RuntimeRegistry((descriptor, descriptor))

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
