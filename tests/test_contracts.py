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

    def test_sample_contract_accepts_run_profile_attribution(self) -> None:
        from synthesis.contracts import validate_sample_record

        sample = _valid_sample()
        sample["lineage"]["run_profile"] = _valid_run_profile_attribution()

        validate_sample_record(sample)

    def test_rejection_contract_accepts_run_profile_attribution(self) -> None:
        from synthesis.contracts import validate_rejection_record

        rejection = _valid_rejection()
        rejection["details"]["run_profile"] = _valid_run_profile_attribution(
            profile_schema_version="run_profile_v2",
            include_source=True,
        )

        validate_rejection_record(rejection)

    def test_run_profile_attribution_rejects_invalid_hashes_and_unknown_keys(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_sample_record

        invalid_records = (
            {"config_hash": "not-a-hash"},
            {"target_candidate_count": 25},
            {"enabled_features": []},
            {"source": {**_valid_run_profile_source_attribution(), "path": "contacts-profile.json"}},
            {"source": {**_valid_run_profile_source_attribution(), "raw_payload": {"contacts": []}}},
        )
        for override in invalid_records:
            with self.subTest(override=override):
                sample = _valid_sample()
                attribution = _valid_run_profile_attribution(include_source=True)
                attribution.update(override)
                sample["lineage"]["run_profile"] = attribution

                with self.assertRaisesRegex(ContractValidationError, "run_profile"):
                    validate_sample_record(sample)

    def test_run_profile_attribution_requires_core_fields(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_rejection_record

        for field in (
            "schema_version",
            "profile_schema_version",
            "profile_id",
            "generation_mode",
            "config_hash",
        ):
            with self.subTest(field=field):
                rejection = _valid_rejection()
                attribution = _valid_run_profile_attribution()
                attribution.pop(field)
                rejection["details"]["run_profile"] = attribution

                with self.assertRaisesRegex(ContractValidationError, "run_profile"):
                    validate_rejection_record(rejection)

    def test_run_profile_attribution_rejects_unsupported_profile_purpose(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_sample_record

        sample = _valid_sample()
        sample["lineage"]["run_profile"] = {
            **_valid_run_profile_attribution(),
            "profile_purpose": "demo",
        }

        with self.assertRaisesRegex(ContractValidationError, "profile_purpose"):
            validate_sample_record(sample)

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

    def test_manifest_contract_accepts_sanitized_run_profile_metadata(self) -> None:
        from synthesis.contracts import validate_manifest_record

        manifest = _valid_manifest()
        manifest["run_profile"] = {
            "schema_version": "run_profile_v1",
            "profile_id": "foundation_scale_probe_25",
            "generation_mode": "deterministic_scale_probe",
            "profile_purpose": "diagnostic_probe",
            "target_candidate_count": 25,
            "config_hash": "sha256:" + "1" * 64,
            "enabled_features": ["enable_mcp_adapter"],
        }

        validate_manifest_record(manifest)

    def test_manifest_contract_rejects_unsupported_profile_purpose(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_manifest_record

        manifest = _valid_manifest()
        manifest["run_profile"] = {
            "schema_version": "run_profile_v1",
            "profile_id": "foundation_scale_probe_25",
            "generation_mode": "deterministic_scale_probe",
            "profile_purpose": "demo",
            "target_candidate_count": 25,
            "config_hash": "sha256:" + "1" * 64,
            "enabled_features": [],
        }

        with self.assertRaisesRegex(ContractValidationError, "profile_purpose"):
            validate_manifest_record(manifest)

    def test_manifest_contract_accepts_v2_profile_source_summary(self) -> None:
        from synthesis.contracts import validate_manifest_record

        manifest = _valid_manifest()
        manifest["run_profile"] = {
            "schema_version": "run_profile_v2",
            "profile_id": "foundation_profile_local_contacts",
            "generation_mode": "foundation_fixture",
            "target_candidate_count": None,
            "config_hash": "sha256:" + "1" * 64,
            "enabled_features": [],
            "source": {
                "kind": "local_contacts_json",
                "source_id": "source_profile_contacts_v1",
                "content_hash": "sha256:" + "2" * 64,
                "license_label": "cc-by-4.0",
                "source_policy_hash": "sha256:" + "3" * 64,
            },
        }

        validate_manifest_record(manifest)

    def test_manifest_contract_rejects_raw_profile_source_metadata(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_manifest_record

        forbidden_pairs = (
            ("path", "contacts-profile.json"),
            ("raw_payload", {"contacts": [{"name": "Alice Zhang"}]}),
            ("authorization", "Bearer secret-test-key"),
            ("api_key", "secret-test-key"),
            ("contact_name", "Alice Zhang"),
        )
        for key, value in forbidden_pairs:
            with self.subTest(key=key):
                manifest = _valid_manifest()
                source = {
                    "kind": "local_contacts_json",
                    "source_id": "source_profile_contacts_v1",
                    "content_hash": "sha256:" + "2" * 64,
                    "license_label": "cc-by-4.0",
                    "source_policy_hash": "sha256:" + "3" * 64,
                    key: value,
                }
                manifest["run_profile"] = {
                    "schema_version": "run_profile_v2",
                    "profile_id": "foundation_profile_local_contacts",
                    "generation_mode": "foundation_fixture",
                    "target_candidate_count": None,
                    "config_hash": "sha256:" + "1" * 64,
                    "enabled_features": [],
                    "source": source,
                }

                with self.assertRaisesRegex(ContractValidationError, "run_profile"):
                    validate_manifest_record(manifest)

    def test_manifest_contract_rejects_raw_secret_like_run_profile_metadata(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_manifest_record

        manifest = _valid_manifest()
        manifest["run_profile"] = {
            "schema_version": "run_profile_v1",
            "profile_id": "foundation_scale_probe_25",
            "generation_mode": "deterministic_scale_probe",
            "target_candidate_count": 25,
            "config_hash": "sha256:" + "1" * 64,
            "enabled_features": [],
            "AGENT_DATA_API_KEY": "secret-test-key",
        }

        with self.assertRaisesRegex(ContractValidationError, "run_profile"):
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

    def test_evaluation_report_contract_accepts_minimal_valid_record(self) -> None:
        from synthesis.contracts import validate_evaluation_report_record

        validate_evaluation_report_record(_valid_evaluation_report())

    def test_evaluation_report_contract_rejects_malformed_schema_version(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_evaluation_report_record

        report = _valid_evaluation_report()
        report["schema_version"] = "evaluation_report_v2"

        with self.assertRaisesRegex(ContractValidationError, "schema_version"):
            validate_evaluation_report_record(report)

    def test_evaluation_report_contract_rejects_invalid_counts_and_rates(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_evaluation_report_record

        invalid_reports = (
            {"counts": {"total": 2, "passed": 2, "failed": 1}},
            {"rates": {"pass_rate": 1.5}},
        )
        for override in invalid_reports:
            with self.subTest(override=override):
                report = _valid_evaluation_report()
                for key, value in override.items():
                    report[key].update(value)

                with self.assertRaisesRegex(ContractValidationError, "counts|pass_rate"):
                    validate_evaluation_report_record(report)

    def test_evaluation_report_contract_rejects_invalid_task_result_status(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_evaluation_report_record

        report = _valid_evaluation_report()
        report["task_results"][0]["status"] = "skipped"

        with self.assertRaisesRegex(ContractValidationError, "status"):
            validate_evaluation_report_record(report)

    def test_evaluation_report_contract_rejects_malformed_capability_threshold(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_evaluation_report_record

        report = _valid_evaluation_report()
        report["thresholds"]["min_capability_pass_rates"] = {"missing_contact": "high"}

        with self.assertRaisesRegex(ContractValidationError, "min_capability_pass_rates"):
            validate_evaluation_report_record(report)

    def test_profile_decision_report_contract_accepts_valid_record(self) -> None:
        from synthesis.contracts import validate_profile_decision_report_record

        validate_profile_decision_report_record(_valid_profile_decision_report())

    def test_profile_decision_report_contract_requires_profile_promotion(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_profile_decision_report_record

        report = _valid_profile_decision_report()
        report["decisions"].pop("profile_promotion")

        with self.assertRaisesRegex(ContractValidationError, "profile_promotion"):
            validate_profile_decision_report_record(report)

    def test_profile_decision_report_contract_rejects_unsupported_promotion_status(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_profile_decision_report_record

        report = _valid_profile_decision_report()
        report["decisions"]["profile_promotion"]["status"] = "maybe"

        with self.assertRaisesRegex(ContractValidationError, "profile_promotion.status"):
            validate_profile_decision_report_record(report)

    def test_dataset_release_report_contract_accepts_release_decision(self) -> None:
        from synthesis.contracts import validate_dataset_release_report_record

        validate_dataset_release_report_record(_valid_dataset_release_report())

    def test_dataset_release_report_contract_rejects_unsupported_status(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_dataset_release_report_record

        report = _valid_dataset_release_report()
        report["decisions"]["dataset_release"]["status"] = "maybe"

        with self.assertRaisesRegex(ContractValidationError, "dataset_release.status"):
            validate_dataset_release_report_record(report)

    def test_dataset_release_report_contract_requires_input_artifact_names(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_dataset_release_report_record

        report = _valid_dataset_release_report()
        report["inputs"].pop("evaluation_report_path")

        with self.assertRaisesRegex(ContractValidationError, "evaluation_report_path"):
            validate_dataset_release_report_record(report)

    def test_dataset_release_report_contract_rejects_raw_secret_like_keys(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_dataset_release_report_record

        report = _valid_dataset_release_report()
        report["profile"]["api_key"] = "secret-test-key"

        with self.assertRaisesRegex(ContractValidationError, "raw secret"):
            validate_dataset_release_report_record(report)

    def test_dataset_release_report_contract_rejects_passed_diagnostic_profile(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_dataset_release_report_record

        report = _valid_dataset_release_report()
        report["profile"]["profile_purpose"] = "diagnostic_probe"

        with self.assertRaisesRegex(ContractValidationError, "profile_purpose"):
            validate_dataset_release_report_record(report)

    def test_dataset_release_report_contract_rejects_malformed_release_completeness(self) -> None:
        from synthesis.contracts import ContractValidationError, validate_dataset_release_report_record

        malformed_reports = (
            ("min_accepted_samples", {"thresholds": {"min_accepted_samples": 0}}),
            ("release_completeness.decision.status", {"decision": {"status": "maybe"}}),
            ("required_task_types", {"thresholds": {"required_task_types": "contact_followup"}}),
            ("observed.task_types", {"observed": {"task_types": "contact_followup"}}),
            (
                "observed.tool_combinations",
                {"observed": {"tool_combinations": "lookup_contact_email"}},
            ),
        )
        for expected_error, override in malformed_reports:
            with self.subTest(expected_error=expected_error):
                report = _valid_dataset_release_report()
                _deep_update(report["release_completeness"], override)

                with self.assertRaisesRegex(ContractValidationError, expected_error):
                    validate_dataset_release_report_record(report)

    def test_manifest_contract_accepts_evaluation_report_artifact(self) -> None:
        from synthesis.contracts import validate_manifest_record

        manifest = _valid_manifest()
        manifest["artifacts"]["evaluation_report"] = "evaluation_report.json"

        validate_manifest_record(manifest)

    def test_manifest_contract_accepts_dataset_release_report_artifact(self) -> None:
        from synthesis.contracts import validate_manifest_record

        manifest = _valid_manifest()
        manifest["artifacts"]["dataset_release_report"] = "dataset_release_report.json"

        validate_manifest_record(manifest)

    def test_manifest_contract_accepts_release_quality_artifacts(self) -> None:
        from synthesis.contracts import validate_manifest_record

        manifest = _valid_manifest()
        manifest["artifacts"]["release_quality_audit"] = "release_quality_audit.json"
        manifest["artifacts"]["dataset_release_card"] = "dataset_release_card.md"

        validate_manifest_record(manifest)


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


def _valid_rejection() -> dict[str, object]:
    return {
        "candidate_id": "candidate_contacts_ben_bad_expectation",
        "cause": "verification_failed",
        "task": {
            "candidate_id": "candidate_contacts_ben_bad_expectation",
            "instruction": "Find Ben Carter's email address.",
            "constraints": {"must_use_tool": "lookup_contact_email"},
            "difficulty": {"level": "easy", "tool_count": 1},
        },
        "details": {
            "check": "final_response_contains_expected_answer",
            "retry_eligible": False,
        },
    }


def _valid_run_profile_attribution(
    *,
    profile_schema_version: str = "run_profile_v1",
    include_source: bool = False,
) -> dict[str, object]:
    attribution: dict[str, object] = {
        "schema_version": "run_profile_attribution_v1",
        "profile_schema_version": profile_schema_version,
        "profile_id": "foundation_fixture_profile",
        "generation_mode": "foundation_fixture",
        "config_hash": "sha256:" + "1" * 64,
    }
    if include_source:
        attribution["source"] = _valid_run_profile_source_attribution()
    return attribution


def _valid_run_profile_source_attribution() -> dict[str, object]:
    return {
        "kind": "local_contacts_json",
        "source_id": "source_profile_contacts_v1",
        "content_hash": "sha256:" + "2" * 64,
        "license_label": "cc-by-4.0",
        "source_policy_hash": "sha256:" + "3" * 64,
    }


def _valid_manifest() -> dict[str, object]:
    return {
        "schema_version": "dataset_manifest_v1",
        "dataset_version": "dataset_test",
        "parent_dataset_version": None,
        "accepted_count": 1,
        "rejected_count": 0,
        "artifacts": {
            "samples": "samples.jsonl",
            "rejections": "rejections.jsonl",
            "quality_report": "quality_report.json",
        },
        "quality": {"success_rate": 1.0, "executable_rate": 1.0},
        "environment_versions": ["env_contacts_v2"],
        "tool_versions": ["tool_lookup_contact_email_v1"],
        "verifier_versions": ["verifier_exact_answer_state_v2"],
        "generator_config_hashes": ["scripted_task_generation_v1"],
        "rejection_causes": {},
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


def _valid_evaluation_report() -> dict[str, object]:
    return {
        "schema_version": "evaluation_report_v1",
        "dataset_version": "dataset_test",
        "suite": {
            "suite_id": "contacts_heldout_v1",
            "suite_version": "contacts_heldout_v1",
            "task_count": 1,
        },
        "profile": None,
        "inputs": {
            "manifest_path": "manifest.json",
            "quality_report_path": "quality_report.json",
            "parent_evaluation_report_path": None,
        },
        "counts": {
            "total": 1,
            "passed": 1,
            "failed": 0,
            "regressed": 0,
            "improved": 0,
            "unchanged": 1,
        },
        "rates": {"pass_rate": 1.0},
        "capability_slices": {
            "contact_lookup": {
                "total": 1,
                "passed": 1,
                "failed": 0,
                "pass_rate": 1.0,
            }
        },
        "task_results": [
            {
                "task_id": "heldout_contacts_lookup_alice",
                "capability_tags": ["contact_lookup"],
                "status": "passed",
                "failure_cause": None,
                "expected_outcome": "passed",
                "observed_failure_cause": None,
            }
        ],
        "thresholds": {
            "mvp_min_heldout_pass_rate": 0.8,
            "max_regression_count": 0,
            "min_capability_pass_rates": {"contact_lookup": 1.0},
        },
        "decision": {
            "status": "passed",
            "reasons": [
                "pass_rate 1.0 is at or above mvp_min_heldout_pass_rate 0.8",
                "regressed 0 is at or below max_regression_count 0",
            ],
            "triggered_by": ["pass_rate", "regressed"],
        },
    }


def _valid_profile_decision_report() -> dict[str, object]:
    return {
        "schema_version": "profile_decision_report_v1",
        "dataset_version": "dataset_test",
        "profile": None,
        "inputs": {
            "manifest_path": "manifest.json",
            "quality_report_path": "quality_report.json",
            "parent_comparison_path": None,
            "evaluation_report_path": "evaluation_report.json",
        },
        "observed": {
            "total_candidates": 25,
            "accepted": 14,
            "rejected": 11,
            "success_rate": 0.56,
            "executable_rate": 1.0,
            "exact_duplicate_count": 3,
            "exact_duplicate_rate": 0.12,
            "infrastructure_rejection_count": 0,
            "infrastructure_rejection_rate": 0.0,
            "source_policy_rejection_count": 0,
            "source_policy_rejection_rate": 0.0,
            "runtime_seconds": 0.03,
            "profile_slice_count": 3,
        },
        "thresholds": {
            "async_candidate_count": 100,
            "async_runtime_seconds": 600.0,
            "semantic_duplicate_min_candidates": 100,
            "semantic_duplicate_exact_rate": 0.1,
            "mvp_min_success_rate": 0.5,
            "mvp_min_executable_rate": 0.8,
            "mvp_max_infrastructure_rejection_rate": 0.0,
            "mvp_max_source_policy_rejection_rate": 0.0,
        },
        "evaluation": {
            "decision_status": "passed",
            "heldout_pass_rate": 1.0,
            "regression_count": 0,
        },
        "decisions": {
            "async_orchestration": {
                "status": "defer",
                "reasons": ["total_candidates 25 is below async_candidate_count 100"],
                "triggered_by": [],
            },
            "semantic_duplicate_detection": {
                "status": "defer",
                "reasons": [
                    "total_candidates 25 is below semantic_duplicate_min_candidates 100"
                ],
                "triggered_by": [],
            },
            "mvp_quality_floor": {
                "status": "passed",
                "reasons": ["held-out evaluation decision passed"],
                "triggered_by": ["heldout_evaluation"],
            },
            "profile_promotion": {
                "status": "passed",
                "reasons": [
                    "mvp_quality_floor passed",
                    "held-out evaluation passed",
                    "async_orchestration remains deferred by scale thresholds",
                    "semantic_duplicate_detection remains deferred by volume threshold",
                ],
                "triggered_by": [
                    "mvp_quality_floor",
                    "heldout_evaluation",
                    "scale_deferral",
                ],
            },
        },
    }


def _valid_dataset_release_report() -> dict[str, object]:
    return {
        "schema_version": "dataset_release_report_v1",
        "dataset_version": "dataset_release",
        "profile": {
            "schema_version": "run_profile_v1",
            "profile_id": "release_profile",
            "generation_mode": "foundation_fixture",
            "profile_purpose": "release_candidate",
            "config_hash": "sha256:" + "a" * 64,
        },
        "inputs": {
            "manifest_path": "manifest.json",
            "quality_report_path": "quality_report.json",
            "evaluation_report_path": "evaluation_report.json",
            "profile_decision_report_path": "profile_decision_report.json",
        },
        "observed": {
            "accepted": 3,
            "rejected": 0,
            "success_rate": 1.0,
            "executable_rate": 1.0,
            "source_policy_rejection_rate": 0.0,
            "heldout_status": "passed",
            "profile_promotion_status": "passed",
            "async_orchestration_status": "defer",
            "semantic_duplicate_detection_status": "defer",
        },
        "release_completeness": {
            "thresholds": {
                "min_accepted_samples": 5,
                "max_rejection_rate": 0.2,
                "required_task_types": [
                    "lookup_contact_email",
                    "contact_followup",
                    "contact_branch_fallback",
                ],
                "required_tool_combinations": [
                    "lookup_contact_email",
                    "lookup_contact_email+record_contact_followup",
                ],
            },
            "observed": {
                "accepted": 6,
                "rejected": 1,
                "rejection_rate": 0.1428571429,
                "task_types": [
                    "contact_branch_fallback",
                    "contact_followup",
                    "lookup_contact_email",
                ],
                "tool_combinations": [
                    "lookup_contact_email",
                    "lookup_contact_email+record_contact_followup",
                ],
            },
            "decision": {
                "status": "passed",
                "reasons": [
                    "accepted 6 is at or above min_accepted_samples 5",
                    "rejection_rate 0.1428571429 is at or below max_rejection_rate 0.2",
                    "required task types are covered",
                    "required tool combinations are covered",
                ],
                "triggered_by": [
                    "accepted",
                    "rejection_rate",
                    "task_type_coverage",
                    "tool_combination_coverage",
                ],
            },
        },
        "decisions": {
            "dataset_release": {
                "status": "passed",
                "reasons": ["release admission passed"],
                "triggered_by": ["profile_promotion", "heldout_evaluation"],
            }
        },
        "release_artifacts": {
            "samples": "samples.jsonl",
            "rejections": "rejections.jsonl",
            "quality_report": "quality_report.json",
            "evaluation_report": "evaluation_report.json",
            "profile_decision_report": "profile_decision_report.json",
        },
    }


def _deep_update(target: dict[str, object], override: dict[str, object]) -> None:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)  # type: ignore[arg-type]
        else:
            target[key] = value


if __name__ == "__main__":
    unittest.main()
