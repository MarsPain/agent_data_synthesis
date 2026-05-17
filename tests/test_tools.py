from __future__ import annotations

import unittest


class ToolExpansionContractsTest(unittest.TestCase):
    def test_capability_gap_export_has_stable_contract_shape(self) -> None:
        from synthesis.contracts import validate_capability_gap_record
        from synthesis.tools import CapabilityGap

        gap = CapabilityGap(
            candidate_id="candidate_needs_contacts",
            policy_id="policy_needs_contacts",
            gap_type="unknown_tool",
            tool_name="list_contact_names",
            cause="tool_missing",
            message="Unknown tool: list_contact_names",
            schema_details={"available_tools": ["lookup_contact_email"]},
            retry_eligible=True,
            source_role_lineage={
                "solution_policy": {
                    "role": "solution_policy",
                    "provider_host": "llm.example.test",
                    "model": "test-generator",
                    "config_hash": "policy-hash",
                }
            },
        )

        record = gap.export()

        self.assertEqual(record["schema_version"], "capability_gap_v1")
        self.assertEqual(record["gap_type"], "unknown_tool")
        self.assertEqual(record["tool_name"], "list_contact_names")
        self.assertEqual(record["source_role_lineage"]["solution_policy"]["role"], "solution_policy")
        validate_capability_gap_record(record)

    def test_tool_proposal_parser_rejects_executable_code_payloads(self) -> None:
        from synthesis.llm import LLMProviderError
        from synthesis.tools import parse_tool_proposal

        with self.assertRaises(LLMProviderError) as context:
            parse_tool_proposal(
                {
                    "proposal": {
                        "tool_name": "list_contact_names",
                        "description": "List known contact names.",
                        "schema": {"type": "object", "additionalProperties": False},
                        "side_effects": "read_only",
                        "required_environment": {"tables": ["contacts"]},
                        "verifier_implications": ["final answer should mention a known contact"],
                        "safety_notes": ["read-only contacts lookup"],
                        "python_code": "def handler(args): return {}",
                    }
                },
                lineage={"role": "tool_generation", "provider_host": "llm.example.test"},
            )
        self.assertEqual(context.exception.cause, "llm_response_schema_error")

    def test_matching_tool_proposal_can_admit_curated_contact_tool(self) -> None:
        from pathlib import Path
        import tempfile

        from synthesis.environments import ContactEnvironment
        from synthesis.tools import (
            ToolProposal,
            ToolRegistry,
            admit_curated_tool,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            environment = ContactEnvironment.create_fixture(Path(tmpdir))
            registry = ToolRegistry()
            proposal = ToolProposal(
                tool_name="list_contact_names",
                description="List known contact names.",
                schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
                side_effects="read_only",
                required_environment={"environment_id": "contacts_fixture", "tables": ["contacts"]},
                verifier_implications=["final response can cite returned contact names"],
                safety_notes=["read-only curated contacts fixture tool"],
                lineage={
                    "role": "tool_generation",
                    "role_version": "role_tool_generation_v1",
                    "output_type": "tool_proposal",
                    "provider_host": "llm.example.test",
                    "model": "test-generator",
                    "config_hash": "proposal-hash",
                },
            )

            admission = admit_curated_tool(proposal, registry, environment)

            self.assertTrue(admission.accepted)
            self.assertEqual(admission.tool_name, "list_contact_names")
            self.assertEqual(registry.execute("list_contact_names", {}), {"contacts": "Alice Zhang, Ben Carter"})


if __name__ == "__main__":
    unittest.main()
