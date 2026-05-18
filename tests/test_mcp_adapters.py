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


if __name__ == "__main__":
    unittest.main()
