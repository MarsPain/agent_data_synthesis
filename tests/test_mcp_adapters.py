from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class LocalContactsMcpAdapterTest(unittest.TestCase):
    def test_manifest_exports_environment_tools_source_and_capabilities(self) -> None:
        from synthesis.contracts import validate_adapter_manifest_record
        from synthesis.environments import ContactEnvironment
        from synthesis.mcp import LocalContactsAdapterShim
        from synthesis.tools import build_contact_tool_registry

        source_policy_hash = "sha256:" + "1" * 64
        source_provenance = {
            "source_bundle_id": "bundle_fixture_contacts_v1",
            "source_policy_hash": source_policy_hash,
            "source_ids": ["source_fixture_contacts"],
            "source_kinds": ["fixture"],
            "license_labels": ["fixture_internal"],
            "license_outcomes": ["allowed"],
            "external_source_eligible": False,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = ContactEnvironment.create_fixture(
                Path(tmpdir),
                source_provenance=source_provenance,
            )
            adapter = LocalContactsAdapterShim(
                environment=environment,
                registry=build_contact_tool_registry(environment),
            )

            manifest = adapter.manifest.export()

        self.assertEqual(manifest["schema_version"], "mcp_adapter_manifest_v1")
        self.assertEqual(manifest["adapter_id"], "contacts_local_mcp_adapter")
        self.assertEqual(manifest["protocol_label"], "mcp-compatible-local-shim")
        self.assertEqual(manifest["environment"]["id"], "contacts_fixture")
        self.assertEqual(manifest["source_policy_hash"], source_policy_hash)
        self.assertEqual(manifest["supported_operations"], ["tool.call"])
        self.assertTrue(manifest["capabilities"]["reset"])
        self.assertTrue(manifest["capabilities"]["checkpoint"])
        self.assertIn("lookup_contact_email", [tool["name"] for tool in manifest["tools"]])
        self.assertIn("state_mutating", manifest["side_effect_classes"])
        validate_adapter_manifest_record(manifest)

    def test_shimmed_tool_call_preserves_observation_and_state(self) -> None:
        from synthesis.contracts import validate_adapter_call_result_record
        from synthesis.environments import ContactEnvironment
        from synthesis.mcp import LocalContactsAdapterShim, ToolCallRequest
        from synthesis.tools import build_contact_tool_registry

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = ContactEnvironment.create_fixture(Path(tmpdir))
            adapter = LocalContactsAdapterShim(
                environment=environment,
                registry=build_contact_tool_registry(environment),
            )
            checkpoint = environment.checkpoint()

            result = adapter.call_tool(
                ToolCallRequest(
                    call_id="call_lookup_alice",
                    adapter_id=adapter.manifest.adapter_id,
                    tool_name="lookup_contact_email",
                    arguments={"name": "Alice Zhang"},
                )
            )
            followup = adapter.call_tool(
                ToolCallRequest(
                    call_id="call_followup_alice",
                    adapter_id=adapter.manifest.adapter_id,
                    tool_name="record_contact_followup",
                    arguments={"name": "Alice Zhang", "note": "Send a note."},
                )
            )

            self.assertEqual(result.observation["email"], "alice.zhang@example.test")
            self.assertEqual(followup.side_effect_summary["class"], "state_mutating")
            self.assertTrue(environment.has_followup("Alice Zhang", "Send a note."))
            environment.restore_checkpoint(checkpoint)
            self.assertFalse(environment.has_followup("Alice Zhang", "Send a note."))
            validate_adapter_call_result_record(result.export())
            validate_adapter_call_result_record(followup.export())

    def test_unknown_tool_returns_classified_adapter_rejection(self) -> None:
        from synthesis.environments import ContactEnvironment
        from synthesis.mcp import LocalContactsAdapterShim, ToolCallRequest
        from synthesis.tools import build_contact_tool_registry

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = ContactEnvironment.create_fixture(Path(tmpdir))
            adapter = LocalContactsAdapterShim(
                environment=environment,
                registry=build_contact_tool_registry(environment),
            )

            result = adapter.call_tool(
                ToolCallRequest(
                    call_id="call_missing",
                    adapter_id=adapter.manifest.adapter_id,
                    tool_name="missing_tool",
                    arguments={},
                )
            )

        self.assertEqual(result.execution_status, "rejected")
        self.assertEqual(result.error["cause"], "tool_missing")
        self.assertIn("available_tools", result.error["details"])


class RuntimeBackedLocalAdapterTest(unittest.TestCase):
    def test_contacts_manifest_is_runtime_backed_and_preserves_existing_identity(self) -> None:
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.mcp import LocalRuntimeAdapterShim
        from synthesis.runtime import runtime_descriptor
        from synthesis.seeds import foundation_seed

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle = build_domain_pipeline_bundle(foundation_seed(), Path(tmpdir))
            adapter = LocalRuntimeAdapterShim(
                descriptor=runtime_descriptor("contacts_fixture"),
                session=bundle.runtime_session(),
            )

            manifest = adapter.manifest.export()

        self.assertEqual(manifest["adapter_id"], "contacts_local_mcp_adapter")
        self.assertEqual(manifest["environment"]["id"], "contacts_fixture")
        self.assertEqual(manifest["environment"]["version"], "contacts_fixture_v1")
        self.assertEqual(manifest["supported_operations"], ["tool.call"])
        self.assertTrue(manifest["capabilities"]["reset"])
        self.assertTrue(manifest["capabilities"]["checkpoint"])
        self.assertIn("lookup_contact_email", [tool["name"] for tool in manifest["tools"]])

    def test_tool_call_maps_through_runtime_action_and_redacts_unsafe_arguments(self) -> None:
        from synthesis.contracts import validate_adapter_call_request_record
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.mcp import LocalRuntimeAdapterShim, ToolCallRequest
        from synthesis.runtime import runtime_descriptor
        from synthesis.seeds import foundation_seed

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle = build_domain_pipeline_bundle(foundation_seed(), Path(tmpdir))
            adapter = LocalRuntimeAdapterShim(
                descriptor=runtime_descriptor("contacts_fixture"),
                session=bundle.runtime_session(),
            )
            request = ToolCallRequest(
                call_id="call_lookup_redacted",
                adapter_id=adapter.manifest.adapter_id,
                tool_name="lookup_contact_email",
                arguments={
                    "name": "Alice Zhang",
                    "raw_source": {"contacts": []},
                    "source_payload": {"rows": []},
                    "profile_path": "/Users/H/profile.json",
                    "credential": "secret-test-key",
                    "headers": {"authorization": "Bearer secret-test-key"},
                    "provider_prompt": "Generate a task",
                    "generated_code": "print('unsafe')",
                },
            )

            request_record = request.export()
            result = adapter.call_tool(request)

        validate_adapter_call_request_record(request_record)
        self.assertEqual(request_record["arguments"], {"name": "Alice Zhang"})
        self.assertEqual(result.execution_status, "succeeded")
        self.assertEqual(result.observation["email"], "alice.zhang@example.test")
        self.assertEqual(result.runtime_action["schema_version"], "runtime_action_result_v1")
        serialized = str(request_record) + str(result.export())
        self.assertNotIn("/Users/H", serialized)
        self.assertNotIn("secret-test-key", serialized)
        self.assertNotIn("raw_source", serialized)
        self.assertNotIn("source_payload", serialized)
        self.assertNotIn("provider_prompt", serialized)
        self.assertNotIn("generated_code", serialized)

    def test_mobile_runtime_adapter_executes_local_tools(self) -> None:
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.mcp import ToolCallRequest
        from synthesis.runtime import runtime_descriptor
        from tests.test_mobile_pipeline import mobile_seed

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle = build_domain_pipeline_bundle(
                mobile_seed(),
                Path(tmpdir),
                enable_mcp_adapter=True,
            )
            adapter = bundle.adapter_shim
            assert adapter is not None

            manifest = adapter.manifest.export()
            lookup = adapter.call_tool(
                ToolCallRequest(
                    call_id="call_mobile_lookup",
                    adapter_id=manifest["adapter_id"],
                    tool_name="search_phone_messages",
                    arguments={"query": "project update", "participant": "Maya"},
                )
            )
            reminder = adapter.call_tool(
                ToolCallRequest(
                    call_id="call_mobile_reminder",
                    adapter_id=manifest["adapter_id"],
                    tool_name="create_phone_reminder",
                    arguments={
                        "title": "Send the project update",
                        "due_at": "tomorrow 9 AM",
                        "source_message_id": "msg_maya_project_update",
                    },
                )
            )
            draft = adapter.call_tool(
                ToolCallRequest(
                    call_id="call_mobile_draft",
                    adapter_id=manifest["adapter_id"],
                    tool_name="draft_message_reply",
                    arguments={
                        "thread_id": "thread_maya",
                        "body": "I will send the update tomorrow morning.",
                    },
                )
            )

        self.assertTrue(runtime_descriptor("mobile_messages_fixture").supports_local_adapter)
        self.assertEqual(manifest["environment"]["id"], "mobile_messages_fixture")
        self.assertEqual(manifest["adapter_id"], "mobile_messages_local_mcp_adapter")
        self.assertEqual(lookup.execution_status, "succeeded")
        self.assertEqual(lookup.observation["message_id"], "msg_maya_project_update")
        self.assertEqual(reminder.execution_status, "succeeded")
        self.assertEqual(reminder.side_effect_summary["class"], "state_mutating")
        self.assertTrue(reminder.runtime_action["side_effect_summary"]["state_changed"])
        self.assertEqual(draft.execution_status, "succeeded")
        self.assertEqual(draft.side_effect_summary["class"], "state_mutating")

    def test_unsupported_runtime_adapter_capability_is_sanitized_rejection(self) -> None:
        from synthesis.domain_pipeline import build_domain_pipeline_bundle
        from synthesis.mcp import LocalRuntimeAdapterShim, ToolCallRequest
        from synthesis.runtime import RuntimeCapabilityDescriptor
        from synthesis.seeds import DomainSeed, foundation_seed

        descriptor = RuntimeCapabilityDescriptor(
            runtime_id="fake_runtime",
            runtime_version="runtime_fake_v1",
            domain_id="fake_domain",
            supports_rebuild=True,
            supports_checkpoint_restore=True,
            supports_episode_replay=False,
            supports_reward_labels=False,
            supports_local_adapter=False,
            state_changing_tools=(),
            task_taxonomy=("fake_lookup",),
            rebuild_seed=DomainSeed(
                seed_id="seed_fake_runtime",
                domain="fake_runtime",
                description="Fake runtime for adapter rejection tests.",
                task_taxonomy=("fake_lookup",),
            ),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle = build_domain_pipeline_bundle(foundation_seed(), Path(tmpdir))
            adapter = LocalRuntimeAdapterShim(
                descriptor=descriptor,
                session=bundle.runtime_session(),
            )
            result = adapter.call_tool(
                ToolCallRequest(
                    call_id="call_fake",
                    adapter_id=adapter.manifest.adapter_id,
                    tool_name="fake_lookup",
                    arguments={"profile_path": "/Users/H/profile.json"},
                )
            )

        self.assertEqual(result.execution_status, "rejected")
        self.assertEqual(result.error["cause"], "unsupported_runtime_adapter")
        serialized = str(result.export())
        self.assertNotIn("/Users/H", serialized)


if __name__ == "__main__":
    unittest.main()
