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


if __name__ == "__main__":
    unittest.main()
