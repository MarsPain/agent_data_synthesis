from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class DatasetContractTest(unittest.TestCase):
    def test_sample_contract_requires_lineage_seed_ids(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_sample_record

        sample = _valid_sample()
        sample["lineage"].pop("seed_ids")

        with self.assertRaisesRegex(ContractValidationError, "lineage.seed_ids"):
            validate_sample_record(sample)

    def test_sample_contract_requires_trajectory_event_type(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_sample_record

        sample = _valid_sample()
        sample["trajectory"][0].pop("type")

        with self.assertRaisesRegex(ContractValidationError, "trajectory.0.type"):
            validate_sample_record(sample)

    def test_sample_contract_accepts_state_change_events_and_policy_lineage(self) -> None:
        from synthesis.contracts import validate_sample_record

        sample = _valid_sample()
        sample["trajectory"].insert(
            1,
            {
                "type": "state_change",
                "tool": "record_contact_followup",
                "change": {
                    "entity": "contact_followup",
                    "operation": "inserted",
                    "name": "Alice Zhang",
                },
            },
        )
        sample["lineage"]["solution_policy"] = {
            "role": "scripted_solution_policy",
            "provider_host": "local",
            "model": "scripted",
            "config_hash": "policy123",
            "configured": True,
        }

        validate_sample_record(sample)

    def test_rejection_contract_requires_cause(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_rejection_record

        rejection = {
            "candidate_id": "candidate_bad",
            "task": {
                "candidate_id": "candidate_bad",
                "instruction": "Find Alice Zhang's email address.",
                "constraints": {},
                "difficulty": {},
            },
            "details": {},
        }

        with self.assertRaisesRegex(ContractValidationError, "cause"):
            validate_rejection_record(rejection)

    def test_manifest_contract_requires_version_comparison_fields(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_manifest_record

        manifest = {
            "dataset_version": "dataset_test",
            "accepted_count": 1,
            "rejected_count": 0,
            "artifacts": {"samples": "samples.jsonl", "rejections": "rejections.jsonl"},
            "quality": {"success_rate": 1.0, "executable_rate": 1.0},
        }

        with self.assertRaisesRegex(ContractValidationError, "schema_version"):
            validate_manifest_record(manifest)

    def test_dataset_writer_rejects_malformed_sample_before_writing(self) -> None:
        from synthesis.contracts import ContractValidationError
        from synthesis.datasets import write_dataset_artifacts

        sample = _valid_sample()
        sample["lineage"]["generator"].pop("model")

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(ContractValidationError, "lineage.generator.model"):
                write_dataset_artifacts(
                    output_dir=Path(tmpdir),
                    dataset_version="dataset_test",
                    samples=[sample],
                    rejections=[],
                )

    def test_tool_proposal_contract_requires_safety_notes(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_tool_proposal_record

        proposal = _valid_tool_proposal()
        proposal.pop("safety_notes")

        with self.assertRaisesRegex(ContractValidationError, "safety_notes"):
            validate_tool_proposal_record(proposal)

    def test_capability_gap_contract_rejects_unknown_gap_type(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_capability_gap_record

        gap = _valid_capability_gap()
        gap["gap_type"] = "mystery"

        with self.assertRaisesRegex(ContractValidationError, "gap_type"):
            validate_capability_gap_record(gap)

    def test_branch_plan_contract_rejects_duplicate_branch_ids(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_branch_plan_record

        plan = _valid_branch_plan()
        plan["branches"].append(dict(plan["branches"][0]))

        with self.assertRaisesRegex(ContractValidationError, "duplicate branch_id"):
            validate_branch_plan_record(plan)

    def test_branch_plan_max_depth_allows_multiple_sibling_branches(self) -> None:
        from synthesis.contracts import validate_branch_plan_record

        plan = _valid_branch_plan()
        plan["max_depth"] = 1
        plan["branches"][1]["parent_id"] = None

        validate_branch_plan_record(plan)

    def test_branch_plan_max_depth_rejects_deep_parent_chain(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_branch_plan_record

        plan = _valid_branch_plan()
        plan["max_depth"] = 1

        with self.assertRaisesRegex(ContractValidationError, "branch depth exceeds max_depth"):
            validate_branch_plan_record(plan)

    def test_branch_outcome_contract_requires_selected_terminal_success(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_branch_outcomes

        outcomes = [
            {
                "schema_version": "branch_outcome_v1",
                "branch_id": "direct_short_name",
                "attempted": True,
                "selected": False,
                "outcome": "rejected",
                "failure_cause": "tool_runtime_error",
                "retry_eligible": True,
                "refinement_eligible": False,
                "message": "Unknown contact: Alice",
                "depth": 1,
                "trajectory": [],
            }
        ]

        with self.assertRaisesRegex(ContractValidationError, "selected terminal branch"):
            validate_branch_outcomes(outcomes)

    def test_seed_transformation_contract_requires_capability_target(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_seed_transformation_record

        transformation = _valid_seed_transformation()
        transformation.pop("capability_target")

        with self.assertRaisesRegex(ContractValidationError, "capability_target"):
            validate_seed_transformation_record(transformation)

    def test_task_suggestion_contract_rejects_unsupported_taxonomy_node(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_task_suggestion_record

        suggestion = _valid_task_suggestion()
        suggestion["target_taxonomy_node"] = "network_research"

        with self.assertRaisesRegex(ContractValidationError, "target_taxonomy_node"):
            validate_task_suggestion_record(suggestion)

    def test_edited_task_contract_requires_candidate_or_rejection(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_edited_task_record

        edited = _valid_edited_task()
        edited.pop("candidate")

        with self.assertRaisesRegex(ContractValidationError, "candidate or rejection"):
            validate_edited_task_record(edited)

    def test_adapter_manifest_contract_requires_source_policy_hash(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_adapter_manifest_record

        manifest = _valid_adapter_manifest()
        manifest.pop("source_policy_hash")

        with self.assertRaisesRegex(ContractValidationError, "source_policy_hash"):
            validate_adapter_manifest_record(manifest)

    def test_adapter_call_request_contract_rejects_unsupported_operation(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_adapter_call_request_record

        request = _valid_adapter_call_request()
        request["operation"] = "resources/read"

        with self.assertRaisesRegex(ContractValidationError, "operation"):
            validate_adapter_call_request_record(request)

    def test_adapter_call_result_contract_requires_error_for_rejection(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_adapter_call_result_record

        result = _valid_adapter_call_result()
        result["execution_status"] = "rejected"
        result["error"] = None

        with self.assertRaisesRegex(ContractValidationError, "error"):
            validate_adapter_call_result_record(result)

    def test_sample_contract_accepts_adapter_lineage(self) -> None:
        from synthesis.contracts import validate_sample_record

        sample = _valid_sample()
        sample["lineage"]["adapter"] = [_valid_adapter_lineage()]

        validate_sample_record(sample)


def _valid_sample() -> dict[str, object]:
    return {
        "sample_id": "sample_candidate_contacts_alice",
        "dataset_version": "dataset_test",
        "environment": {
            "id": "contacts_fixture",
            "version": "env_contacts_v1",
            "reset_recipe": {"type": "sqlite_fixture"},
        },
        "tools": [
            {
                "name": "lookup_contact_email",
                "version": "tool_lookup_contact_email_v1",
                "schema": {"type": "object"},
                "side_effects": "read_only",
            }
        ],
        "task": {
            "instruction": "Find Alice Zhang's email address.",
            "constraints": {"must_use_tool": "lookup_contact_email"},
            "difficulty": {"level": "easy", "tool_count": 1},
        },
        "trajectory": [
            {
                "type": "action",
                "tool": "lookup_contact_email",
                "arguments": {"name": "Alice Zhang"},
            },
            {
                "type": "final_response",
                "content": "Alice Zhang's email is alice.zhang@example.test.",
            },
        ],
        "final_response": "Alice Zhang's email is alice.zhang@example.test.",
        "verifier": {
            "id": "exact_answer_verifier",
            "version": "verifier_exact_answer_v1",
            "checks": ["final_response_contains_expected_answer"],
        },
        "verification": {
            "verifier_id": "exact_answer_verifier",
            "version": "verifier_exact_answer_v1",
            "passed": True,
            "checks": [
                {
                    "name": "final_response_contains_expected_answer",
                    "passed": True,
                    "expected": "alice.zhang@example.test",
                    "actual": "Alice Zhang's email is alice.zhang@example.test.",
                }
            ],
        },
        "quality": {
            "scores": {"executable": 1.0, "verified": 1.0},
            "tags": ["foundation"],
            "review_status": "auto_accepted",
        },
        "lineage": {
            "seed_ids": ["seed_contacts_v1"],
            "generator": {
                "role": "task_generation",
                "provider_host": "unconfigured",
                "model": "unconfigured",
                "config_hash": "abc123",
                "configured": False,
            },
            "verifier": {
                "id": "exact_answer_verifier",
                "version": "verifier_exact_answer_v1",
            },
        },
    }


def _valid_capability_gap() -> dict[str, object]:
    return {
        "schema_version": "capability_gap_v1",
        "candidate_id": "candidate_needs_contacts",
        "policy_id": "policy_needs_contacts",
        "gap_type": "unknown_tool",
        "tool_name": "list_contact_names",
        "cause": "tool_missing",
        "message": "Unknown tool: list_contact_names",
        "schema_details": {"available_tools": ["lookup_contact_email"]},
        "retry_eligible": True,
        "source_role_lineage": {},
    }


def _valid_tool_proposal() -> dict[str, object]:
    return {
        "schema_version": "tool_proposal_v1",
        "tool_name": "list_contact_names",
        "description": "List known contact names.",
        "schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        "side_effects": "read_only",
        "required_environment": {"environment_id": "contacts_fixture", "tables": ["contacts"]},
        "verifier_implications": ["final response can cite returned contact names"],
        "safety_notes": ["read-only curated contacts fixture tool"],
        "lineage": {
            "role": "tool_generation",
            "provider_host": "llm.example.test",
            "model": "test-generator",
            "config_hash": "proposal-hash",
        },
    }


def _valid_branch_plan() -> dict[str, object]:
    return {
        "schema_version": "branch_plan_v1",
        "plan_id": "branch_plan_candidate_contacts_alice_fallback",
        "max_depth": 2,
        "branches": [
            {
                "branch_id": "direct_short_name",
                "node_type": "attempt",
                "parent_id": None,
                "condition": "Try the abbreviated name first.",
                "steps": [
                    {
                        "tool_name": "lookup_contact_email",
                        "arguments": {"name": "Alice"},
                    }
                ],
                "final_response_template": "{name}'s email is {email}.",
                        "terminal_outcome": "fallback_on_failure",
                    },
            {
                "branch_id": "fallback_full_name",
                "node_type": "fallback",
                "parent_id": "direct_short_name",
                "condition": "Use the full name when the abbreviated lookup fails.",
                "steps": [
                    {
                        "tool_name": "lookup_contact_email",
                        "arguments": {"name": "Alice Zhang"},
                    }
                ],
                "final_response_template": "{name}'s email is {email}.",
                        "terminal_outcome": "accept_on_success",
                    },
        ],
    }


def _valid_seed_transformation() -> dict[str, object]:
    return {
        "schema_version": "seed_transformation_v1",
        "transformation_id": "transform_seed_contacts_followup",
        "source_seed_id": "seed_contacts_v1",
        "transformation_type": "taxonomy_expansion",
        "target_taxonomy_node": "contact_followup",
        "capability_target": "stateful_contact_followup",
        "difficulty_movement": "easy_to_medium",
        "lineage": {
            "role": "scripted_seed_transformation",
            "provider_host": "local",
            "model": "scripted",
            "config_hash": "seed-transform-local-v1",
        },
    }


def _valid_task_suggestion() -> dict[str, object]:
    return {
        "schema_version": "task_suggestion_v1",
        "suggestion_id": "suggestion_contact_followup_ben",
        "transformation_id": "transform_seed_contacts_followup",
        "target_taxonomy_node": "contact_followup",
        "intent": "Find Ben Carter's email and record a follow-up.",
        "required_capabilities": ["lookup_contact_email", "record_contact_followup"],
        "target_tools": ["lookup_contact_email", "record_contact_followup"],
        "constraints": {"task_type": "contact_followup"},
        "expected_verification": "exact_answer_and_state_change",
        "outcome": "accepted",
        "lineage": {
            "role": "task_suggester",
            "provider_host": "local",
            "model": "scripted",
            "config_hash": "suggestion-local-v1",
        },
    }


def _valid_edited_task() -> dict[str, object]:
    return {
        "schema_version": "edited_task_v1",
        "suggestion_id": "suggestion_contact_followup_ben",
        "editor_action": "created_candidate",
        "candidate": {
            "candidate_id": "candidate_expanded_ben_followup",
            "instruction": "Find Ben Carter's email and record a follow-up note.",
            "constraints": {
                "task_type": "contact_followup",
                "required_tools": ["lookup_contact_email", "record_contact_followup"],
            },
            "difficulty": {
                "level": "medium",
                "tool_count": 2,
                "constraint_count": 2,
                "state_changes": 1,
                "ambiguity": "none",
                "recovery_paths": 0,
            },
            "tool_name": "lookup_contact_email",
            "arguments": {"name": "Ben Carter"},
            "expected_answer": "ben.carter@example.test",
        },
        "lineage": {
            "role": "task_editor",
            "provider_host": "local",
            "model": "scripted",
            "config_hash": "editor-local-v1",
        },
    }


def _valid_adapter_manifest() -> dict[str, object]:
    return {
        "schema_version": "mcp_adapter_manifest_v1",
        "adapter_id": "contacts_local_mcp_adapter",
        "protocol_label": "mcp-compatible-local-shim",
        "adapter_version": "adapter_contacts_local_v1",
        "environment": {
            "id": "contacts_fixture",
            "version": "env_contacts_v2",
            "reset_recipe": {"type": "sqlite_fixture"},
        },
        "source_policy_hash": "sha256:" + "1" * 64,
        "supported_operations": ["tool.call"],
        "capabilities": {"reset": True, "checkpoint": True},
        "tools": [
            {
                "name": "lookup_contact_email",
                "version": "tool_lookup_contact_email_v1",
                "schema": {"type": "object"},
                "side_effects": "read_only",
                "verifier_implications": ["observation must support exact-answer checks"],
            }
        ],
        "side_effect_classes": ["read_only"],
        "verifier_implications": ["adapter observations preserve local trajectory semantics"],
    }


def _valid_adapter_call_request() -> dict[str, object]:
    return {
        "schema_version": "mcp_tool_call_request_v1",
        "call_id": "call_lookup_alice",
        "adapter_id": "contacts_local_mcp_adapter",
        "operation": "tool.call",
        "tool_name": "lookup_contact_email",
        "arguments": {"name": "Alice Zhang"},
    }


def _valid_adapter_call_result() -> dict[str, object]:
    return {
        "schema_version": "mcp_tool_call_result_v1",
        "call_id": "call_lookup_alice",
        "adapter_id": "contacts_local_mcp_adapter",
        "tool_name": "lookup_contact_email",
        "execution_status": "succeeded",
        "observation": {"name": "Alice Zhang", "email": "alice.zhang@example.test"},
        "side_effect_summary": {"class": "read_only"},
        "error": None,
    }


def _valid_adapter_lineage() -> dict[str, object]:
    return {
        "schema_version": "adapter_lineage_v1",
        "adapter_id": "contacts_local_mcp_adapter",
        "protocol_label": "mcp-compatible-local-shim",
        "adapter_version": "adapter_contacts_local_v1",
        "operation": "tool.call",
        "tool_name": "lookup_contact_email",
        "call_id": "call_lookup_alice",
        "execution_status": "succeeded",
        "rejection_cause": None,
    }


if __name__ == "__main__":
    unittest.main()
