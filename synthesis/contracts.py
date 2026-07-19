from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
import hashlib
import json
import math
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from synthesis.tasks import CandidateTask


class ContractValidationError(ValueError):
    pass


REJECTION_CAUSES = {
    "candidate_schema_error",
    "tool_missing",
    "tool_schema_error",
    "tool_runtime_error",
    "verification_failed",
    "infrastructure_error",
    "llm_provider_error",
    "llm_response_schema_error",
    "quality_duplicate",
    "solution_logic_error",
    "task_editor_rejected",
    "task_suggestion_rejected",
    "source_policy_rejected",
    "adapter_contract_rejected",
    "unsafe_generated_code",
}

LLM_RESPONSE_SCHEMA_REASONS = {
    "response_shape_mismatch",
    "provider_record_keys_mismatch",
    "invalid_task_type",
    "invalid_required_tools",
    "invalid_primary_tool",
    "invalid_tool_arguments",
    "invalid_difficulty",
    "invalid_expected_state",
    "invalid_candidate_id",
    "invalid_required_capabilities",
    "invalid_final_answer",
    "unsafe_provider_value",
    "duplicate_candidate_id",
    "batch_count_mismatch",
}

LLM_RESPONSE_SCHEMA_DETAILS = {
    "invalid_expected_state": {
        "expected_state_not_list",
        "expected_state_item_keys_mismatch",
        "expected_state_check_type_invalid",
        "expected_state_check_duplicate",
        "expected_state_expected_not_object",
        "expected_state_missing",
        "expected_state_arguments_invalid",
        "expected_state_reference_not_grounded",
    },
    "invalid_final_answer": {
        "final_answer_field_name_literal",
        "final_answer_not_grounded",
        "final_answer_sentinel_mismatch",
        "final_answer_derivation_failed",
    },
    "duplicate_candidate_id": {
        "within_batch",
        "across_batch",
    },
    "invalid_candidate_id": {
        "batch_prefix_mismatch",
    },
    "invalid_required_capabilities": {
        "required_capabilities_not_list",
        "required_capabilities_empty",
        "required_capabilities_duplicate",
        "required_capabilities_contract_mismatch",
    },
}

REFINEMENT_DECISIONS = {
    "not_repairable",
    "repair_candidate",
    "repair_policy",
}

CAPABILITY_GAP_TYPES = {
    "unknown_tool",
    "incompatible_arguments",
    "unavailable_side_effect",
    "environment_dependency_mismatch",
}

BRANCH_NODE_TYPES = {"attempt", "fallback"}
BRANCH_OUTCOMES = {"accepted", "rejected"}
TASK_TAXONOMY_NODES = {
    "single_tool_lookup",
    "verification_failure_fixture",
    "contact_followup",
    "branch_fallback",
    "unsupported_network_research",
}
TASK_SUGGESTION_OUTCOMES = {"accepted", "rejected"}
SOURCE_KINDS = {"fixture", "synthetic", "transformed", "external", "local_file"}
SOURCE_LICENSE_LABELS = {
    "fixture_internal",
    "synthetic_internal",
    "transformed_internal",
    "cc-by-4.0",
    "cc0-1.0",
    "public_domain",
}
LICENSE_POLICY_OUTCOMES = {"allowed", "rejected", "review_required"}
SOURCE_EVENT_TYPES = {
    "source_accepted",
    "source_rejected",
    "fetch_attempt",
    "fetch_accepted",
    "fetch_rejected",
    "environment_source_admitted",
    "environment_source_rejected",
}
SAFE_FETCH_CONTENT_TYPES = {"application/json"}
ADAPTER_OPERATIONS = {"tool.call"}
ADAPTER_EXECUTION_STATUSES = {"succeeded", "rejected", "failed"}
GENERATED_ARTIFACT_KINDS = {"tool_handler", "environment_builder", "verifier"}
GENERATED_CODE_SCAN_STATUSES = {"passed", "rejected"}
SANDBOX_EXECUTION_STATUSES = {"succeeded", "failed"}
SANDBOX_EXIT_CLASSES = {"zero", "nonzero", "timeout", "wrapper_error", "non_json"}
ARTIFACT_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
RUN_PROFILE_GENERATION_MODES = {
    "foundation_fixture",
    "deterministic_scale_probe",
    "mobile_fixture",
    "workspace_fixture",
    "llm",
}
RUN_PROFILE_PURPOSES = {"diagnostic_probe", "release_candidate", "benchmark"}
RUN_PROFILE_FEATURE_KEYS = {
    "enable_branching",
    "enable_task_expansion",
    "enable_refinement",
    "enable_mcp_adapter",
    "enable_sandbox_fixture",
    "enable_source_governance_fixture",
}
MANIFEST_ARTIFACT_KEYS = {
    "samples",
    "rejections",
    "episodes",
    "quality_report",
    "episode_quality_report",
    "episode_replay_report",
    "reward_labels",
    "reward_label_report",
    "parent_comparison",
    "review_queue",
    "tool_proposals",
    "source_events",
    "sandbox_audits",
    "profile_decision_report",
    "evaluation_report",
    "dataset_release_report",
    "dataset_release_pack",
    "release_quality_audit",
    "dataset_release_card",
    "release_review_queue",
    "review_resolution_report",
}
EVALUATION_TASK_STATUSES = {"passed", "failed"}
EVALUATION_DECISION_STATUSES = {"passed", "failed", "insufficient_evidence"}
EVALUATION_EXPECTED_OUTCOMES = {"passed", "controlled_failure"}
EVALUATION_DOMAINS = {
    "contacts_fixture",
    "mobile_messages_fixture",
    "workspace_tasks_fixture",
}
PROFILE_PROMOTION_STATUSES = {"passed", "failed", "blocked", "insufficient_evidence"}
DATASET_RELEASE_STATUSES = {
    "passed",
    "failed",
    "blocked",
    "ineligible",
    "insufficient_evidence",
}
RELEASE_COMPLETENESS_STATUSES = {"passed", "insufficient_evidence"}
DATASET_RELEASE_PACK_STATUSES = {"passed", "failed", "insufficient_evidence"}
RELEASE_QUALITY_AUDIT_STATUSES = {
    "clear",
    "watch",
    "insufficient_evidence",
    "blocked",
}
RELEASE_REVIEW_RISK_KINDS = {
    "small_release_size",
    "exact_duplicate_rate",
    "task_type_concentration",
    "tool_combination_concentration",
    "duplicate_family",
}
REVIEW_DECISION_OUTCOMES = {
    "accepted_risk",
    "confirmed_issue",
    "needs_follow_up",
}
REVIEW_DECISION_REASON_CODES = {
    "sufficient_context",
    "insufficient_diversity",
    "near_duplicate_suspected",
    "source_or_verifier_concern",
    "requires_more_data",
}
REVIEW_RESOLUTION_STATUSES = {
    "reviewed",
    "pending_review",
    "insufficient_evidence",
}
REPRESENTATIVE_SCALE_CLASSIFICATIONS = {
    "representative",
    "diagnostic_only",
    "insufficient_evidence",
}
REPRESENTATIVE_SCALE_RECOMMENDATIONS = {
    "activate_async_orchestration",
    "activate_semantic_duplicate_detection",
    "improve_generation_or_verification",
    "expand_representative_evidence",
    "no_change_recommended",
}
DOWNSTREAM_BENCHMARK_STATUSES = {
    "improved",
    "no_detected_improvement",
    "insufficient_evidence",
}
REPRESENTATIVE_SCALE_DOMAINS = (
    "contacts_fixture",
    "mobile_messages_fixture",
    "workspace_tasks_fixture",
)
REPRESENTATIVE_SCALE_SIGNALS = {
    "async_orchestration",
    "semantic_duplicate_detection",
}
DOWNSTREAM_RESULT_REASON_CODES = {
    "observation_unreadable_or_malformed",
    "benchmark_identity_mismatch",
    "release_identity_mismatch",
    "benchmark_suite_mismatch",
    "evaluation_identity_invalid",
    "metric_contract_invalid",
}
REVIEW_ITEM_ID_RE = re.compile(r"^review_item:sha256:[0-9a-f]{64}$")
REVIEWER_ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
SAFE_REVIEW_SAMPLE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
SAFE_REVIEW_DATASET_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
SAFE_REVIEW_REPORT_TEXT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.:-]*$")
UTC_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
RELEASE_REVIEW_NUMBER_PATTERN = r"[0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?"
RELEASE_REVIEW_REASON_PATTERNS = {
    "small_release_size": re.compile(
        r"^accepted ([0-9]+) is below small_release_watch_accepted_samples ([0-9]+)$"
    ),
    "exact_duplicate_rate": re.compile(
        rf"^exact_duplicate_rate ({RELEASE_REVIEW_NUMBER_PATTERN}) is above "
        rf"max_exact_duplicate_rate ({RELEASE_REVIEW_NUMBER_PATTERN})$"
    ),
    "task_type_concentration": re.compile(
        rf"^largest_task_type_share ({RELEASE_REVIEW_NUMBER_PATTERN}) is above "
        rf"max_largest_task_type_share ({RELEASE_REVIEW_NUMBER_PATTERN})$"
    ),
    "tool_combination_concentration": re.compile(
        rf"^largest_tool_combination_share ({RELEASE_REVIEW_NUMBER_PATTERN}) is above "
        rf"max_largest_tool_combination_share ({RELEASE_REVIEW_NUMBER_PATTERN})$"
    ),
}
DATASET_RELEASE_PACK_ARTIFACT_KEYS = {
    "manifest",
    "samples",
    "rejections",
    "quality_report",
    "evaluation_report",
    "profile_decision_report",
    "dataset_release_report",
}
RUNTIME_METADATA_KEYS = {
    "schema_version",
    "runtime_id",
    "runtime_version",
    "environment_id",
    "environment_version",
    "reset_recipe",
    "state_backend",
    "checkpoint_strategy",
    "source_provenance",
    "sandbox_policy",
    "adapter",
}
RUNTIME_ACTION_REQUEST_KEYS = {
    "schema_version",
    "runtime_id",
    "tool_name",
    "arguments",
    "arguments_hash",
    "action_id",
}
RUNTIME_ACTION_RESULT_KEYS = {
    "schema_version",
    "runtime_id",
    "tool_name",
    "status",
    "observation",
    "observation_hash",
    "state_change",
    "state_change_hash",
    "error_class",
    "side_effect_summary",
    "action_id",
}
EPISODE_OUTCOMES = {"accepted", "rejected", "failed"}
EPISODE_EVENT_TYPES = {"action", "observation", "state_change", "final_response", "error"}
EPISODE_QUALITY_DECISION_STATUSES = {
    "passed",
    "watch",
    "failed",
    "insufficient_evidence",
}
EPISODE_QUALITY_CHECK_NAMES = {
    "contract_valid",
    "has_action",
    "has_observation",
    "accepted_has_final_response",
    "accepted_has_no_error",
    "state_change_supported",
    "runtime_known",
}
EPISODE_REPLAY_DECISION_STATUSES = {
    "passed",
    "watch",
    "failed",
    "insufficient_evidence",
}
EPISODE_REPLAY_CHECK_NAMES = {
    "contract_valid",
    "runtime_supported",
    "runtime_rebuilt",
    "actions_replayed",
    "accepted_has_final_response",
    "observation_hash_match",
    "state_change_hash_match",
    "runtime_metadata_stable",
}
EPISODE_REPLAY_RUNTIME_METHODS = {"execute_action", "rebuild", "runtime_metadata"}
EPISODE_REPLAY_REGISTRY_METHODS: set[str] = set()
REWARD_LABEL_STATUSES = {"usable", "excluded", "insufficient_evidence"}
REWARD_LABEL_DECISION_STATUSES = {
    "passed",
    "watch",
    "failed",
    "insufficient_evidence",
}
REWARD_LABEL_COMPONENT_NAMES = {
    "outcome",
    "contract",
    "execution",
    "state_support",
    "replay_consistency",
}
REWARD_LABEL_CHECK_NAMES = {
    "labels_present",
    "label_contract_valid",
    "episode_contract_valid",
    "quality_evidence_aligned",
    "replay_evidence_aligned",
    "usable_label_coverage",
    "sanitized_summaries",
}
RUN_PROFILE_SOURCE_KINDS = {
    "local_contacts_json",
    "local_mobile_messages_json",
    "local_workspace_tasks_json",
}


def validate_candidate_task(task: object) -> "CandidateTask":
    from synthesis.tasks import CandidateTask

    if not isinstance(task, CandidateTask):
        raise ContractValidationError("candidate must be a CandidateTask")
    _require_non_empty_string(task.candidate_id, "candidate_id")
    _require_non_empty_string(task.instruction, "instruction")
    _require_mapping(task.constraints, "constraints")
    _require_mapping(task.difficulty, "difficulty")
    _require_non_empty_string(task.tool_name, "tool_name")
    _require_mapping(task.arguments, "arguments")
    _require_non_empty_string(task.expected_answer, "expected_answer")
    if task.expected_state is not None:
        _require_mapping(task.expected_state, "expected_state")
    if task.branch_plan is not None:
        validate_branch_plan_record(task.branch_plan)
    if not task.seed_ids:
        raise ContractValidationError("seed_ids must contain at least one seed id")
    for index, seed_id in enumerate(task.seed_ids):
        _require_non_empty_string(seed_id, f"seed_ids.{index}")
    return task


def validate_sample_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "sample")
    _require_non_empty_string(record.get("sample_id"), "sample_id")
    _require_non_empty_string(record.get("dataset_version"), "dataset_version")
    _validate_environment(record.get("environment"))
    _validate_tools(record.get("tools"))
    _validate_task(record.get("task"))
    _validate_trajectory(record.get("trajectory"))
    _require_non_empty_string(record.get("final_response"), "final_response")
    _validate_verifier(record.get("verifier"))
    _validate_verification(record.get("verification"))
    _validate_quality(record.get("quality"))
    _validate_lineage(record.get("lineage"))


def validate_rejection_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "rejection")
    _require_non_empty_string(record.get("candidate_id"), "candidate_id")
    cause = record.get("cause")
    _require_non_empty_string(cause, "cause")
    if cause not in REJECTION_CAUSES:
        raise ContractValidationError(f"cause must be one of {sorted(REJECTION_CAUSES)}")
    _validate_task(record.get("task"))
    details = _require_mapping(record.get("details"), "details")
    schema_reason = details.get("schema_reason")
    schema_detail = details.get("schema_detail")
    is_generation_schema_rejection = (
        record.get("candidate_id") == "generation_stage"
        and cause == "llm_response_schema_error"
    )
    if is_generation_schema_rejection:
        _require_non_empty_string(schema_reason, "details.schema_reason")
        if schema_reason not in LLM_RESPONSE_SCHEMA_REASONS:
            raise ContractValidationError(
                "details.schema_reason must be an approved LLM response schema reason"
            )
        if schema_detail is not None:
            _require_non_empty_string(schema_detail, "details.schema_detail")
            if schema_detail not in LLM_RESPONSE_SCHEMA_DETAILS.get(schema_reason, set()):
                raise ContractValidationError(
                    "details.schema_detail must match the approved LLM response schema reason"
                )
    elif schema_reason is not None:
        raise ContractValidationError(
            "details.schema_reason is only allowed for generation-stage "
            "llm_response_schema_error rejections"
        )
    elif schema_detail is not None:
        raise ContractValidationError(
            "details.schema_detail is only allowed for generation-stage "
            "llm_response_schema_error rejections"
        )
    if "run_profile" in details:
        _validate_run_profile_attribution(
            details.get("run_profile"),
            "details.run_profile",
        )


def validate_manifest_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "manifest")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    _require_non_empty_string(record.get("dataset_version"), "dataset_version")
    parent = record.get("parent_dataset_version")
    if parent is not None:
        _require_non_empty_string(parent, "parent_dataset_version")
    _require_int(record.get("accepted_count"), "accepted_count")
    _require_int(record.get("rejected_count"), "rejected_count")
    _validate_manifest_artifacts(record.get("artifacts"))
    quality = _require_mapping(record.get("quality"), "quality")
    _require_number(quality.get("success_rate"), "quality.success_rate")
    _require_number(quality.get("executable_rate"), "quality.executable_rate")
    _require_sequence(record.get("environment_versions"), "environment_versions")
    _require_sequence(record.get("tool_versions"), "tool_versions")
    _require_sequence(record.get("verifier_versions"), "verifier_versions")
    _require_sequence(record.get("generator_config_hashes"), "generator_config_hashes")
    _require_mapping(record.get("rejection_causes"), "rejection_causes")
    if "source_policy_hashes" in record:
        _require_non_empty_string_sequence(
            record.get("source_policy_hashes"),
            "source_policy_hashes",
        )
    if "run_profile" in record:
        _validate_run_profile_metadata(record.get("run_profile"))


def validate_runtime_metadata_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "runtime_metadata")
    from awm_runtime.runtime import validate_runtime_metadata_safety

    validate_runtime_metadata_safety(record)
    unexpected = sorted(str(key) for key in record if key not in RUNTIME_METADATA_KEYS)
    if unexpected:
        raise ContractValidationError(
            f"runtime_metadata contains unsupported keys: {', '.join(unexpected)}"
        )
    missing = sorted(RUNTIME_METADATA_KEYS.difference(record))
    if missing:
        raise ContractValidationError(
            f"runtime_metadata missing required keys: {', '.join(missing)}"
        )
    schema_version = _require_non_empty_string(
        record.get("schema_version"),
        "runtime_metadata.schema_version",
    )
    if schema_version != "runtime_metadata_v1":
        raise ContractValidationError("runtime_metadata.schema_version is unsupported")
    _require_non_empty_string(record.get("runtime_id"), "runtime_metadata.runtime_id")
    _require_non_empty_string(record.get("runtime_version"), "runtime_metadata.runtime_version")
    _require_non_empty_string(record.get("environment_id"), "runtime_metadata.environment_id")
    _require_non_empty_string(
        record.get("environment_version"),
        "runtime_metadata.environment_version",
    )
    reset_recipe = _require_non_empty_string(
        record.get("reset_recipe"),
        "runtime_metadata.reset_recipe",
    )
    if ":" not in reset_recipe:
        raise ContractValidationError("runtime_metadata.reset_recipe is unsupported")
    state_backend = _require_non_empty_string(
        record.get("state_backend"),
        "runtime_metadata.state_backend",
    )
    if state_backend != "sqlite":
        raise ContractValidationError("runtime_metadata.state_backend is unsupported")
    checkpoint_strategy = _require_non_empty_string(
        record.get("checkpoint_strategy"),
        "runtime_metadata.checkpoint_strategy",
    )
    if checkpoint_strategy != "sqlite_backup":
        raise ContractValidationError("runtime_metadata.checkpoint_strategy is unsupported")
    _require_mapping(record.get("source_provenance"), "runtime_metadata.source_provenance")
    _require_mapping(record.get("sandbox_policy"), "runtime_metadata.sandbox_policy")
    _require_mapping(record.get("adapter"), "runtime_metadata.adapter")


def validate_runtime_action_request_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "runtime_action_request")
    if _contains_raw_secret(record) or _contains_runtime_action_unsafe_material(record):
        raise ContractValidationError("runtime_action_request contains raw secret material")
    unexpected = sorted(str(key) for key in record if key not in RUNTIME_ACTION_REQUEST_KEYS)
    if unexpected:
        raise ContractValidationError(
            f"runtime_action_request contains unsupported keys: {', '.join(unexpected)}"
        )
    for key in ("schema_version", "runtime_id", "tool_name", "arguments", "arguments_hash"):
        if key not in record:
            raise ContractValidationError(f"runtime_action_request missing required key: {key}")
    schema_version = _require_non_empty_string(
        record.get("schema_version"),
        "runtime_action_request.schema_version",
    )
    if schema_version != "runtime_action_request_v1":
        raise ContractValidationError("runtime_action_request.schema_version is unsupported")
    _require_non_empty_string(record.get("runtime_id"), "runtime_action_request.runtime_id")
    _require_non_empty_string(record.get("tool_name"), "runtime_action_request.tool_name")
    _require_mapping(record.get("arguments"), "runtime_action_request.arguments")
    _validate_content_hash(
        record.get("arguments_hash"),
        "runtime_action_request.arguments_hash",
    )
    if "action_id" in record:
        _require_non_empty_string(record.get("action_id"), "runtime_action_request.action_id")


def validate_runtime_action_result_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "runtime_action_result")
    if _contains_raw_secret(record) or _contains_runtime_action_unsafe_material(record):
        raise ContractValidationError("runtime_action_result contains raw secret material")
    unexpected = sorted(str(key) for key in record if key not in RUNTIME_ACTION_RESULT_KEYS)
    if unexpected:
        raise ContractValidationError(
            f"runtime_action_result contains unsupported keys: {', '.join(unexpected)}"
        )
    required = {
        "schema_version",
        "runtime_id",
        "tool_name",
        "status",
        "observation",
        "observation_hash",
        "state_change_hash",
        "error_class",
        "side_effect_summary",
    }
    missing = sorted(key for key in required if key not in record)
    if missing:
        raise ContractValidationError(
            f"runtime_action_result missing required keys: {', '.join(missing)}"
        )
    schema_version = _require_non_empty_string(
        record.get("schema_version"),
        "runtime_action_result.schema_version",
    )
    if schema_version != "runtime_action_result_v1":
        raise ContractValidationError("runtime_action_result.schema_version is unsupported")
    _require_non_empty_string(record.get("runtime_id"), "runtime_action_result.runtime_id")
    _require_non_empty_string(record.get("tool_name"), "runtime_action_result.tool_name")
    status = _require_non_empty_string(record.get("status"), "runtime_action_result.status")
    if status not in {"succeeded", "failed"}:
        raise ContractValidationError("runtime_action_result.status is unsupported")
    _require_mapping(record.get("observation"), "runtime_action_result.observation")
    _validate_content_hash(
        record.get("observation_hash"),
        "runtime_action_result.observation_hash",
    )
    if "state_change" in record:
        _require_mapping(record.get("state_change"), "runtime_action_result.state_change")
    _validate_content_hash(
        record.get("state_change_hash"),
        "runtime_action_result.state_change_hash",
    )
    error_class = record.get("error_class")
    if status == "failed":
        _require_non_empty_string(error_class, "runtime_action_result.error_class")
    elif error_class is not None:
        raise ContractValidationError(
            "runtime_action_result.error_class must be null when succeeded"
        )
    side_effect_summary = _require_mapping(
        record.get("side_effect_summary"),
        "runtime_action_result.side_effect_summary",
    )
    if not isinstance(side_effect_summary.get("state_changed"), bool):
        raise ContractValidationError(
            "runtime_action_result.side_effect_summary.state_changed must be a bool"
        )
    if "action_id" in record:
        _require_non_empty_string(record.get("action_id"), "runtime_action_result.action_id")


def validate_episode_log_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "episode_log")
    schema_version = _require_non_empty_string(
        record.get("schema_version"),
        "episode_log.schema_version",
    )
    if schema_version != "episode_log_v1":
        raise ContractValidationError("episode_log.schema_version is unsupported")
    _require_non_empty_string(record.get("episode_id"), "episode_log.episode_id")
    _require_non_empty_string(record.get("candidate_id"), "episode_log.candidate_id")
    _validate_episode_runtime(record.get("runtime"))
    policy = _require_mapping(record.get("policy"), "episode_log.policy")
    _require_non_empty_string(policy.get("policy_id"), "episode_log.policy.policy_id")
    _require_non_empty_string(policy.get("role"), "episode_log.policy.role")
    verifier = _require_mapping(record.get("verifier"), "episode_log.verifier")
    _require_non_empty_string(verifier.get("id"), "episode_log.verifier.id")
    _require_non_empty_string(verifier.get("version"), "episode_log.verifier.version")
    transitions = _require_sequence(record.get("transitions"), "episode_log.transitions")
    if not transitions:
        raise ContractValidationError("episode_log.transitions must contain at least one entry")
    for expected_index, raw_transition in enumerate(transitions, start=1):
        _validate_episode_transition(raw_transition, expected_index)
    outcome = _require_mapping(record.get("outcome"), "episode_log.outcome")
    status = _require_non_empty_string(outcome.get("status"), "episode_log.outcome.status")
    if status not in EPISODE_OUTCOMES:
        raise ContractValidationError("episode_log.outcome.status is unsupported")
    failure_cause = outcome.get("failure_cause")
    if status == "accepted":
        if failure_cause is not None:
            raise ContractValidationError(
                "episode_log.outcome.failure_cause must be null when accepted"
            )
    elif not isinstance(failure_cause, str) or not failure_cause.strip():
        raise ContractValidationError(
            "episode_log.outcome.failure_cause must be a non-empty string"
        )


def validate_episode_quality_report_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "episode_quality_report")
    if _contains_raw_secret(record):
        raise ContractValidationError("episode_quality_report contains raw secret material")
    schema_version = _require_non_empty_string(record.get("schema_version"), "schema_version")
    if schema_version != "episode_quality_report_v1":
        raise ContractValidationError("schema_version is unsupported")
    _require_non_empty_string(record.get("dataset_version"), "dataset_version")

    inputs = _require_mapping(record.get("inputs"), "inputs")
    for field in ("manifest_path", "episodes_path"):
        artifact_name = _require_non_empty_string(inputs.get(field), f"inputs.{field}")
        _validate_artifact_filename(artifact_name, f"inputs.{field}")

    observed = _require_mapping(record.get("observed"), "observed")
    for field in ("episode_count", "accepted", "rejected", "failed"):
        _require_int(observed.get(field), f"observed.{field}")
    _validate_string_count_mapping(observed.get("runtime_counts"), "observed.runtime_counts")
    tool_names = _require_sequence(observed.get("tool_names"), "observed.tool_names")
    for index, tool_name in enumerate(tool_names):
        _require_non_empty_string(tool_name, f"observed.tool_names.{index}")

    seen_checks: set[str] = set()
    for index, raw_check in enumerate(_require_sequence(record.get("checks"), "checks")):
        check = _require_mapping(raw_check, f"checks.{index}")
        name = _require_non_empty_string(check.get("name"), f"checks.{index}.name")
        if name not in EPISODE_QUALITY_CHECK_NAMES:
            raise ContractValidationError(f"checks.{index}.name is unsupported")
        if name in seen_checks:
            raise ContractValidationError(f"checks.{index}.name is duplicated")
        seen_checks.add(name)
        status = _require_non_empty_string(check.get("status"), f"checks.{index}.status")
        if status not in {"passed", "failed"}:
            raise ContractValidationError(f"checks.{index}.status is unsupported")
        _require_int(check.get("passed"), f"checks.{index}.passed")
        _require_int(check.get("failed"), f"checks.{index}.failed")
        if not isinstance(check.get("required"), bool):
            raise ContractValidationError(f"checks.{index}.required must be a bool")

    for index, raw_summary in enumerate(
        _require_sequence(record.get("episode_summaries"), "episode_summaries")
    ):
        summary = _require_mapping(raw_summary, f"episode_summaries.{index}")
        allowed_keys = {
            "episode_id",
            "candidate_id",
            "runtime_id",
            "outcome_status",
            "action_count",
            "observation_count",
            "state_change_count",
            "final_response_count",
            "error_count",
            "tool_names",
            "failed_checks",
        }
        unexpected = sorted(str(key) for key in summary if key not in allowed_keys)
        if unexpected:
            raise ContractValidationError(
                f"episode_summaries.{index} contains unsupported keys: {', '.join(unexpected)}"
            )
        for field in ("episode_id", "candidate_id", "runtime_id", "outcome_status"):
            _require_non_empty_string(summary.get(field), f"episode_summaries.{index}.{field}")
        for field in (
            "action_count",
            "observation_count",
            "state_change_count",
            "final_response_count",
            "error_count",
        ):
            _require_int(summary.get(field), f"episode_summaries.{index}.{field}")
        for tool_index, tool_name in enumerate(
            _require_sequence(
                summary.get("tool_names"),
                f"episode_summaries.{index}.tool_names",
            )
        ):
            _require_non_empty_string(
                tool_name,
                f"episode_summaries.{index}.tool_names.{tool_index}",
            )
        for check_index, check_name in enumerate(
            _require_sequence(
                summary.get("failed_checks"),
                f"episode_summaries.{index}.failed_checks",
            )
        ):
            name = _require_non_empty_string(
                check_name,
                f"episode_summaries.{index}.failed_checks.{check_index}",
            )
            if name not in EPISODE_QUALITY_CHECK_NAMES:
                raise ContractValidationError(
                    f"episode_summaries.{index}.failed_checks.{check_index} is unsupported"
                )

    decision = _require_mapping(record.get("decision"), "decision")
    status = _require_non_empty_string(decision.get("status"), "decision.status")
    if status not in EPISODE_QUALITY_DECISION_STATUSES:
        raise ContractValidationError("decision.status is unsupported")
    for field in ("reasons", "triggered_by"):
        values = _require_sequence(decision.get(field), f"decision.{field}")
        for index, value in enumerate(values):
            _require_non_empty_string(value, f"decision.{field}.{index}")


def validate_episode_replay_report_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "episode_replay_report")
    if _contains_raw_secret(record):
        raise ContractValidationError("episode_replay_report contains raw secret material")
    schema_version = _require_non_empty_string(record.get("schema_version"), "schema_version")
    if schema_version != "episode_replay_report_v1":
        raise ContractValidationError("schema_version is unsupported")
    _require_non_empty_string(record.get("dataset_version"), "dataset_version")

    inputs = _require_mapping(record.get("inputs"), "inputs")
    for field in ("manifest_path", "episodes_path"):
        artifact_name = _require_non_empty_string(inputs.get(field), f"inputs.{field}")
        _validate_artifact_filename(artifact_name, f"inputs.{field}")

    observed = _require_mapping(record.get("observed"), "observed")
    for field in ("episode_count", "replayed"):
        _require_int(observed.get(field), f"observed.{field}")
    _validate_string_count_mapping(observed.get("runtime_counts"), "observed.runtime_counts")
    tool_names = _require_sequence(observed.get("tool_names"), "observed.tool_names")
    for index, tool_name in enumerate(tool_names):
        _require_non_empty_string(tool_name, f"observed.tool_names.{index}")

    seen_checks: set[str] = set()
    for index, raw_check in enumerate(_require_sequence(record.get("checks"), "checks")):
        check = _require_mapping(raw_check, f"checks.{index}")
        name = _require_non_empty_string(check.get("name"), f"checks.{index}.name")
        if name not in EPISODE_REPLAY_CHECK_NAMES:
            raise ContractValidationError(f"checks.{index}.name is unsupported")
        if name in seen_checks:
            raise ContractValidationError(f"checks.{index}.name is duplicated")
        seen_checks.add(name)
        status = _require_non_empty_string(check.get("status"), f"checks.{index}.status")
        if status not in {"passed", "failed"}:
            raise ContractValidationError(f"checks.{index}.status is unsupported")
        _require_int(check.get("passed"), f"checks.{index}.passed")
        _require_int(check.get("failed"), f"checks.{index}.failed")
        if not isinstance(check.get("required"), bool):
            raise ContractValidationError(f"checks.{index}.required must be a bool")

    allowed_summary_keys = {
        "episode_id",
        "candidate_id",
        "runtime_id",
        "outcome_status",
        "action_count",
        "replayed_action_count",
        "observation_match_count",
        "observation_mismatch_count",
        "state_change_match_count",
        "state_change_mismatch_count",
        "final_response_count",
        "tool_names",
        "failed_checks",
    }
    for index, raw_summary in enumerate(
        _require_sequence(record.get("episode_summaries"), "episode_summaries")
    ):
        summary = _require_mapping(raw_summary, f"episode_summaries.{index}")
        unexpected = sorted(str(key) for key in summary if key not in allowed_summary_keys)
        if unexpected:
            raise ContractValidationError(
                f"episode_summaries.{index} contains unsupported keys: {', '.join(unexpected)}"
            )
        for field in ("episode_id", "candidate_id", "runtime_id", "outcome_status"):
            _require_non_empty_string(summary.get(field), f"episode_summaries.{index}.{field}")
        for field in (
            "action_count",
            "replayed_action_count",
            "observation_match_count",
            "observation_mismatch_count",
            "state_change_match_count",
            "state_change_mismatch_count",
            "final_response_count",
        ):
            _require_int(summary.get(field), f"episode_summaries.{index}.{field}")
        for tool_index, tool_name in enumerate(
            _require_sequence(
                summary.get("tool_names"),
                f"episode_summaries.{index}.tool_names",
            )
        ):
            _require_non_empty_string(
                tool_name,
                f"episode_summaries.{index}.tool_names.{tool_index}",
            )
        for check_index, check_name in enumerate(
            _require_sequence(
                summary.get("failed_checks"),
                f"episode_summaries.{index}.failed_checks",
            )
        ):
            name = _require_non_empty_string(
                check_name,
                f"episode_summaries.{index}.failed_checks.{check_index}",
            )
            if name not in EPISODE_REPLAY_CHECK_NAMES:
                raise ContractValidationError(
                    f"episode_summaries.{index}.failed_checks.{check_index} is unsupported"
                )

    boundary = _require_mapping(
        record.get("runtime_boundary_evidence"),
        "runtime_boundary_evidence",
    )
    runtime_methods = _require_sequence(
        boundary.get("runtime_methods_used"),
        "runtime_boundary_evidence.runtime_methods_used",
    )
    for index, method_name in enumerate(runtime_methods):
        name = _require_non_empty_string(
            method_name,
            f"runtime_boundary_evidence.runtime_methods_used.{index}",
        )
        if name not in EPISODE_REPLAY_RUNTIME_METHODS:
            raise ContractValidationError(
                f"runtime_boundary_evidence.runtime_methods_used.{index} is unsupported"
            )
    registry_methods = _require_sequence(
        boundary.get("registry_methods_used"),
        "runtime_boundary_evidence.registry_methods_used",
    )
    for index, method_name in enumerate(registry_methods):
        name = _require_non_empty_string(
            method_name,
            f"runtime_boundary_evidence.registry_methods_used.{index}",
        )
        if name not in EPISODE_REPLAY_REGISTRY_METHODS:
            raise ContractValidationError(
                f"runtime_boundary_evidence.registry_methods_used.{index} is unsupported"
            )
    if not isinstance(boundary.get("requires_external_package"), bool):
        raise ContractValidationError(
            "runtime_boundary_evidence.requires_external_package must be a bool"
        )
    _require_non_empty_string(
        boundary.get("extraction_signal"),
        "runtime_boundary_evidence.extraction_signal",
    )

    decision = _require_mapping(record.get("decision"), "decision")
    status = _require_non_empty_string(decision.get("status"), "decision.status")
    if status not in EPISODE_REPLAY_DECISION_STATUSES:
        raise ContractValidationError("decision.status is unsupported")
    for field in ("reasons", "triggered_by"):
        values = _require_sequence(decision.get(field), f"decision.{field}")
        for index, value in enumerate(values):
            _require_non_empty_string(value, f"decision.{field}.{index}")


def validate_reward_label_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "reward_label")
    if _contains_raw_secret(record):
        raise ContractValidationError("reward_label contains raw secret material")
    schema_version = _require_non_empty_string(record.get("schema_version"), "schema_version")
    if schema_version != "reward_label_v1":
        raise ContractValidationError("schema_version is unsupported")
    for field in ("label_id", "episode_id", "candidate_id"):
        _require_non_empty_string(record.get(field), field)
    _require_non_empty_string(record.get("runtime_id"), "runtime_id")
    outcome_status = _require_non_empty_string(record.get("outcome_status"), "outcome_status")
    if outcome_status not in EPISODE_OUTCOMES:
        raise ContractValidationError("outcome_status is unsupported")
    scalar_reward = _require_number(record.get("scalar_reward"), "scalar_reward")
    _validate_rate(scalar_reward, "scalar_reward")
    label_status = _require_non_empty_string(record.get("label_status"), "label_status")
    if label_status not in REWARD_LABEL_STATUSES:
        raise ContractValidationError("label_status is unsupported")

    label_source = _require_mapping(record.get("label_source"), "label_source")
    for raw_key, raw_value in label_source.items():
        key = _require_non_empty_string(raw_key, "label_source key")
        if key in {
            "raw_payload",
            "prompt",
            "provider_payload",
            "arguments",
            "observations",
            "final_response",
        }:
            raise ContractValidationError(f"label_source.{key} is unsupported")
        value = _require_non_empty_string(raw_value, f"label_source.{key}")
        _validate_artifact_filename(value, f"label_source.{key}")

    components = _require_mapping(record.get("components"), "components")
    unexpected_components = sorted(
        str(key) for key in components if key not in REWARD_LABEL_COMPONENT_NAMES
    )
    if unexpected_components:
        raise ContractValidationError(
            f"components contains unsupported keys: {', '.join(unexpected_components)}"
        )
    missing_components = sorted(REWARD_LABEL_COMPONENT_NAMES.difference(components))
    if missing_components:
        raise ContractValidationError(
            f"components missing required keys: {', '.join(missing_components)}"
        )
    for component_name in sorted(REWARD_LABEL_COMPONENT_NAMES):
        value = _require_number(components.get(component_name), f"components.{component_name}")
        _validate_rate(value, f"components.{component_name}")

    preference_group = _require_mapping(record.get("preference_group"), "preference_group")
    allowed_preference_keys = {"group_id", "rank", "tie_breaker"}
    unexpected_preference_keys = sorted(
        str(key) for key in preference_group if key not in allowed_preference_keys
    )
    if unexpected_preference_keys:
        raise ContractValidationError(
            "preference_group contains unsupported keys: "
            + ", ".join(unexpected_preference_keys)
        )
    _require_non_empty_string(preference_group.get("group_id"), "preference_group.group_id")
    _require_positive_int(preference_group.get("rank"), "preference_group.rank")
    _require_non_empty_string(
        preference_group.get("tie_breaker"),
        "preference_group.tie_breaker",
    )

    reasons = _require_sequence(record.get("reasons"), "reasons")
    if not reasons:
        raise ContractValidationError("reasons must contain at least one reason")
    for index, reason in enumerate(reasons):
        _require_non_empty_string(reason, f"reasons.{index}")


def validate_reward_label_report_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "reward_label_report")
    if _contains_raw_secret(record):
        raise ContractValidationError("reward_label_report contains raw secret material")
    schema_version = _require_non_empty_string(record.get("schema_version"), "schema_version")
    if schema_version != "reward_label_report_v1":
        raise ContractValidationError("schema_version is unsupported")
    _require_non_empty_string(record.get("dataset_version"), "dataset_version")

    inputs = _require_mapping(record.get("inputs"), "inputs")
    for field in (
        "manifest_path",
        "episodes_path",
        "episode_quality_report_path",
        "episode_replay_report_path",
        "reward_labels_path",
    ):
        raw_path = inputs.get(field)
        if raw_path is None:
            continue
        artifact_name = _require_non_empty_string(raw_path, f"inputs.{field}")
        _validate_artifact_filename(artifact_name, f"inputs.{field}")

    observed = _require_mapping(record.get("observed"), "observed")
    for field in ("episode_count", "label_count", "usable", "excluded", "insufficient_evidence"):
        _require_int(observed.get(field), f"observed.{field}")
    runtime_counts = _validate_string_count_mapping(
        observed.get("runtime_counts"),
        "observed.runtime_counts",
    )
    average = _require_number(observed.get("average_scalar_reward"), "observed.average_scalar_reward")
    _validate_rate(average, "observed.average_scalar_reward")

    seen_checks: set[str] = set()
    for index, raw_check in enumerate(_require_sequence(record.get("checks"), "checks")):
        check = _require_mapping(raw_check, f"checks.{index}")
        name = _require_non_empty_string(check.get("name"), f"checks.{index}.name")
        if name not in REWARD_LABEL_CHECK_NAMES:
            raise ContractValidationError(f"checks.{index}.name is unsupported")
        if name in seen_checks:
            raise ContractValidationError(f"checks.{index}.name is duplicated")
        seen_checks.add(name)
        status = _require_non_empty_string(check.get("status"), f"checks.{index}.status")
        if status not in {"passed", "failed"}:
            raise ContractValidationError(f"checks.{index}.status is unsupported")
        _require_int(check.get("passed"), f"checks.{index}.passed")
        _require_int(check.get("failed"), f"checks.{index}.failed")
        if not isinstance(check.get("required"), bool):
            raise ContractValidationError(f"checks.{index}.required must be a bool")

    allowed_summary_keys = {
        "label_id",
        "episode_id",
        "candidate_id",
        "runtime_id",
        "label_status",
        "scalar_reward",
        "failed_checks",
    }
    for index, raw_summary in enumerate(
        _require_sequence(record.get("label_summaries"), "label_summaries")
    ):
        summary = _require_mapping(raw_summary, f"label_summaries.{index}")
        unexpected = sorted(str(key) for key in summary if key not in allowed_summary_keys)
        if unexpected:
            raise ContractValidationError(
                f"label_summaries.{index} contains unsupported keys: {', '.join(unexpected)}"
            )
        for field in ("label_id", "episode_id", "candidate_id", "runtime_id", "label_status"):
            _require_non_empty_string(summary.get(field), f"label_summaries.{index}.{field}")
        if summary.get("runtime_id") not in runtime_counts:
            raise ContractValidationError(
                f"label_summaries.{index}.runtime_id lacks report-local evidence"
            )
        if summary.get("label_status") not in REWARD_LABEL_STATUSES:
            raise ContractValidationError(f"label_summaries.{index}.label_status is unsupported")
        scalar = _require_number(
            summary.get("scalar_reward"),
            f"label_summaries.{index}.scalar_reward",
        )
        _validate_rate(scalar, f"label_summaries.{index}.scalar_reward")
        for check_index, raw_check in enumerate(
            _require_sequence(
                summary.get("failed_checks"),
                f"label_summaries.{index}.failed_checks",
            )
        ):
            check_name = _require_non_empty_string(
                raw_check,
                f"label_summaries.{index}.failed_checks.{check_index}",
            )
            if check_name not in REWARD_LABEL_CHECK_NAMES:
                raise ContractValidationError(
                    f"label_summaries.{index}.failed_checks.{check_index} is unsupported"
                )

    decision = _require_mapping(record.get("decision"), "decision")
    status = _require_non_empty_string(decision.get("status"), "decision.status")
    if status not in REWARD_LABEL_DECISION_STATUSES:
        raise ContractValidationError("decision.status is unsupported")
    for field in ("reasons", "triggered_by"):
        values = _require_sequence(decision.get(field), f"decision.{field}")
        for index, value in enumerate(values):
            _require_non_empty_string(value, f"decision.{field}.{index}")


def _validate_episode_runtime(raw: object) -> None:
    runtime = _require_mapping(raw, "episode_log.runtime")
    allowed_keys = {"schema_version", "runtime_id", "runtime_version"}
    unexpected = sorted(str(key) for key in runtime if key not in allowed_keys)
    if unexpected:
        raise ContractValidationError(
            f"episode_log.runtime contains unsupported keys: {', '.join(unexpected)}"
        )
    schema_version = _require_non_empty_string(
        runtime.get("schema_version"),
        "episode_log.runtime.schema_version",
    )
    if schema_version != "runtime_metadata_v1":
        raise ContractValidationError("episode_log.runtime.schema_version is unsupported")
    _require_non_empty_string(runtime.get("runtime_id"), "episode_log.runtime.runtime_id")
    _require_non_empty_string(
        runtime.get("runtime_version"),
        "episode_log.runtime.runtime_version",
    )


def _validate_episode_transition(raw: object, expected_index: int) -> None:
    transition = _require_mapping(raw, f"episode_log.transitions.{expected_index - 1}")
    transition_index = _require_positive_int(
        transition.get("transition_index"),
        f"episode_log.transitions.{expected_index - 1}.transition_index",
    )
    if transition_index != expected_index:
        raise ContractValidationError("episode_log.transition_index must be ordered")
    event_type = _require_non_empty_string(
        transition.get("event_type"),
        f"episode_log.transitions.{expected_index - 1}.event_type",
    )
    if event_type not in EPISODE_EVENT_TYPES:
        raise ContractValidationError("episode_log.transition event_type is unsupported")
    if event_type in {"action", "observation", "state_change"}:
        _require_non_empty_string(
            transition.get("tool_name"),
            f"episode_log.transitions.{expected_index - 1}.tool_name",
        )
    if event_type == "action":
        _validate_content_hash(
            transition.get("arguments_hash"),
            f"episode_log.transitions.{expected_index - 1}.arguments_hash",
        )
        _require_mapping(
            transition.get("arguments"),
            f"episode_log.transitions.{expected_index - 1}.arguments",
        )
    elif event_type == "observation":
        _validate_content_hash(
            transition.get("observation_hash"),
            f"episode_log.transitions.{expected_index - 1}.observation_hash",
        )
        _require_mapping(
            transition.get("observation"),
            f"episode_log.transitions.{expected_index - 1}.observation",
        )
    elif event_type == "state_change":
        _validate_content_hash(
            transition.get("change_hash"),
            f"episode_log.transitions.{expected_index - 1}.change_hash",
        )
        _require_mapping(
            transition.get("change"),
            f"episode_log.transitions.{expected_index - 1}.change",
        )
    elif event_type == "final_response":
        _validate_content_hash(
            transition.get("content_hash"),
            f"episode_log.transitions.{expected_index - 1}.content_hash",
        )
        _require_non_empty_string(
            transition.get("content"),
            f"episode_log.transitions.{expected_index - 1}.content",
        )
    elif event_type == "error":
        _validate_content_hash(
            transition.get("error_hash"),
            f"episode_log.transitions.{expected_index - 1}.error_hash",
        )
        _require_mapping(
            transition.get("error"),
            f"episode_log.transitions.{expected_index - 1}.error",
        )


def validate_representative_scale_campaign_record(record: Mapping[str, Any]) -> None:
    campaign = _require_mapping(record, "representative_scale_campaign")
    _require_exact_keys(campaign, {"schema_version", "campaign_label", "runs"}, "representative_scale_campaign")
    if campaign.get("schema_version") != "representative_scale_campaign_v1":
        raise ContractValidationError("schema_version is unsupported")
    campaign_label = _require_non_empty_string(campaign.get("campaign_label"), "campaign_label")
    if not ARTIFACT_ID_RE.fullmatch(campaign_label):
        raise ContractValidationError("campaign_label must be a safe identifier")
    runs = _require_sequence(campaign.get("runs"), "runs")
    if len(runs) != len(REPRESENTATIVE_SCALE_DOMAINS):
        raise ContractValidationError("runs must contain exactly three supported domains")
    seen: set[str] = set()
    for index, raw_run in enumerate(runs):
        run = _require_mapping(raw_run, f"runs.{index}")
        _require_exact_keys(run, {"domain_id", "artifact_dir"}, f"runs.{index}")
        domain_id = _require_non_empty_string(run.get("domain_id"), f"runs.{index}.domain_id")
        if domain_id not in REPRESENTATIVE_SCALE_DOMAINS or domain_id in seen:
            raise ContractValidationError(f"runs.{index}.domain_id is unsupported or duplicated")
        seen.add(domain_id)
        _validate_safe_input_path(
            _require_non_empty_string(run.get("artifact_dir"), f"runs.{index}.artifact_dir"),
            f"runs.{index}.artifact_dir",
        )
    if seen != set(REPRESENTATIVE_SCALE_DOMAINS):
        raise ContractValidationError("runs must contain every supported domain")


def validate_representative_scale_evidence_record(record: Mapping[str, Any]) -> None:
    evidence = _require_mapping(record, "representative_scale_evidence")
    _require_exact_keys(
        evidence,
        {"schema_version", "campaign_id", "campaign_label", "domains", "review", "triggered_signals", "decision"},
        "representative_scale_evidence",
    )
    if evidence.get("schema_version") != "representative_scale_evidence_v1":
        raise ContractValidationError("schema_version is unsupported")
    _validate_canonical_digest_id(evidence.get("campaign_id"), "campaign_id", "scale_campaign")
    campaign_label = _require_non_empty_string(evidence.get("campaign_label"), "campaign_label")
    if not ARTIFACT_ID_RE.fullmatch(campaign_label):
        raise ContractValidationError("campaign_label must be a safe identifier")
    domains = _require_sequence(evidence.get("domains"), "domains")
    if len(domains) != len(REPRESENTATIVE_SCALE_DOMAINS):
        raise ContractValidationError("domains must contain exactly three entries")
    for index, (raw_domain, expected_domain) in enumerate(zip(domains, REPRESENTATIVE_SCALE_DOMAINS)):
        _validate_scale_domain_summary(raw_domain, index=index, expected_domain=expected_domain)
    review = _require_mapping(evidence.get("review"), "review")
    review_keys = {"queued", "resolved", "pending", "confirmed_issue", "accepted_risk", "needs_follow_up", "review_minutes"}
    _require_exact_keys(review, review_keys, "review")
    for key in review_keys:
        _require_int(review.get(key), f"review.{key}")
    signals = _require_sequence(evidence.get("triggered_signals"), "triggered_signals")
    _validate_unique_vocabulary(signals, REPRESENTATIVE_SCALE_SIGNALS, "triggered_signals")
    decision = _require_mapping(evidence.get("decision"), "decision")
    _require_exact_keys(decision, {"recommendation", "reasons"}, "decision")
    recommendation = _require_non_empty_string(decision.get("recommendation"), "decision.recommendation")
    if recommendation not in REPRESENTATIVE_SCALE_RECOMMENDATIONS:
        raise ContractValidationError("decision.recommendation is unsupported")
    _require_non_empty_string_sequence(decision.get("reasons"), "decision.reasons")


def validate_downstream_benchmark_bundle_record(record: Mapping[str, Any]) -> None:
    bundle = _require_mapping(record, "downstream_benchmark_bundle")
    _require_exact_keys(bundle, {"schema_version", "benchmark_id", "dataset_version", "release", "protocol", "claims"}, "downstream_benchmark_bundle")
    if bundle.get("schema_version") != "downstream_benchmark_bundle_v1":
        raise ContractValidationError("schema_version is unsupported")
    _validate_canonical_digest_id(bundle.get("benchmark_id"), "benchmark_id", "downstream_benchmark")
    dataset_version = _require_non_empty_string(bundle.get("dataset_version"), "dataset_version")
    release = _require_mapping(bundle.get("release"), "release")
    _require_exact_keys(release, {"release_id", "pack_path", "pack_sha256", "pack_byte_count"}, "release")
    _validate_release_id(release.get("release_id"), dataset_version, "release.release_id")
    _validate_artifact_filename(_require_non_empty_string(release.get("pack_path"), "release.pack_path"), "release.pack_path")
    _validate_plain_sha256(release.get("pack_sha256"), "release.pack_sha256")
    _require_int(release.get("pack_byte_count"), "release.pack_byte_count")
    _validate_benchmark_protocol(bundle.get("protocol"))
    claims = _require_mapping(bundle.get("claims"), "claims")
    claim_keys = {"changes_release_admission", "proves_causality", "trains_inside_repository"}
    _require_exact_keys(claims, claim_keys, "claims")
    for key in claim_keys:
        if claims.get(key) is not False:
            raise ContractValidationError(f"claims.{key} must be false")


def validate_downstream_benchmark_observation_record(record: Mapping[str, Any]) -> None:
    _validate_benchmark_observation_fields(record, schema_version="downstream_benchmark_observation_v1")


def validate_downstream_benchmark_result_record(record: Mapping[str, Any]) -> None:
    result = _require_mapping(record, "downstream_benchmark_result")
    base_keys = _benchmark_observation_keys()
    _require_exact_keys(result, base_keys | {"comparison", "decision"}, "downstream_benchmark_result")
    if result.get("schema_version") != "downstream_benchmark_result_v1":
        raise ContractValidationError("schema_version is unsupported")
    decision = _require_mapping(result.get("decision"), "decision")
    _require_exact_keys(decision, {"status", "reasons"}, "decision")
    status = _require_non_empty_string(decision.get("status"), "decision.status")
    if status not in DOWNSTREAM_BENCHMARK_STATUSES:
        raise ContractValidationError("decision.status is unsupported")
    reasons = _require_non_empty_string_sequence(decision.get("reasons"), "decision.reasons")
    if status == "insufficient_evidence":
        _validate_benchmark_identity_fields(result)
        if result.get("evaluation_seed_ids") != [] or result.get("evaluation_sample_count") != 0:
            raise ContractValidationError("insufficient_evidence evaluation identity must be empty")
        if result.get("arms") is not None or result.get("comparison") is not None:
            raise ContractValidationError("insufficient_evidence arms and comparison must be null")
        if len(reasons) != 1 or reasons[0] not in DOWNSTREAM_RESULT_REASON_CODES:
            raise ContractValidationError("insufficient_evidence reason is unsupported")
        return
    _validate_benchmark_observation_fields(result, schema_version="downstream_benchmark_result_v1", allow_result_keys=True)
    comparison = _require_mapping(result.get("comparison"), "comparison")
    _require_exact_keys(comparison, {"primary_metric", "absolute_delta", "relative_delta"}, "comparison")
    _require_non_empty_string(comparison.get("primary_metric"), "comparison.primary_metric")
    if not math.isfinite(_require_number(comparison.get("absolute_delta"), "comparison.absolute_delta")):
        raise ContractValidationError("comparison.absolute_delta must be finite")
    relative = comparison.get("relative_delta")
    if relative is not None and not math.isfinite(_require_number(relative, "comparison.relative_delta")):
        raise ContractValidationError("comparison.relative_delta must be finite")


def _benchmark_observation_keys() -> set[str]:
    return {"schema_version", "benchmark_id", "dataset_version", "release_id", "release_pack_sha256", "benchmark_suite_id", "benchmark_suite_version", "evaluation_seed_ids", "evaluation_sample_count", "arms"}


def _validate_benchmark_observation_fields(record: Mapping[str, Any], *, schema_version: str, allow_result_keys: bool = False) -> None:
    observation = _require_mapping(record, "downstream_benchmark_observation")
    if not allow_result_keys:
        _require_exact_keys(observation, _benchmark_observation_keys(), "downstream_benchmark_observation")
    if observation.get("schema_version") != schema_version:
        raise ContractValidationError("schema_version is unsupported")
    dataset_version = _validate_benchmark_identity_fields(observation)
    _validate_release_id(observation.get("release_id"), dataset_version, "release_id")
    seeds = _require_sequence(observation.get("evaluation_seed_ids"), "evaluation_seed_ids")
    if not seeds:
        raise ContractValidationError("evaluation_seed_ids must not be empty")
    seen: set[str] = set()
    for index, seed in enumerate(seeds):
        value = _require_non_empty_string(seed, f"evaluation_seed_ids.{index}")
        if value in seen:
            raise ContractValidationError("evaluation_seed_ids must be unique")
        seen.add(value)
    _require_positive_int(observation.get("evaluation_sample_count"), "evaluation_sample_count")
    arms = _require_mapping(observation.get("arms"), "arms")
    _require_exact_keys(arms, {"baseline", "treatment"}, "arms")
    for arm_name in ("baseline", "treatment"):
        arm = _require_mapping(arms.get(arm_name), f"arms.{arm_name}")
        _require_exact_keys(arm, {"model_alias", "metrics"}, f"arms.{arm_name}")
        alias = _require_non_empty_string(arm.get("model_alias"), f"arms.{arm_name}.model_alias")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", alias):
            raise ContractValidationError(f"arms.{arm_name}.model_alias is unsafe")
        metrics = _require_mapping(arm.get("metrics"), f"arms.{arm_name}.metrics")
        if not metrics:
            raise ContractValidationError(f"arms.{arm_name}.metrics must not be empty")
        for metric_name, raw_value in metrics.items():
            _require_non_empty_string(metric_name, f"arms.{arm_name}.metrics.name")
            value = _require_number(raw_value, f"arms.{arm_name}.metrics.{metric_name}")
            if not math.isfinite(value):
                raise ContractValidationError(f"arms.{arm_name}.metrics.{metric_name} must be finite")


def _validate_benchmark_identity_fields(record: Mapping[str, Any]) -> str:
    _validate_canonical_digest_id(record.get("benchmark_id"), "benchmark_id", "downstream_benchmark")
    dataset_version = _require_non_empty_string(record.get("dataset_version"), "dataset_version")
    _validate_release_id(record.get("release_id"), dataset_version, "release_id")
    _validate_plain_sha256(record.get("release_pack_sha256"), "release_pack_sha256")
    _require_non_empty_string(record.get("benchmark_suite_id"), "benchmark_suite_id")
    _require_non_empty_string(record.get("benchmark_suite_version"), "benchmark_suite_version")
    return dataset_version


def _validate_benchmark_protocol(raw: object) -> None:
    protocol = _require_mapping(raw, "protocol")
    keys = {"protocol_version", "benchmark_suite_id", "benchmark_suite_version", "baseline_arm", "treatment_arm", "primary_metric", "metrics", "result_schema_version"}
    _require_exact_keys(protocol, keys, "protocol")
    if protocol.get("protocol_version") != "external_agent_benchmark_v1" or protocol.get("result_schema_version") != "downstream_benchmark_result_v1":
        raise ContractValidationError("protocol version is unsupported")
    for key in ("benchmark_suite_id", "benchmark_suite_version", "primary_metric"):
        _require_non_empty_string(protocol.get(key), f"protocol.{key}")
    if protocol.get("baseline_arm") != "baseline_without_synthetic_release" or protocol.get("treatment_arm") != "treatment_with_exact_synthetic_release":
        raise ContractValidationError("protocol arms are unsupported")
    metrics = _require_sequence(protocol.get("metrics"), "protocol.metrics")
    if not metrics:
        raise ContractValidationError("protocol.metrics must not be empty")
    names: set[str] = set()
    for index, raw_metric in enumerate(metrics):
        metric = _require_mapping(raw_metric, f"protocol.metrics.{index}")
        _require_exact_keys(metric, {"name", "direction", "minimum", "maximum"}, f"protocol.metrics.{index}")
        name = _require_non_empty_string(metric.get("name"), f"protocol.metrics.{index}.name")
        if name in names:
            raise ContractValidationError("protocol metric names must be unique")
        names.add(name)
        if metric.get("direction") not in {"higher_is_better", "lower_is_better"}:
            raise ContractValidationError(f"protocol.metrics.{index}.direction is unsupported")
        minimum = _require_number(metric.get("minimum"), f"protocol.metrics.{index}.minimum")
        maximum = _require_number(metric.get("maximum"), f"protocol.metrics.{index}.maximum")
        if not math.isfinite(minimum) or not math.isfinite(maximum) or minimum > maximum:
            raise ContractValidationError(f"protocol.metrics.{index} bounds are invalid")
    if protocol.get("primary_metric") not in names:
        raise ContractValidationError("protocol.primary_metric must name a protocol metric")


def _validate_scale_domain_summary(raw: object, *, index: int, expected_domain: str) -> None:
    domain = _require_mapping(raw, f"domains.{index}")
    keys = {"domain_id", "dataset_version", "profile_id", "generation_mode", "classification", "artifacts", "observed", "signals"}
    _require_exact_keys(domain, keys, f"domains.{index}")
    if domain.get("domain_id") != expected_domain:
        raise ContractValidationError("domains must use the fixed supported order")
    for key in ("dataset_version", "profile_id", "generation_mode"):
        _require_non_empty_string(domain.get(key), f"domains.{index}.{key}")
    if domain.get("classification") not in REPRESENTATIVE_SCALE_CLASSIFICATIONS:
        raise ContractValidationError(f"domains.{index}.classification is unsupported")
    artifacts = _require_mapping(domain.get("artifacts"), f"domains.{index}.artifacts")
    required = {"manifest", "quality_report", "evaluation_report", "profile_decision_report", "dataset_release_report", "release_quality_audit"}
    if not required.issubset(artifacts) or set(artifacts) - required - {"review_resolution_report"}:
        raise ContractValidationError(f"domains.{index}.artifacts has invalid keys")
    for name, raw_artifact in artifacts.items():
        artifact = _require_mapping(raw_artifact, f"domains.{index}.artifacts.{name}")
        _require_exact_keys(artifact, {"path", "sha256"}, f"domains.{index}.artifacts.{name}")
        _validate_artifact_filename(_require_non_empty_string(artifact.get("path"), f"domains.{index}.artifacts.{name}.path"), f"domains.{index}.artifacts.{name}.path")
        _validate_plain_sha256(artifact.get("sha256"), f"domains.{index}.artifacts.{name}.sha256")
    observed = _require_mapping(domain.get("observed"), f"domains.{index}.observed")
    observed_keys = {"total_candidates", "accepted", "rejected", "runtime_seconds", "exact_duplicate_count", "exact_duplicate_rate", "heldout_status", "mvp_quality_floor_status", "profile_promotion_status", "dataset_release_status", "release_audit_status", "review_resolution_status"}
    _require_exact_keys(observed, observed_keys, f"domains.{index}.observed")
    for key in ("total_candidates", "accepted", "rejected", "exact_duplicate_count"):
        _require_int(observed.get(key), f"domains.{index}.observed.{key}")
    runtime_seconds = _require_number(observed.get("runtime_seconds"), f"domains.{index}.observed.runtime_seconds")
    if not math.isfinite(runtime_seconds) or runtime_seconds < 0:
        raise ContractValidationError(f"domains.{index}.observed.runtime_seconds is invalid")
    duplicate_rate = _require_number(observed.get("exact_duplicate_rate"), f"domains.{index}.observed.exact_duplicate_rate")
    _validate_rate(duplicate_rate, f"domains.{index}.observed.exact_duplicate_rate")
    if observed.get("accepted") + observed.get("rejected") != observed.get("total_candidates"):
        raise ContractValidationError(f"domains.{index}.observed counts must sum to total_candidates")
    for key in ("heldout_status", "mvp_quality_floor_status", "profile_promotion_status", "dataset_release_status", "release_audit_status"):
        _require_non_empty_string(observed.get(key), f"domains.{index}.observed.{key}")
    review_status = observed.get("review_resolution_status")
    if review_status is not None:
        _require_non_empty_string(review_status, f"domains.{index}.observed.review_resolution_status")
    _validate_unique_vocabulary(_require_sequence(domain.get("signals"), f"domains.{index}.signals"), REPRESENTATIVE_SCALE_SIGNALS, f"domains.{index}.signals")


def _validate_unique_vocabulary(values: Sequence[Any], allowed: set[str], path: str) -> None:
    seen: set[str] = set()
    for index, raw_value in enumerate(values):
        value = _require_non_empty_string(raw_value, f"{path}.{index}")
        if value not in allowed or value in seen:
            raise ContractValidationError(f"{path}.{index} is unsupported or duplicated")
        seen.add(value)


def _validate_safe_input_path(value: str, path: str) -> None:
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if value.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", value) or ".." in parts or "" in parts:
        raise ContractValidationError(f"{path} must be a safe relative path")


def _validate_plain_sha256(raw: object, path: str) -> str:
    value = _require_non_empty_string(raw, path)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ContractValidationError(f"{path} must be a lowercase sha256 digest")
    return value


def _validate_canonical_digest_id(raw: object, path: str, prefix: str) -> None:
    value = _require_non_empty_string(raw, path)
    expected = f"{prefix}:sha256:"
    if not value.startswith(expected):
        raise ContractValidationError(f"{path} must use the {expected} prefix")
    _validate_plain_sha256(value.removeprefix(expected), path)


def _validate_release_id(raw: object, dataset_version: str, path: str) -> None:
    value = _require_non_empty_string(raw, path)
    prefix = f"{dataset_version}:sha256:"
    if not value.startswith(prefix):
        raise ContractValidationError(f"{path} must match dataset_version")
    _validate_plain_sha256(value.removeprefix(prefix), path)


def validate_profile_decision_report_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "profile_decision_report")
    if _contains_raw_secret(record):
        raise ContractValidationError("profile_decision_report contains raw secret material")
    schema_version = _require_non_empty_string(record.get("schema_version"), "schema_version")
    if schema_version != "profile_decision_report_v1":
        raise ContractValidationError("schema_version is unsupported")
    _require_non_empty_string(record.get("dataset_version"), "dataset_version")
    profile = record.get("profile")
    if profile is not None:
        _validate_profile_decision_profile(profile)
    inputs = _require_mapping(record.get("inputs"), "inputs")
    for field in ("manifest_path", "quality_report_path"):
        artifact_name = _require_non_empty_string(inputs.get(field), f"inputs.{field}")
        _validate_artifact_filename(artifact_name, f"inputs.{field}")
    parent_path = inputs.get("parent_comparison_path")
    if parent_path is not None:
        artifact_name = _require_non_empty_string(parent_path, "inputs.parent_comparison_path")
        _validate_artifact_filename(artifact_name, "inputs.parent_comparison_path")
    evaluation_path = inputs.get("evaluation_report_path")
    if evaluation_path is not None:
        artifact_name = _require_non_empty_string(evaluation_path, "inputs.evaluation_report_path")
        _validate_artifact_filename(artifact_name, "inputs.evaluation_report_path")

    observed = _require_mapping(record.get("observed"), "observed")
    for field in (
        "total_candidates",
        "accepted",
        "rejected",
        "exact_duplicate_count",
        "infrastructure_rejection_count",
        "source_policy_rejection_count",
        "profile_slice_count",
    ):
        _require_int(observed.get(field), f"observed.{field}")
    for field in (
        "exact_duplicate_rate",
        "infrastructure_rejection_rate",
        "source_policy_rejection_rate",
    ):
        _require_number(observed.get(field), f"observed.{field}")
    for field in ("success_rate", "executable_rate", "runtime_seconds"):
        value = observed.get(field)
        if value is not None:
            _require_number(value, f"observed.{field}")

    thresholds = _require_mapping(record.get("thresholds"), "thresholds")
    for field in (
        "async_candidate_count",
        "semantic_duplicate_min_candidates",
    ):
        _require_positive_int(thresholds.get(field), f"thresholds.{field}")
    for field in (
        "async_runtime_seconds",
        "semantic_duplicate_exact_rate",
        "mvp_min_success_rate",
        "mvp_min_executable_rate",
        "mvp_max_infrastructure_rejection_rate",
        "mvp_max_source_policy_rejection_rate",
    ):
        _require_number(thresholds.get(field), f"thresholds.{field}")

    decisions = _require_mapping(record.get("decisions"), "decisions")
    for decision_name in (
        "async_orchestration",
        "semantic_duplicate_detection",
        "mvp_quality_floor",
    ):
        _validate_profile_decision(decisions.get(decision_name), f"decisions.{decision_name}")
    _validate_profile_decision(
        decisions.get("profile_promotion"),
        "decisions.profile_promotion",
        allowed_statuses=PROFILE_PROMOTION_STATUSES,
    )
    if "evaluation" in record:
        _validate_profile_decision_evaluation(record.get("evaluation"))


def validate_dataset_release_report_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "dataset_release_report")
    if _contains_raw_secret(record):
        raise ContractValidationError("dataset_release_report contains raw secret material")
    schema_version = _require_non_empty_string(record.get("schema_version"), "schema_version")
    if schema_version != "dataset_release_report_v1":
        raise ContractValidationError("schema_version is unsupported")
    _require_non_empty_string(record.get("dataset_version"), "dataset_version")

    profile = _require_mapping(record.get("profile"), "profile")
    _validate_profile_decision_profile(profile)
    profile_purpose = _require_non_empty_string(
        profile.get("profile_purpose"),
        "profile.profile_purpose",
    )
    if profile_purpose not in RUN_PROFILE_PURPOSES:
        raise ContractValidationError("profile.profile_purpose is unsupported")

    inputs = _require_mapping(record.get("inputs"), "inputs")
    required_inputs = (
        "manifest_path",
        "quality_report_path",
        "evaluation_report_path",
        "profile_decision_report_path",
    )
    for field in required_inputs:
        artifact_name = _require_non_empty_string(inputs.get(field), f"inputs.{field}")
        _validate_artifact_filename(artifact_name, f"inputs.{field}")

    observed = _require_mapping(record.get("observed"), "observed")
    for field in ("accepted", "rejected"):
        _require_int(observed.get(field), f"observed.{field}")
    for field in (
        "success_rate",
        "executable_rate",
        "source_policy_rejection_rate",
    ):
        _validate_rate(_require_number(observed.get(field), f"observed.{field}"), f"observed.{field}")
    for field in (
        "heldout_status",
        "profile_promotion_status",
        "async_orchestration_status",
        "semantic_duplicate_detection_status",
    ):
        _require_non_empty_string(observed.get(field), f"observed.{field}")

    release_completeness = _validate_release_completeness(
        record.get("release_completeness")
    )

    decisions = _require_mapping(record.get("decisions"), "decisions")
    release_decision = _require_mapping(
        decisions.get("dataset_release"),
        "decisions.dataset_release",
    )
    _validate_profile_decision(
        release_decision,
        "decisions.dataset_release",
        allowed_statuses=DATASET_RELEASE_STATUSES,
    )
    if (
        profile_purpose != "release_candidate"
        and release_decision.get("status") == "passed"
    ):
        raise ContractValidationError(
            "profile.profile_purpose must be release_candidate when dataset_release passes"
        )
    if (
        release_decision.get("status") == "passed"
        and release_completeness["decision_status"] != "passed"
    ):
        raise ContractValidationError(
            "release_completeness.decision.status must be passed when dataset_release passes"
        )

    release_artifacts = _require_mapping(record.get("release_artifacts"), "release_artifacts")
    required_release_artifacts = {
        "samples",
        "rejections",
        "quality_report",
        "evaluation_report",
        "profile_decision_report",
    }
    missing = sorted(required_release_artifacts.difference(release_artifacts))
    if missing and release_decision.get("status") != "insufficient_evidence":
        raise ContractValidationError(
            f"release_artifacts missing required keys: {', '.join(missing)}"
        )
    unexpected = sorted(str(key) for key in release_artifacts if key not in required_release_artifacts)
    if unexpected:
        raise ContractValidationError(
            f"release_artifacts contains unsupported keys: {', '.join(unexpected)}"
        )
    for field in sorted(key for key in required_release_artifacts if key in release_artifacts):
        artifact_name = _require_non_empty_string(
            release_artifacts.get(field),
            f"release_artifacts.{field}",
        )
        _validate_artifact_filename(artifact_name, f"release_artifacts.{field}")


def validate_dataset_release_pack_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "dataset_release_pack")
    if _contains_raw_secret(record):
        raise ContractValidationError("dataset_release_pack contains raw secret material")
    schema_version = _require_non_empty_string(record.get("schema_version"), "schema_version")
    if schema_version != "dataset_release_pack_v1":
        raise ContractValidationError("schema_version is unsupported")
    dataset_version = _require_non_empty_string(record.get("dataset_version"), "dataset_version")
    release_id = _require_non_empty_string(record.get("release_id"), "release_id")
    expected_prefix = f"{dataset_version}:sha256:"
    if not release_id.startswith(expected_prefix) or len(release_id) != len(expected_prefix) + 64:
        raise ContractValidationError("release_id must be dataset_version:sha256:<digest>")
    release_digest = release_id.removeprefix(expected_prefix)
    if any(character not in "0123456789abcdef" for character in release_digest):
        raise ContractValidationError("release_id must be dataset_version:sha256:<digest>")

    _validate_profile_decision_profile(record.get("profile"))
    inputs = _require_mapping(record.get("inputs"), "inputs")
    for field in ("manifest_path", "dataset_release_report_path"):
        artifact_name = _require_non_empty_string(inputs.get(field), f"inputs.{field}")
        _validate_artifact_filename(artifact_name, f"inputs.{field}")

    artifacts = _require_mapping(record.get("artifacts"), "artifacts")
    missing = sorted(DATASET_RELEASE_PACK_ARTIFACT_KEYS.difference(artifacts))
    if missing:
        raise ContractValidationError(f"artifacts missing required keys: {', '.join(missing)}")
    unexpected = sorted(str(key) for key in artifacts if key not in DATASET_RELEASE_PACK_ARTIFACT_KEYS)
    if unexpected:
        raise ContractValidationError(
            f"artifacts contains unsupported keys: {', '.join(unexpected)}"
        )
    for key in sorted(DATASET_RELEASE_PACK_ARTIFACT_KEYS):
        artifact = _require_mapping(artifacts.get(key), f"artifacts.{key}")
        path = _require_non_empty_string(artifact.get("path"), f"artifacts.{key}.path")
        _validate_artifact_filename(path, f"artifacts.{key}.path")
        _validate_content_hash(artifact.get("sha256"), f"artifacts.{key}.sha256")
        _require_int(artifact.get("byte_count"), f"artifacts.{key}.byte_count")

    evidence = _require_mapping(record.get("evidence"), "evidence")
    for field in ("accepted", "rejected"):
        _require_int(evidence.get(field), f"evidence.{field}")
    for field in (
        "heldout_status",
        "profile_promotion_status",
        "dataset_release_status",
        "release_completeness_status",
        "async_orchestration_status",
        "semantic_duplicate_detection_status",
    ):
        _require_non_empty_string(evidence.get(field), f"evidence.{field}")

    verification = _require_mapping(record.get("verification"), "verification")
    status = _require_non_empty_string(verification.get("status"), "verification.status")
    if status not in DATASET_RELEASE_PACK_STATUSES:
        raise ContractValidationError("verification.status is unsupported")
    reasons = _require_sequence(verification.get("reasons"), "verification.reasons")
    if not reasons:
        raise ContractValidationError("verification.reasons must contain at least one reason")
    for index, reason in enumerate(reasons):
        _require_non_empty_string(reason, f"verification.reasons.{index}")


def validate_release_quality_audit_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "release_quality_audit")
    if _contains_raw_secret(record):
        raise ContractValidationError("release_quality_audit contains raw secret material")
    schema_version = _require_non_empty_string(record.get("schema_version"), "schema_version")
    if schema_version != "release_quality_audit_v1":
        raise ContractValidationError("schema_version is unsupported")
    _require_non_empty_string(record.get("dataset_version"), "dataset_version")
    _validate_profile_decision_profile(record.get("profile"))

    inputs = _require_mapping(record.get("inputs"), "inputs")
    for field in (
        "manifest_path",
        "quality_report_path",
        "evaluation_report_path",
        "profile_decision_report_path",
        "dataset_release_report_path",
        "samples_path",
        "rejections_path",
    ):
        artifact_name = _require_non_empty_string(inputs.get(field), f"inputs.{field}")
        _validate_artifact_filename(artifact_name, f"inputs.{field}")

    observed = _require_mapping(record.get("observed"), "observed")
    for field in (
        "accepted",
        "rejected",
        "exact_duplicate_count",
        "task_type_count",
        "tool_combination_count",
    ):
        _require_int(observed.get(field), f"observed.{field}")
    for field in (
        "exact_duplicate_rate",
        "largest_task_type_share",
        "largest_tool_combination_share",
    ):
        _validate_rate(
            _require_number(observed.get(field), f"observed.{field}"),
            f"observed.{field}",
        )
    _require_non_empty_string(
        observed.get("release_completeness_status"),
        "observed.release_completeness_status",
    )
    _require_non_empty_string(
        observed.get("semantic_duplicate_detection_status"),
        "observed.semantic_duplicate_detection_status",
    )

    thresholds = _require_mapping(record.get("thresholds"), "thresholds")
    for field in (
        "small_release_watch_accepted_samples",
        "max_duplicate_family_size",
    ):
        _require_positive_int(thresholds.get(field), f"thresholds.{field}")
    for field in (
        "max_largest_task_type_share",
        "max_largest_tool_combination_share",
        "max_exact_duplicate_rate",
    ):
        _validate_rate(
            _require_number(thresholds.get(field), f"thresholds.{field}"),
            f"thresholds.{field}",
        )

    duplicate_family_risks = _require_sequence(
        record.get("duplicate_family_risks"),
        "duplicate_family_risks",
    )
    for index, raw_risk in enumerate(duplicate_family_risks):
        risk = _require_mapping(raw_risk, f"duplicate_family_risks.{index}")
        _validate_content_hash(
            risk.get("family_key"),
            f"duplicate_family_risks.{index}.family_key",
        )
        risk_kind = _require_non_empty_string(
            risk.get("risk_kind"),
            f"duplicate_family_risks.{index}.risk_kind",
        )
        if risk_kind != "same_task_type_and_tool_combination":
            raise ContractValidationError(
                f"duplicate_family_risks.{index}.risk_kind is unsupported"
            )
        risk_level = _require_non_empty_string(
            risk.get("risk_level"),
            f"duplicate_family_risks.{index}.risk_level",
        )
        if risk_level not in {"watch"}:
            raise ContractValidationError(
                f"duplicate_family_risks.{index}.risk_level is unsupported"
            )
        sample_ids = _require_sequence(
            risk.get("sample_ids"),
            f"duplicate_family_risks.{index}.sample_ids",
        )
        if not sample_ids:
            raise ContractValidationError(
                f"duplicate_family_risks.{index}.sample_ids must not be empty"
            )
        for sample_index, sample_id in enumerate(sample_ids):
            _require_non_empty_string(
                sample_id,
                f"duplicate_family_risks.{index}.sample_ids.{sample_index}",
            )
        sample_count = _require_positive_int(
            risk.get("sample_count"),
            f"duplicate_family_risks.{index}.sample_count",
        )
        if sample_count != len(sample_ids):
            raise ContractValidationError(
                f"duplicate_family_risks.{index}.sample_count must equal sample_ids length"
            )
        _require_non_empty_string(
            risk.get("reason"),
            f"duplicate_family_risks.{index}.reason",
        )

    decision = _require_mapping(record.get("decision"), "decision")
    status = _require_non_empty_string(decision.get("status"), "decision.status")
    if status not in RELEASE_QUALITY_AUDIT_STATUSES:
        raise ContractValidationError("decision.status is unsupported")
    reasons = _require_sequence(decision.get("reasons"), "decision.reasons")
    if not reasons:
        raise ContractValidationError("decision.reasons must contain at least one reason")
    for index, reason in enumerate(reasons):
        _require_non_empty_string(reason, f"decision.reasons.{index}")
    triggered_by = _require_sequence(decision.get("triggered_by"), "decision.triggered_by")
    for index, trigger in enumerate(triggered_by):
        _require_non_empty_string(trigger, f"decision.triggered_by.{index}")


def validate_release_review_item_record(record: Mapping[str, Any]) -> None:
    item = _require_mapping(record, "release_review_item")
    if _contains_raw_secret(item):
        raise ContractValidationError("release_review_item contains raw secret material")
    _require_exact_keys(
        item,
        {
            "schema_version",
            "review_item_id",
            "dataset_version",
            "source",
            "risk",
            "created_at",
        },
        "release_review_item",
    )
    if item.get("schema_version") != "release_review_item_v1":
        raise ContractValidationError("schema_version is unsupported")
    dataset_version = _require_non_empty_string(
        item.get("dataset_version"),
        "dataset_version",
    )
    if not SAFE_REVIEW_DATASET_VERSION_RE.fullmatch(dataset_version):
        raise ContractValidationError("dataset_version must be an ASCII-safe identifier")

    source = _require_mapping(item.get("source"), "source")
    _require_exact_keys(source, {"artifact", "audit_status"}, "source")
    if source.get("artifact") != "release_quality_audit.json":
        raise ContractValidationError("source.artifact is unsupported")
    if source.get("audit_status") != "watch":
        raise ContractValidationError("source.audit_status is unsupported")

    risk = _require_mapping(item.get("risk"), "risk")
    _require_exact_keys(risk, {"kind", "level", "reason", "sample_ids"}, "risk")
    risk_kind = _require_non_empty_string(risk.get("kind"), "risk.kind")
    if risk_kind not in RELEASE_REVIEW_RISK_KINDS:
        raise ContractValidationError("risk.kind is unsupported")
    if risk.get("level") != "watch":
        raise ContractValidationError("risk.level is unsupported")
    reason = _require_non_empty_string(risk.get("reason"), "risk.reason")
    sample_ids = _require_sequence(risk.get("sample_ids"), "risk.sample_ids")
    normalized_sample_ids: list[str] = []
    for index, raw_sample_id in enumerate(sample_ids):
        sample_id = _require_non_empty_string(
            raw_sample_id,
            f"risk.sample_ids.{index}",
        )
        if not SAFE_REVIEW_SAMPLE_ID_RE.fullmatch(sample_id):
            raise ContractValidationError(
                f"risk.sample_ids.{index} must be an ASCII-safe sample identifier"
            )
        normalized_sample_ids.append(sample_id)
    if risk_kind != "duplicate_family" and normalized_sample_ids:
        raise ContractValidationError(
            "risk.sample_ids must be empty unless risk.kind is duplicate_family"
        )
    if risk_kind == "duplicate_family" and not normalized_sample_ids:
        raise ContractValidationError(
            "risk.sample_ids must not be empty when risk.kind is duplicate_family"
        )
    if len(set(normalized_sample_ids)) != len(normalized_sample_ids):
        raise ContractValidationError("risk.sample_ids must not contain duplicates")
    _validate_release_review_reason(
        risk_kind=risk_kind,
        reason=reason,
        sample_id_count=len(normalized_sample_ids),
    )

    if item.get("created_at") != "1970-01-01T00:00:00Z":
        raise ContractValidationError("created_at must use the fixed deterministic timestamp")
    review_item_id = _require_non_empty_string(
        item.get("review_item_id"),
        "review_item_id",
    )
    if not REVIEW_ITEM_ID_RE.fullmatch(review_item_id):
        raise ContractValidationError("review_item_id must be a review_item sha256 identifier")
    canonical_payload = {
        "dataset_version": dataset_version,
        "source_artifact": source["artifact"],
        "risk_kind": risk_kind,
        "risk_level": risk["level"],
        "reason": reason,
        "sample_ids": sorted(normalized_sample_ids),
    }
    canonical = json.dumps(
        canonical_payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    expected_id = "review_item:sha256:" + hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()
    if review_item_id != expected_id:
        raise ContractValidationError("review_item_id does not match canonical item evidence")


def _validate_release_review_reason(
    *,
    risk_kind: str,
    reason: str,
    sample_id_count: int,
) -> None:
    if risk_kind == "duplicate_family":
        expected = (
            f"{sample_id_count} accepted samples share the same task type "
            "and tool combination"
        )
        if reason != expected:
            raise ContractValidationError(
                "risk.reason must match canonical duplicate_family evidence"
            )
        return
    pattern = RELEASE_REVIEW_REASON_PATTERNS[risk_kind]
    matched = pattern.fullmatch(reason)
    if matched is None:
        raise ContractValidationError(
            f"risk.reason must match canonical {risk_kind} evidence"
        )
    observed_token, threshold_token = matched.groups()
    if risk_kind == "small_release_size":
        if len(observed_token) > 20 or len(threshold_token) > 20:
            raise ContractValidationError("risk.reason contains oversized integers")
        observed_value = int(observed_token)
        threshold_value = int(threshold_token)
        semantically_valid = observed_value < threshold_value
    else:
        if len(observed_token) > 32 or len(threshold_token) > 32:
            raise ContractValidationError("risk.reason contains oversized numbers")
        observed_value = float(observed_token)
        threshold_value = float(threshold_token)
        semantically_valid = (
            math.isfinite(observed_value)
            and math.isfinite(threshold_value)
            and 0.0 <= observed_value <= 1.0
            and 0.0 <= threshold_value <= 1.0
            and observed_value > threshold_value
        )
    expected = canonical_release_review_reason(
        risk_kind,
        observed_value,
        threshold_value,
    )
    if not semantically_valid or reason != expected:
        raise ContractValidationError(
            f"risk.reason must match canonical {risk_kind} evidence"
        )


def canonical_release_review_reason(
    risk_kind: str,
    observed_value: int | float,
    threshold_value: int | float,
) -> str:
    if risk_kind == "small_release_size":
        return (
            f"accepted {int(observed_value)} is below "
            f"small_release_watch_accepted_samples {int(threshold_value)}"
        )
    if risk_kind == "exact_duplicate_rate":
        return (
            f"exact_duplicate_rate {float(observed_value)} is above "
            f"max_exact_duplicate_rate {float(threshold_value)}"
        )
    if risk_kind == "task_type_concentration":
        return (
            f"largest_task_type_share {float(observed_value)} is above "
            f"max_largest_task_type_share {float(threshold_value)}"
        )
    if risk_kind == "tool_combination_concentration":
        return (
            f"largest_tool_combination_share {float(observed_value)} is above "
            f"max_largest_tool_combination_share {float(threshold_value)}"
        )
    raise ContractValidationError("risk.kind has no canonical direct reason")


def validate_review_decision_record(record: Mapping[str, Any]) -> None:
    decision = _require_mapping(record, "review_decision")
    _require_exact_keys(
        decision,
        {
            "schema_version",
            "review_item_id",
            "outcome",
            "reason_code",
            "review_minutes",
            "reviewer_alias",
            "decided_at",
        },
        "review_decision",
    )
    if decision.get("schema_version") != "review_decision_v1":
        raise ContractValidationError("schema_version is unsupported")
    review_item_id = _require_non_empty_string(
        decision.get("review_item_id"),
        "review_item_id",
    )
    if not REVIEW_ITEM_ID_RE.fullmatch(review_item_id):
        raise ContractValidationError("review_item_id must be a review_item sha256 identifier")
    outcome = _require_non_empty_string(decision.get("outcome"), "outcome")
    if outcome not in REVIEW_DECISION_OUTCOMES:
        raise ContractValidationError("outcome is unsupported")
    reason_code = _require_non_empty_string(
        decision.get("reason_code"),
        "reason_code",
    )
    if reason_code not in REVIEW_DECISION_REASON_CODES:
        raise ContractValidationError("reason_code is unsupported")
    review_minutes = _require_int(
        decision.get("review_minutes"),
        "review_minutes",
    )
    if review_minutes > 480:
        raise ContractValidationError("review_minutes must not exceed 480")
    reviewer_alias = _require_non_empty_string(
        decision.get("reviewer_alias"),
        "reviewer_alias",
    )
    if len(reviewer_alias) > 128 or not REVIEWER_ALIAS_RE.fullmatch(reviewer_alias):
        raise ContractValidationError(
            "reviewer_alias must be an ASCII-safe opaque identifier"
        )
    if _contains_raw_secret(reviewer_alias):
        raise ContractValidationError("reviewer_alias contains unsafe material")
    _validate_utc_timestamp(decision.get("decided_at"), "decided_at")


def validate_review_resolution_report_record(record: Mapping[str, Any]) -> None:
    report = _require_mapping(record, "review_resolution_report")
    if _contains_raw_secret(report):
        raise ContractValidationError(
            "review_resolution_report contains raw secret material"
        )
    _require_exact_keys(
        report,
        {"schema_version", "dataset_version", "inputs", "counts", "decision"},
        "review_resolution_report",
    )
    if report.get("schema_version") != "review_resolution_report_v1":
        raise ContractValidationError("schema_version is unsupported")
    dataset_version = _require_non_empty_string(
        report.get("dataset_version"),
        "dataset_version",
    )
    if not SAFE_REVIEW_DATASET_VERSION_RE.fullmatch(dataset_version):
        raise ContractValidationError("dataset_version must be an ASCII-safe identifier")

    inputs = _require_mapping(report.get("inputs"), "inputs")
    _require_exact_keys(
        inputs,
        {"release_review_queue_path", "review_decisions_path"},
        "inputs",
    )
    for field in ("release_review_queue_path", "review_decisions_path"):
        artifact_name = _require_non_empty_string(inputs.get(field), f"inputs.{field}")
        _validate_artifact_filename(artifact_name, f"inputs.{field}")

    counts = _require_mapping(report.get("counts"), "counts")
    count_fields = {
        "queued",
        "resolved",
        "pending",
        "accepted_risk",
        "confirmed_issue",
        "needs_follow_up",
        "review_minutes",
    }
    _require_exact_keys(counts, count_fields, "counts")
    normalized_counts = {
        field: _require_int(counts.get(field), f"counts.{field}")
        for field in count_fields
    }
    resolved_outcomes = sum(
        normalized_counts[outcome] for outcome in REVIEW_DECISION_OUTCOMES
    )
    if normalized_counts["resolved"] != resolved_outcomes:
        raise ContractValidationError("counts.resolved must equal outcome counts")
    if normalized_counts["review_minutes"] > normalized_counts["resolved"] * 480:
        raise ContractValidationError(
            "counts.review_minutes must not exceed resolved * 480"
        )
    if normalized_counts["queued"] != (
        normalized_counts["resolved"] + normalized_counts["pending"]
    ):
        raise ContractValidationError("counts.queued must equal resolved + pending")

    decision = _require_mapping(report.get("decision"), "decision")
    _require_exact_keys(decision, {"status", "reasons", "triggered_by"}, "decision")
    status = _require_non_empty_string(decision.get("status"), "decision.status")
    if status not in REVIEW_RESOLUTION_STATUSES:
        raise ContractValidationError("decision.status is unsupported")
    _validate_sanitized_review_report_strings(
        decision.get("reasons"),
        "decision.reasons",
    )
    _validate_sanitized_review_report_strings(
        decision.get("triggered_by"),
        "decision.triggered_by",
    )
    _validate_review_resolution_status_counts(status, normalized_counts)


def _validate_review_resolution_status_counts(
    status: str,
    counts: Mapping[str, int],
) -> None:
    if status == "reviewed":
        if counts["queued"] < 1 or counts["pending"] != 0:
            raise ContractValidationError(
                "counts must have a non-empty fully resolved queue when reviewed"
            )
        return
    if status == "pending_review":
        if (
            counts["queued"] < 1
            or counts["resolved"] < 1
            or counts["pending"] < 1
        ):
            raise ContractValidationError(
                "counts must include resolved and pending items when pending_review"
            )
        return
    if counts["resolved"] != 0 or counts["review_minutes"] != 0:
        raise ContractValidationError(
            "counts must not include resolved evidence when insufficient_evidence"
        )


def _validate_sanitized_review_report_strings(raw: object, path: str) -> None:
    values = _require_non_empty_string_sequence(raw, path)
    for index, raw_value in enumerate(values):
        value = _require_non_empty_string(raw_value, f"{path}.{index}")
        if len(value) > 160 or not SAFE_REVIEW_REPORT_TEXT_RE.fullmatch(value):
            raise ContractValidationError(f"{path}.{index} must be sanitized text")


def _validate_utc_timestamp(raw: object, path: str) -> None:
    value = _require_non_empty_string(raw, path)
    if not UTC_TIMESTAMP_RE.fullmatch(value):
        raise ContractValidationError(f"{path} must be a UTC timestamp")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ContractValidationError(f"{path} must be a valid UTC timestamp") from exc


def _validate_release_completeness(raw: object) -> dict[str, str]:
    release_completeness = _require_mapping(raw, "release_completeness")
    thresholds = _require_mapping(
        release_completeness.get("thresholds"),
        "release_completeness.thresholds",
    )
    _require_positive_int(
        thresholds.get("min_accepted_samples"),
        "release_completeness.thresholds.min_accepted_samples",
    )
    _validate_rate(
        _require_number(
            thresholds.get("max_rejection_rate"),
            "release_completeness.thresholds.max_rejection_rate",
        ),
        "release_completeness.thresholds.max_rejection_rate",
    )
    _require_non_empty_string_sequence(
        thresholds.get("required_task_types"),
        "release_completeness.thresholds.required_task_types",
    )
    _require_non_empty_string_sequence(
        thresholds.get("required_tool_combinations"),
        "release_completeness.thresholds.required_tool_combinations",
    )

    observed = _require_mapping(
        release_completeness.get("observed"),
        "release_completeness.observed",
    )
    _require_int(observed.get("accepted"), "release_completeness.observed.accepted")
    _require_int(observed.get("rejected"), "release_completeness.observed.rejected")
    _validate_rate(
        _require_number(
            observed.get("rejection_rate"),
            "release_completeness.observed.rejection_rate",
        ),
        "release_completeness.observed.rejection_rate",
    )
    for field in ("task_types", "tool_combinations"):
        path = f"release_completeness.observed.{field}"
        values = _require_sequence(observed.get(field), path)
        for index, value in enumerate(values):
            _require_non_empty_string(value, f"{path}.{index}")

    decision = _require_mapping(
        release_completeness.get("decision"),
        "release_completeness.decision",
    )
    _validate_profile_decision(
        decision,
        "release_completeness.decision",
        allowed_statuses=RELEASE_COMPLETENESS_STATUSES,
    )
    return {
        "decision_status": str(decision.get("status")),
    }


def validate_evaluation_report_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "evaluation_report")
    if _contains_raw_secret(record):
        raise ContractValidationError("evaluation_report contains raw secret material")
    schema_version = _require_non_empty_string(record.get("schema_version"), "schema_version")
    if schema_version != "evaluation_report_v1":
        raise ContractValidationError("schema_version is unsupported")
    _require_non_empty_string(record.get("dataset_version"), "dataset_version")

    suite = _require_mapping(record.get("suite"), "suite")
    suite_id = _require_non_empty_string(suite.get("suite_id"), "suite.suite_id")
    _require_non_empty_string(suite.get("suite_version"), "suite.suite_version")
    suite_task_count = _require_int(suite.get("task_count"), "suite.task_count")
    suite_domain_id = _evaluation_suite_domain_id(suite, suite_id)
    report_domain_id = _evaluation_report_domain_id(record, suite_id)
    if suite_domain_id != report_domain_id:
        raise ContractValidationError("evaluation_report domain fields must match")

    profile = record.get("profile")
    if profile is not None:
        _validate_profile_decision_profile(profile)
        profile_mapping = _require_mapping(profile, "profile")
        profile_domain = profile_mapping.get("domain")
        if profile_domain is not None:
            normalized_profile_domain = _normalize_domain_id(
                _require_non_empty_string(profile_domain, "profile.domain")
            )
            if normalized_profile_domain != report_domain_id:
                raise ContractValidationError("profile.domain must match evaluation domain")

    inputs = _require_mapping(record.get("inputs"), "inputs")
    for field in ("manifest_path", "quality_report_path"):
        artifact_name = _require_non_empty_string(inputs.get(field), f"inputs.{field}")
        _validate_artifact_filename(artifact_name, f"inputs.{field}")
    parent_path = inputs.get("parent_evaluation_report_path")
    if parent_path is not None:
        artifact_name = _require_non_empty_string(
            parent_path,
            "inputs.parent_evaluation_report_path",
        )
        _validate_artifact_filename(artifact_name, "inputs.parent_evaluation_report_path")

    counts = _require_mapping(record.get("counts"), "counts")
    total = _require_int(counts.get("total"), "counts.total")
    passed = _require_int(counts.get("passed"), "counts.passed")
    failed = _require_int(counts.get("failed"), "counts.failed")
    regressed = _require_int(counts.get("regressed"), "counts.regressed")
    improved = _require_int(counts.get("improved"), "counts.improved")
    unchanged = _require_int(counts.get("unchanged"), "counts.unchanged")
    if passed + failed != total:
        raise ContractValidationError("counts.passed + counts.failed must equal counts.total")
    if regressed + improved + unchanged > total:
        raise ContractValidationError("counts comparison totals must not exceed counts.total")
    if suite_task_count != total:
        raise ContractValidationError("suite.task_count must equal counts.total")

    rates = _require_mapping(record.get("rates"), "rates")
    pass_rate = _require_number(rates.get("pass_rate"), "rates.pass_rate")
    _validate_rate(pass_rate, "rates.pass_rate")

    task_results = _require_sequence(record.get("task_results"), "task_results")
    if len(task_results) != total:
        raise ContractValidationError("task_results length must equal counts.total")
    result_counts = {"passed": 0, "failed": 0}
    seen_task_ids: set[str] = set()
    for index, raw_result in enumerate(task_results):
        result = _require_mapping(raw_result, f"task_results.{index}")
        task_id = _require_non_empty_string(
            result.get("task_id"),
            f"task_results.{index}.task_id",
        )
        if task_id in seen_task_ids:
            raise ContractValidationError(f"task_results.{index}.task_id is duplicated")
        seen_task_ids.add(task_id)
        tags = _require_non_empty_string_sequence(
            result.get("capability_tags"),
            f"task_results.{index}.capability_tags",
        )
        status = _require_non_empty_string(
            result.get("status"),
            f"task_results.{index}.status",
        )
        if status not in EVALUATION_TASK_STATUSES:
            raise ContractValidationError(f"task_results.{index}.status is unsupported")
        result_counts[status] += 1
        failure_cause = result.get("failure_cause")
        if status == "passed":
            if failure_cause is not None:
                raise ContractValidationError(
                    f"task_results.{index}.failure_cause must be null when passed"
                )
        else:
            _require_non_empty_string(failure_cause, f"task_results.{index}.failure_cause")
        for tag_index, tag in enumerate(tags):
            _require_non_empty_string(tag, f"task_results.{index}.capability_tags.{tag_index}")
        expected_outcome = result.get("expected_outcome")
        if expected_outcome is not None:
            outcome = _require_non_empty_string(
                expected_outcome,
                f"task_results.{index}.expected_outcome",
            )
            if outcome not in EVALUATION_EXPECTED_OUTCOMES:
                raise ContractValidationError(
                    f"task_results.{index}.expected_outcome is unsupported"
                )
        observed_failure_cause = result.get("observed_failure_cause")
        if observed_failure_cause is not None:
            _require_non_empty_string(
                observed_failure_cause,
                f"task_results.{index}.observed_failure_cause",
            )
    if result_counts["passed"] != passed or result_counts["failed"] != failed:
        raise ContractValidationError("counts must match task_results statuses")

    _validate_evaluation_capability_slices(record.get("capability_slices"), total=total)
    _validate_evaluation_thresholds(record.get("thresholds"))
    _validate_evaluation_decision(record.get("decision"))


def _evaluation_suite_domain_id(suite: Mapping[str, Any], suite_id: str) -> str:
    raw_domain = suite.get("domain_id")
    if raw_domain is None:
        if suite_id == "contacts_heldout_v1":
            return "contacts_fixture"
        raise ContractValidationError("suite.domain_id is required")
    return _validate_evaluation_domain_id(raw_domain, "suite.domain_id")


def _evaluation_report_domain_id(record: Mapping[str, Any], suite_id: str) -> str:
    raw_domain = record.get("domain")
    if raw_domain is None:
        if suite_id == "contacts_heldout_v1":
            return "contacts_fixture"
        raise ContractValidationError("domain.domain_id is required")
    domain = _require_mapping(raw_domain, "domain")
    return _validate_evaluation_domain_id(domain.get("domain_id"), "domain.domain_id")


def _validate_evaluation_domain_id(raw: object, path: str) -> str:
    domain_id = _normalize_domain_id(_require_non_empty_string(raw, path))
    if domain_id not in EVALUATION_DOMAINS:
        raise ContractValidationError(f"{path} is unsupported")
    return domain_id


def _normalize_domain_id(domain_id: str) -> str:
    return "contacts_fixture" if domain_id == "contacts" else domain_id


def validate_source_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "source_record")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    _require_non_empty_string(record.get("source_id"), "source_id")
    source_kind = _require_non_empty_string(record.get("source_kind"), "source_kind")
    if source_kind not in SOURCE_KINDS:
        raise ContractValidationError(f"source_kind must be one of {sorted(SOURCE_KINDS)}")
    _require_non_empty_string(record.get("origin_reference"), "origin_reference")
    if source_kind == "external":
        _require_non_empty_string(record.get("retrieval_timestamp"), "retrieval_timestamp")
    elif record.get("retrieval_timestamp") is not None:
        _require_non_empty_string(record.get("retrieval_timestamp"), "retrieval_timestamp")
    _validate_content_hash(record.get("content_hash"), "content_hash")
    license_label = _require_non_empty_string(record.get("license_label"), "license_label")
    if license_label not in SOURCE_LICENSE_LABELS:
        raise ContractValidationError(
            f"license_label must be one of {sorted(SOURCE_LICENSE_LABELS)}"
        )
    if not isinstance(record.get("retention_eligible"), bool):
        raise ContractValidationError("retention_eligible must be a bool")
    if not isinstance(record.get("export_eligible"), bool):
        raise ContractValidationError("export_eligible must be a bool")


def validate_license_policy_decision(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "license_policy_decision")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    _require_non_empty_string(record.get("source_id"), "source_id")
    license_label = _require_non_empty_string(record.get("license_label"), "license_label")
    if license_label not in SOURCE_LICENSE_LABELS:
        raise ContractValidationError(
            f"license_label must be one of {sorted(SOURCE_LICENSE_LABELS)}"
        )
    outcome = _require_non_empty_string(record.get("outcome"), "outcome")
    if outcome not in LICENSE_POLICY_OUTCOMES:
        raise ContractValidationError(
            f"outcome must be one of {sorted(LICENSE_POLICY_OUTCOMES)}"
        )
    if outcome != "allowed":
        _require_non_empty_string(record.get("cause"), "cause")
    _require_non_empty_string(record.get("reviewed_by"), "reviewed_by")


def validate_network_policy_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "network_policy")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    if not isinstance(record.get("enabled"), bool):
        raise ContractValidationError("enabled must be a bool")
    allowed_hosts = _require_sequence(record.get("allowed_hosts"), "allowed_hosts")
    for index, host in enumerate(allowed_hosts):
        _require_non_empty_string(host, f"allowed_hosts.{index}")
    _require_int(record.get("request_budget"), "request_budget")
    if not isinstance(record.get("require_source_events"), bool):
        raise ContractValidationError("require_source_events must be a bool")


def validate_fetched_source_request_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "fetched_source_request")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    url = _require_non_empty_string(record.get("url"), "url")
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ContractValidationError("url must use https")
    allowed_hosts = _require_non_empty_string_sequence(
        record.get("allowed_hosts"),
        "allowed_hosts",
    )
    if parsed.hostname not in set(str(host) for host in allowed_hosts):
        raise ContractValidationError("url host must be allowlisted")
    _require_positive_int(record.get("request_budget"), "request_budget")
    timeout_seconds = _require_number(record.get("timeout_seconds"), "timeout_seconds")
    if timeout_seconds <= 0:
        raise ContractValidationError("timeout_seconds must be positive")
    _require_positive_int(record.get("max_bytes"), "max_bytes")
    expected_content_type = _require_non_empty_string(
        record.get("expected_content_type"),
        "expected_content_type",
    )
    if expected_content_type not in SAFE_FETCH_CONTENT_TYPES:
        raise ContractValidationError("expected_content_type is unsupported")
    license_label = _require_non_empty_string(record.get("license_label"), "license_label")
    if license_label not in SOURCE_LICENSE_LABELS:
        raise ContractValidationError(
            f"license_label must be one of {sorted(SOURCE_LICENSE_LABELS)}"
        )
    if not isinstance(record.get("require_source_audit"), bool):
        raise ContractValidationError("require_source_audit must be a bool")


def validate_fetched_source_result_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "fetched_source_result")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    _require_non_empty_string(record.get("source_id"), "source_id")
    _require_non_empty_string(record.get("origin_alias"), "origin_alias")
    _require_non_empty_string(record.get("retrieval_timestamp"), "retrieval_timestamp")
    _validate_content_hash(record.get("content_hash"), "content_hash")
    content_type = _require_non_empty_string(record.get("content_type"), "content_type")
    if content_type not in SAFE_FETCH_CONTENT_TYPES:
        raise ContractValidationError("content_type is unsupported")
    _require_int(record.get("byte_count"), "byte_count")
    outcome = _require_non_empty_string(record.get("policy_outcome"), "policy_outcome")
    if outcome not in {"allowed", "rejected"}:
        raise ContractValidationError("policy_outcome must be allowed or rejected")


def validate_sandbox_policy_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "sandbox_policy")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    _require_non_empty_string(record.get("policy_id"), "policy_id")
    _require_non_empty_string(record.get("filesystem_isolation"), "filesystem_isolation")
    if not isinstance(record.get("generated_code_allowed"), bool):
        raise ContractValidationError("generated_code_allowed must be a bool")
    if not isinstance(record.get("secret_redaction"), bool):
        raise ContractValidationError("secret_redaction must be a bool")


def validate_generated_executable_artifact_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "generated_executable_artifact")
    if _contains_raw_secret(record):
        raise ContractValidationError("generated_executable_artifact contains raw secret material")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    artifact_id = _require_non_empty_string(record.get("artifact_id"), "artifact_id")
    if not ARTIFACT_ID_RE.match(artifact_id):
        raise ContractValidationError("artifact_id must be a snake_case identifier")
    artifact_kind = _require_non_empty_string(record.get("artifact_kind"), "artifact_kind")
    if artifact_kind not in GENERATED_ARTIFACT_KINDS:
        raise ContractValidationError(
            f"artifact_kind must be one of {sorted(GENERATED_ARTIFACT_KINDS)}"
        )
    language = _require_non_empty_string(record.get("language"), "language")
    if language != "python":
        raise ContractValidationError("language must be python")
    _validate_content_hash(record.get("source_hash"), "source_hash")
    _require_non_empty_string(record.get("declared_entrypoint"), "declared_entrypoint")
    _require_non_empty_string(record.get("source_role"), "source_role")
    role_lineage = _require_mapping(record.get("role_lineage"), "role_lineage")
    _validate_lineage_role(role_lineage, "role_lineage")
    _require_non_empty_string(record.get("created_at"), "created_at")
    _validate_content_hash(record.get("sandbox_policy_hash"), "sandbox_policy_hash")


def validate_generated_code_scan_result_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "generated_code_scan_result")
    if _contains_raw_secret(record):
        raise ContractValidationError("generated_code_scan_result contains raw secret material")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    status = _require_non_empty_string(record.get("status"), "status")
    if status not in GENERATED_CODE_SCAN_STATUSES:
        raise ContractValidationError(
            f"status must be one of {sorted(GENERATED_CODE_SCAN_STATUSES)}"
        )
    violations = _require_sequence(record.get("violations"), "violations")
    for index, raw_violation in enumerate(violations):
        violation = _require_mapping(raw_violation, f"violations.{index}")
        _require_non_empty_string(violation.get("category"), f"violations.{index}.category")
        _require_int(violation.get("line_number"), f"violations.{index}.line_number")
        _require_non_empty_string(violation.get("symbol"), f"violations.{index}.symbol")
        if "excerpt" in violation or "source" in violation:
            raise ContractValidationError(f"violations.{index} must not include raw source")
    for index, symbol in enumerate(_require_sequence(record.get("forbidden_symbols"), "forbidden_symbols")):
        _require_non_empty_string(symbol, f"forbidden_symbols.{index}")
    _validate_content_hash(record.get("source_hash"), "source_hash")
    _require_non_empty_string(record.get("scanner_version"), "scanner_version")
    _require_mapping(record.get("redaction_summary"), "redaction_summary")


def validate_sandbox_admission_result_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "sandbox_admission_result")
    if _contains_raw_secret(record):
        raise ContractValidationError("sandbox_admission_result contains raw secret material")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    _require_non_empty_string(record.get("artifact_id"), "artifact_id")
    scan_status = _require_non_empty_string(record.get("scan_status"), "scan_status")
    if scan_status not in GENERATED_CODE_SCAN_STATUSES:
        raise ContractValidationError("scan_status is unsupported")
    _require_non_empty_string(record.get("policy_id"), "policy_id")
    accepted = record.get("accepted")
    if not isinstance(accepted, bool):
        raise ContractValidationError("accepted must be a bool")
    rejection_cause = record.get("rejection_cause")
    if accepted:
        if rejection_cause is not None:
            raise ContractValidationError("rejection_cause must be null when accepted")
    else:
        if rejection_cause != "unsafe_generated_code":
            raise ContractValidationError("rejection_cause must be unsafe_generated_code")
    _require_non_empty_string(record.get("sanitized_reason"), "sanitized_reason")
    audit_path = _require_non_empty_string(record.get("audit_artifact_path"), "audit_artifact_path")
    if "/" in audit_path or "\\" in audit_path:
        raise ContractValidationError("audit_artifact_path must be a relative artifact name")


def validate_sandbox_execution_result_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "sandbox_execution_result")
    if _contains_raw_secret(record):
        raise ContractValidationError("sandbox_execution_result contains raw secret material")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    _require_non_empty_string(record.get("artifact_id"), "artifact_id")
    status = _require_non_empty_string(record.get("status"), "status")
    if status not in SANDBOX_EXECUTION_STATUSES:
        raise ContractValidationError(
            f"status must be one of {sorted(SANDBOX_EXECUTION_STATUSES)}"
        )
    if not isinstance(record.get("timeout"), bool):
        raise ContractValidationError("timeout must be a bool")
    exit_class = _require_non_empty_string(record.get("exit_class"), "exit_class")
    if exit_class not in SANDBOX_EXIT_CLASSES:
        raise ContractValidationError(
            f"exit_class must be one of {sorted(SANDBOX_EXIT_CLASSES)}"
        )
    _validate_content_hash(record.get("stdout_hash"), "stdout_hash")
    _require_int(record.get("stdout_bytes"), "stdout_bytes")
    _validate_content_hash(record.get("stderr_hash"), "stderr_hash")
    _require_int(record.get("stderr_bytes"), "stderr_bytes")
    _require_int(record.get("duration_ms"), "duration_ms")
    error_class = record.get("sanitized_error_class")
    if status == "succeeded":
        if error_class is not None:
            raise ContractValidationError("sanitized_error_class must be null when succeeded")
    else:
        _require_non_empty_string(error_class, "sanitized_error_class")


def validate_source_event_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "source_event")
    if _contains_raw_secret(record):
        raise ContractValidationError("source_event contains raw secret material")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    event_type = _require_non_empty_string(record.get("event_type"), "event_type")
    if event_type not in SOURCE_EVENT_TYPES:
        raise ContractValidationError(
            f"event_type must be one of {sorted(SOURCE_EVENT_TYPES)}"
        )
    _require_non_empty_string(record.get("source_id"), "source_id")
    source_kind = _require_non_empty_string(record.get("source_kind"), "source_kind")
    if source_kind not in SOURCE_KINDS:
        raise ContractValidationError(f"source_kind must be one of {sorted(SOURCE_KINDS)}")
    outcome = _require_non_empty_string(record.get("policy_outcome"), "policy_outcome")
    if outcome not in {"allowed", "rejected"}:
        raise ContractValidationError("policy_outcome must be allowed or rejected")
    _require_non_empty_string(record.get("origin_alias"), "origin_alias")
    _validate_content_hash(record.get("content_hash"), "content_hash")
    license_label = _require_non_empty_string(record.get("license_label"), "license_label")
    if license_label not in SOURCE_LICENSE_LABELS:
        raise ContractValidationError(
            f"license_label must be one of {sorted(SOURCE_LICENSE_LABELS)}"
        )
    license_outcome = _require_non_empty_string(record.get("license_outcome"), "license_outcome")
    if license_outcome not in LICENSE_POLICY_OUTCOMES and license_outcome != "missing":
        raise ContractValidationError("license_outcome is unsupported")
    _validate_content_hash(record.get("source_policy_hash"), "source_policy_hash")
    causes = _require_sequence(record.get("rejection_causes"), "rejection_causes")
    for index, cause in enumerate(causes):
        _require_non_empty_string(cause, f"rejection_causes.{index}")


def validate_contacts_environment_input_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "contacts_environment_input")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    contacts = _require_sequence(record.get("contacts"), "contacts")
    if not contacts:
        raise ContractValidationError("contacts must contain at least one contact")
    seen_names: set[str] = set()
    for index, raw_contact in enumerate(contacts):
        contact = _require_mapping(raw_contact, f"contacts.{index}")
        name = _require_non_empty_string(contact.get("name"), f"contacts.{index}.name")
        if name in seen_names:
            raise ContractValidationError(f"contacts.{index}.name must be unique")
        seen_names.add(name)
        email = _require_non_empty_string(contact.get("email"), f"contacts.{index}.email")
        if "@" not in email:
            raise ContractValidationError(f"contacts.{index}.email must contain @")
    followups = _require_sequence(record.get("followups"), "followups")
    for index, raw_followup in enumerate(followups):
        followup = _require_mapping(raw_followup, f"followups.{index}")
        name = _require_non_empty_string(followup.get("name"), f"followups.{index}.name")
        if name not in seen_names:
            raise ContractValidationError(f"followups.{index}.name must reference a contact")
        _require_non_empty_string(followup.get("note"), f"followups.{index}.note")
        _require_non_empty_string(followup.get("created_at"), f"followups.{index}.created_at")
    _require_non_empty_string(record.get("source_bundle_id"), "source_bundle_id")
    _validate_content_hash(record.get("source_policy_hash"), "source_policy_hash")
    errors = _require_sequence(record.get("validation_errors"), "validation_errors")
    for index, error in enumerate(errors):
        _require_non_empty_string(error, f"validation_errors.{index}")


def validate_mobile_messages_environment_input_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "mobile_messages_environment_input")
    schema_version = _require_non_empty_string(record.get("schema_version"), "schema_version")
    if schema_version != "mobile_messages_environment_input_v1":
        raise ContractValidationError("schema_version is unsupported")

    threads = _require_sequence(record.get("threads"), "threads")
    if not threads:
        raise ContractValidationError("threads must contain at least one thread")
    thread_ids: set[str] = set()
    for index, raw_thread in enumerate(threads):
        thread = _require_mapping(raw_thread, f"threads.{index}")
        thread_id = _require_non_empty_string(
            thread.get("thread_id"),
            f"threads.{index}.thread_id",
        )
        if thread_id in thread_ids:
            raise ContractValidationError(f"threads.{index}.thread_id must be unique")
        thread_ids.add(thread_id)
        _require_non_empty_string(thread.get("participant"), f"threads.{index}.participant")

    messages = _require_sequence(record.get("messages"), "messages")
    if not messages:
        raise ContractValidationError("messages must contain at least one message")
    message_ids: set[str] = set()
    for index, raw_message in enumerate(messages):
        message = _require_mapping(raw_message, f"messages.{index}")
        message_id = _require_non_empty_string(
            message.get("message_id"),
            f"messages.{index}.message_id",
        )
        if message_id in message_ids:
            raise ContractValidationError(f"messages.{index}.message_id must be unique")
        message_ids.add(message_id)
        thread_id = _require_non_empty_string(
            message.get("thread_id"),
            f"messages.{index}.thread_id",
        )
        if thread_id not in thread_ids:
            raise ContractValidationError(
                f"messages.{index}.thread_id must reference a thread"
            )
        _require_non_empty_string(message.get("sender"), f"messages.{index}.sender")
        _require_non_empty_string(message.get("body"), f"messages.{index}.body")
        _require_non_empty_string(
            message.get("received_at"),
            f"messages.{index}.received_at",
        )

    reminders = _require_sequence(record.get("reminders"), "reminders")
    for index, raw_reminder in enumerate(reminders):
        reminder = _require_mapping(raw_reminder, f"reminders.{index}")
        _require_non_empty_string(
            reminder.get("reminder_id"),
            f"reminders.{index}.reminder_id",
        )
        _require_non_empty_string(reminder.get("title"), f"reminders.{index}.title")
        due_at = reminder.get("due_at")
        if due_at is not None:
            _require_non_empty_string(due_at, f"reminders.{index}.due_at")
        source_message_id = reminder.get("source_message_id")
        if source_message_id is not None:
            source_id = _require_non_empty_string(
                source_message_id,
                f"reminders.{index}.source_message_id",
            )
            if source_id not in message_ids:
                raise ContractValidationError(
                    f"reminders.{index}.source_message_id must reference a message"
                )
        _require_non_empty_string(
            reminder.get("created_at"),
            f"reminders.{index}.created_at",
        )

    draft_replies = _require_sequence(record.get("draft_replies"), "draft_replies")
    for index, raw_draft in enumerate(draft_replies):
        draft = _require_mapping(raw_draft, f"draft_replies.{index}")
        _require_non_empty_string(draft.get("draft_id"), f"draft_replies.{index}.draft_id")
        thread_id = _require_non_empty_string(
            draft.get("thread_id"),
            f"draft_replies.{index}.thread_id",
        )
        if thread_id not in thread_ids:
            raise ContractValidationError(
                f"draft_replies.{index}.thread_id must reference a thread"
            )
        _require_non_empty_string(draft.get("body"), f"draft_replies.{index}.body")
        _require_non_empty_string(
            draft.get("created_at"),
            f"draft_replies.{index}.created_at",
        )

    source_bundle_id = record.get("source_bundle_id")
    if source_bundle_id is not None:
        _require_non_empty_string(source_bundle_id, "source_bundle_id")
    source_policy_hash = record.get("source_policy_hash")
    if source_policy_hash is not None:
        _validate_content_hash(source_policy_hash, "source_policy_hash")


def validate_workspace_tasks_environment_input_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "workspace_tasks_environment_input")
    schema_version = _require_non_empty_string(record.get("schema_version"), "schema_version")
    if schema_version != "workspace_tasks_environment_input_v1":
        raise ContractValidationError("schema_version is unsupported")

    projects = _require_sequence(record.get("projects"), "projects")
    if not projects:
        raise ContractValidationError("projects must contain at least one project")
    project_ids: set[str] = set()
    for index, raw_project in enumerate(projects):
        project = _require_mapping(raw_project, f"projects.{index}")
        project_id = _require_non_empty_string(
            project.get("project_id"),
            f"projects.{index}.project_id",
        )
        if project_id in project_ids:
            raise ContractValidationError(f"projects.{index}.project_id must be unique")
        project_ids.add(project_id)
        _require_non_empty_string(project.get("name"), f"projects.{index}.name")
        _require_non_empty_string(project.get("status"), f"projects.{index}.status")

    tasks = _require_sequence(record.get("tasks"), "tasks")
    if not tasks:
        raise ContractValidationError("tasks must contain at least one task")
    task_ids: set[str] = set()
    for index, raw_task in enumerate(tasks):
        task = _require_mapping(raw_task, f"tasks.{index}")
        task_id = _require_non_empty_string(task.get("task_id"), f"tasks.{index}.task_id")
        if task_id in task_ids:
            raise ContractValidationError(f"tasks.{index}.task_id must be unique")
        task_ids.add(task_id)
        project_id = _require_non_empty_string(
            task.get("project_id"),
            f"tasks.{index}.project_id",
        )
        if project_id not in project_ids:
            raise ContractValidationError(
                f"tasks.{index}.project_id must reference a project"
            )
        _require_non_empty_string(task.get("title"), f"tasks.{index}.title")
        _require_non_empty_string(task.get("priority"), f"tasks.{index}.priority")
        _require_non_empty_string(task.get("due_label"), f"tasks.{index}.due_label")
        _require_non_empty_string(task.get("status"), f"tasks.{index}.status")
        _require_non_empty_string(task.get("created_at"), f"tasks.{index}.created_at")

    documents = _require_sequence(record.get("documents"), "documents")
    for index, raw_document in enumerate(documents):
        document = _require_mapping(raw_document, f"documents.{index}")
        _require_non_empty_string(
            document.get("document_id"),
            f"documents.{index}.document_id",
        )
        project_id = _require_non_empty_string(
            document.get("project_id"),
            f"documents.{index}.project_id",
        )
        if project_id not in project_ids:
            raise ContractValidationError(
                f"documents.{index}.project_id must reference a project"
            )
        _require_non_empty_string(document.get("title"), f"documents.{index}.title")
        _require_non_empty_string(document.get("body"), f"documents.{index}.body")

    comments = _require_sequence(record.get("comments"), "comments")
    for index, raw_comment in enumerate(comments):
        comment = _require_mapping(raw_comment, f"comments.{index}")
        _require_non_empty_string(
            comment.get("comment_id"),
            f"comments.{index}.comment_id",
        )
        task_id = _require_non_empty_string(
            comment.get("task_id"),
            f"comments.{index}.task_id",
        )
        if task_id not in task_ids:
            raise ContractValidationError(
                f"comments.{index}.task_id must reference a task"
            )
        _require_non_empty_string(comment.get("body"), f"comments.{index}.body")
        _require_non_empty_string(comment.get("created_at"), f"comments.{index}.created_at")

    source_bundle_id = record.get("source_bundle_id")
    if source_bundle_id is not None:
        _require_non_empty_string(source_bundle_id, "source_bundle_id")
    source_policy_hash = record.get("source_policy_hash")
    if source_policy_hash is not None:
        _validate_content_hash(source_policy_hash, "source_policy_hash")


def validate_adapter_manifest_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "adapter_manifest")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    _require_non_empty_string(record.get("adapter_id"), "adapter_id")
    _require_non_empty_string(record.get("protocol_label"), "protocol_label")
    _require_non_empty_string(record.get("adapter_version"), "adapter_version")
    _validate_adapter_environment(record.get("environment"), "environment")
    _validate_content_hash(record.get("source_policy_hash"), "source_policy_hash")
    operations = _require_non_empty_string_sequence(
        record.get("supported_operations"),
        "supported_operations",
    )
    for index, operation in enumerate(operations):
        if operation not in ADAPTER_OPERATIONS:
            raise ContractValidationError(
                f"supported_operations.{index} must be one of {sorted(ADAPTER_OPERATIONS)}"
            )
    capabilities = _require_mapping(record.get("capabilities"), "capabilities")
    if not isinstance(capabilities.get("reset"), bool):
        raise ContractValidationError("capabilities.reset must be a bool")
    if not isinstance(capabilities.get("checkpoint"), bool):
        raise ContractValidationError("capabilities.checkpoint must be a bool")
    _validate_adapter_tools(record.get("tools"), "tools")
    _require_non_empty_string_sequence(
        record.get("side_effect_classes"),
        "side_effect_classes",
    )
    _require_non_empty_string_sequence(
        record.get("verifier_implications"),
        "verifier_implications",
    )


def validate_adapter_call_request_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "adapter_call_request")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    _require_non_empty_string(record.get("call_id"), "call_id")
    _require_non_empty_string(record.get("adapter_id"), "adapter_id")
    operation = _require_non_empty_string(record.get("operation"), "operation")
    if operation not in ADAPTER_OPERATIONS:
        raise ContractValidationError(f"operation must be one of {sorted(ADAPTER_OPERATIONS)}")
    _require_non_empty_string(record.get("tool_name"), "tool_name")
    _require_mapping(record.get("arguments"), "arguments")


def validate_adapter_call_result_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "adapter_call_result")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    _require_non_empty_string(record.get("call_id"), "call_id")
    _require_non_empty_string(record.get("adapter_id"), "adapter_id")
    _require_non_empty_string(record.get("tool_name"), "tool_name")
    status = _require_non_empty_string(record.get("execution_status"), "execution_status")
    if status not in ADAPTER_EXECUTION_STATUSES:
        raise ContractValidationError(
            f"execution_status must be one of {sorted(ADAPTER_EXECUTION_STATUSES)}"
        )
    _require_mapping(record.get("observation"), "observation")
    _require_mapping(record.get("side_effect_summary"), "side_effect_summary")
    error = record.get("error")
    if status == "succeeded":
        if error is not None:
            raise ContractValidationError("error must be null for succeeded results")
        return
    if error is None:
        raise ContractValidationError("error is required for rejected or failed results")
    _validate_adapter_error(error, "error")


def validate_adapter_lineage_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "adapter_lineage")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    _require_non_empty_string(record.get("adapter_id"), "adapter_id")
    _require_non_empty_string(record.get("protocol_label"), "protocol_label")
    _require_non_empty_string(record.get("adapter_version"), "adapter_version")
    operation = _require_non_empty_string(record.get("operation"), "operation")
    if operation not in ADAPTER_OPERATIONS:
        raise ContractValidationError(f"operation must be one of {sorted(ADAPTER_OPERATIONS)}")
    _require_non_empty_string(record.get("tool_name"), "tool_name")
    _require_non_empty_string(record.get("call_id"), "call_id")
    status = _require_non_empty_string(record.get("execution_status"), "execution_status")
    if status not in ADAPTER_EXECUTION_STATUSES:
        raise ContractValidationError(
            f"execution_status must be one of {sorted(ADAPTER_EXECUTION_STATUSES)}"
        )
    rejection_cause = record.get("rejection_cause")
    if rejection_cause is not None:
        _require_non_empty_string(rejection_cause, "rejection_cause")


def validate_review_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "review_record")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    _require_non_empty_string(record.get("candidate_id"), "candidate_id")
    cause = record.get("cause")
    _require_non_empty_string(cause, "cause")
    if cause not in REJECTION_CAUSES:
        raise ContractValidationError(f"cause must be one of {sorted(REJECTION_CAUSES)}")
    _validate_task(record.get("task"))
    _require_non_empty_string(record.get("uncertainty_reason"), "uncertainty_reason")
    _require_non_empty_string(record.get("source_artifact"), "source_artifact")
    _require_non_empty_string(record.get("created_at"), "created_at")


def validate_capability_gap_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "capability_gap")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    _require_non_empty_string(record.get("candidate_id"), "candidate_id")
    _require_non_empty_string(record.get("policy_id"), "policy_id")
    gap_type = record.get("gap_type")
    _require_non_empty_string(gap_type, "gap_type")
    if gap_type not in CAPABILITY_GAP_TYPES:
        raise ContractValidationError(
            f"gap_type must be one of {sorted(CAPABILITY_GAP_TYPES)}"
        )
    _require_non_empty_string(record.get("tool_name"), "tool_name")
    cause = record.get("cause")
    _require_non_empty_string(cause, "cause")
    if cause not in REJECTION_CAUSES:
        raise ContractValidationError(f"cause must be one of {sorted(REJECTION_CAUSES)}")
    _require_non_empty_string(record.get("message"), "message")
    _require_mapping(record.get("schema_details"), "schema_details")
    if not isinstance(record.get("retry_eligible"), bool):
        raise ContractValidationError("retry_eligible must be a bool")
    _require_mapping(record.get("source_role_lineage"), "source_role_lineage")


def validate_tool_proposal_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "tool_proposal")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    _require_non_empty_string(record.get("tool_name"), "tool_name")
    _require_non_empty_string(record.get("description"), "description")
    _require_mapping(record.get("schema"), "schema")
    _require_non_empty_string(record.get("side_effects"), "side_effects")
    _require_mapping(record.get("required_environment"), "required_environment")
    _require_non_empty_string_sequence(
        record.get("verifier_implications"),
        "verifier_implications",
    )
    _require_non_empty_string_sequence(record.get("safety_notes"), "safety_notes")
    lineage = _require_mapping(record.get("lineage"), "lineage")
    _validate_lineage_role(lineage, "lineage")


def validate_branch_plan_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "branch_plan")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    _require_non_empty_string(record.get("plan_id"), "plan_id")
    max_depth = _require_positive_int(record.get("max_depth"), "max_depth")
    branches = _require_sequence(record.get("branches"), "branches")
    if not branches:
        raise ContractValidationError("branches must contain at least one branch")
    seen: set[str] = set()
    branch_depths: dict[str, int] = {}
    for index, raw_branch in enumerate(branches):
        branch = _require_mapping(raw_branch, f"branches.{index}")
        branch_id = _require_non_empty_string(
            branch.get("branch_id"),
            f"branches.{index}.branch_id",
        )
        if branch_id in seen:
            raise ContractValidationError(f"duplicate branch_id: {branch_id}")
        seen.add(branch_id)

        node_type = _require_non_empty_string(
            branch.get("node_type"),
            f"branches.{index}.node_type",
        )
        if node_type not in BRANCH_NODE_TYPES:
            raise ContractValidationError(
                f"branches.{index}.node_type must be one of {sorted(BRANCH_NODE_TYPES)}"
            )
        parent_id = branch.get("parent_id")
        if parent_id is not None:
            _require_non_empty_string(parent_id, f"branches.{index}.parent_id")
            if parent_id not in seen:
                raise ContractValidationError(
                    f"branches.{index}.parent_id must refer to an earlier branch"
                )
            branch_depth = branch_depths[parent_id] + 1
        else:
            branch_depth = 1
        if branch_depth > max_depth:
            raise ContractValidationError("branch depth exceeds max_depth")
        branch_depths[branch_id] = branch_depth
        _require_non_empty_string(branch.get("condition"), f"branches.{index}.condition")
        _require_non_empty_string(
            branch.get("terminal_outcome"),
            f"branches.{index}.terminal_outcome",
        )
        _require_non_empty_string(
            branch.get("final_response_template"),
            f"branches.{index}.final_response_template",
        )
        _validate_branch_steps(branch.get("steps"), f"branches.{index}.steps")

def validate_branch_outcomes(
    records: Sequence[Any],
    *,
    require_selected_terminal: bool = True,
) -> None:
    outcomes = _require_sequence(records, "branch_outcomes")
    if not outcomes:
        raise ContractValidationError("branch_outcomes must contain at least one outcome")
    has_selected_terminal = False
    for index, raw_outcome in enumerate(outcomes):
        outcome = _require_mapping(raw_outcome, f"branch_outcomes.{index}")
        _require_non_empty_string(
            outcome.get("schema_version"),
            f"branch_outcomes.{index}.schema_version",
        )
        _require_non_empty_string(
            outcome.get("branch_id"),
            f"branch_outcomes.{index}.branch_id",
        )
        if not isinstance(outcome.get("attempted"), bool):
            raise ContractValidationError(f"branch_outcomes.{index}.attempted must be a bool")
        if not isinstance(outcome.get("selected"), bool):
            raise ContractValidationError(f"branch_outcomes.{index}.selected must be a bool")
        if not isinstance(outcome.get("retry_eligible"), bool):
            raise ContractValidationError(f"branch_outcomes.{index}.retry_eligible must be a bool")
        if not isinstance(outcome.get("refinement_eligible"), bool):
            raise ContractValidationError(
                f"branch_outcomes.{index}.refinement_eligible must be a bool"
            )
        raw_status = outcome.get("outcome")
        _require_non_empty_string(raw_status, f"branch_outcomes.{index}.outcome")
        if raw_status not in BRANCH_OUTCOMES:
            raise ContractValidationError(
                f"branch_outcomes.{index}.outcome must be one of {sorted(BRANCH_OUTCOMES)}"
            )
        failure_cause = outcome.get("failure_cause")
        if failure_cause is not None:
            _require_non_empty_string(
                failure_cause,
                f"branch_outcomes.{index}.failure_cause",
            )
        _require_non_empty_string(outcome.get("message"), f"branch_outcomes.{index}.message")
        _require_positive_int(outcome.get("depth"), f"branch_outcomes.{index}.depth")
        _require_sequence(outcome.get("trajectory"), f"branch_outcomes.{index}.trajectory")
        if outcome.get("selected") and raw_status == "accepted":
            has_selected_terminal = True
    if require_selected_terminal and not has_selected_terminal:
        raise ContractValidationError("branch_outcomes must include a selected terminal branch")


def validate_seed_transformation_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "seed_transformation")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    _require_non_empty_string(record.get("transformation_id"), "transformation_id")
    _require_non_empty_string(record.get("source_seed_id"), "source_seed_id")
    _require_non_empty_string(record.get("transformation_type"), "transformation_type")
    target = _require_non_empty_string(
        record.get("target_taxonomy_node"),
        "target_taxonomy_node",
    )
    if target not in TASK_TAXONOMY_NODES:
        raise ContractValidationError(
            f"target_taxonomy_node must be one of {sorted(TASK_TAXONOMY_NODES)}"
        )
    _require_non_empty_string(record.get("capability_target"), "capability_target")
    _require_non_empty_string(record.get("difficulty_movement"), "difficulty_movement")
    lineage = _require_mapping(record.get("lineage"), "lineage")
    _validate_lineage_role(lineage, "lineage")


def validate_task_suggestion_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "task_suggestion")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    _require_non_empty_string(record.get("suggestion_id"), "suggestion_id")
    _require_non_empty_string(record.get("transformation_id"), "transformation_id")
    target = _require_non_empty_string(
        record.get("target_taxonomy_node"),
        "target_taxonomy_node",
    )
    if target not in TASK_TAXONOMY_NODES:
        raise ContractValidationError(
            f"target_taxonomy_node must be one of {sorted(TASK_TAXONOMY_NODES)}"
        )
    _require_non_empty_string(record.get("intent"), "intent")
    _require_non_empty_string_sequence(
        record.get("required_capabilities"),
        "required_capabilities",
    )
    _require_non_empty_string_sequence(record.get("target_tools"), "target_tools")
    _require_mapping(record.get("constraints"), "constraints")
    _require_non_empty_string(record.get("expected_verification"), "expected_verification")
    outcome = _require_non_empty_string(record.get("outcome"), "outcome")
    if outcome not in TASK_SUGGESTION_OUTCOMES:
        raise ContractValidationError(
            f"outcome must be one of {sorted(TASK_SUGGESTION_OUTCOMES)}"
        )
    if outcome == "rejected":
        _require_non_empty_string(record.get("rejection_reason"), "rejection_reason")
    lineage = _require_mapping(record.get("lineage"), "lineage")
    _validate_lineage_role(lineage, "lineage")


def validate_edited_task_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "edited_task")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    _require_non_empty_string(record.get("suggestion_id"), "suggestion_id")
    _require_non_empty_string(record.get("editor_action"), "editor_action")
    has_candidate = "candidate" in record
    has_rejection = "rejection" in record
    if has_candidate == has_rejection:
        raise ContractValidationError("edited_task must contain exactly one candidate or rejection")
    if has_candidate:
        _validate_edited_candidate(record.get("candidate"))
    if has_rejection:
        rejection = _require_mapping(record.get("rejection"), "rejection")
        _require_non_empty_string(rejection.get("cause"), "rejection.cause")
        _require_non_empty_string(rejection.get("message"), "rejection.message")
    lineage = _require_mapping(record.get("lineage"), "lineage")
    _validate_lineage_role(lineage, "lineage")


def validate_refinement_attempt(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "refinement_attempt")
    _require_non_empty_string(record.get("original_candidate_id"), "original_candidate_id")
    _require_positive_int(record.get("attempt_number"), "attempt_number")
    cause = record.get("source_failure_cause")
    _require_non_empty_string(cause, "source_failure_cause")
    if cause not in REJECTION_CAUSES:
        raise ContractValidationError(
            f"source_failure_cause must be one of {sorted(REJECTION_CAUSES)}"
        )
    _require_mapping(record.get("source_failure_details"), "source_failure_details")
    _require_non_empty_string(record.get("critic_diagnosis"), "critic_diagnosis")
    decision = record.get("repair_decision")
    _require_non_empty_string(decision, "repair_decision")
    if decision not in REFINEMENT_DECISIONS:
        raise ContractValidationError(
            f"repair_decision must be one of {sorted(REFINEMENT_DECISIONS)}"
        )
    lineage = _require_mapping(record.get("lineage"), "lineage")
    _validate_lineage_role(lineage, "lineage")
    if decision == "repair_candidate":
        if "revised_candidate" not in record:
            raise ContractValidationError("revised_candidate is required")
        _validate_task(record.get("revised_candidate"))
    elif decision == "repair_policy":
        if "revised_policy" not in record:
            raise ContractValidationError("revised_policy is required")
        _validate_revised_policy(record.get("revised_policy"))


def _validate_environment(raw: object) -> None:
    environment = _require_mapping(raw, "environment")
    _require_non_empty_string(environment.get("id"), "environment.id")
    _require_non_empty_string(environment.get("version"), "environment.version")
    if "reset_recipe" in environment:
        _require_mapping(environment.get("reset_recipe"), "environment.reset_recipe")
    if "source_provenance" in environment:
        _validate_source_provenance(
            environment.get("source_provenance"),
            "environment.source_provenance",
        )


def _validate_tools(raw: object) -> None:
    tools = _require_sequence(raw, "tools")
    if not tools:
        raise ContractValidationError("tools must contain at least one tool")
    for index, raw_tool in enumerate(tools):
        tool = _require_mapping(raw_tool, f"tools.{index}")
        _require_non_empty_string(tool.get("name"), f"tools.{index}.name")
        _require_non_empty_string(tool.get("version"), f"tools.{index}.version")
        _require_mapping(tool.get("schema"), f"tools.{index}.schema")
        _require_non_empty_string(tool.get("side_effects"), f"tools.{index}.side_effects")


def _validate_task(raw: object) -> None:
    task = _require_mapping(raw, "task")
    if "candidate_id" in task:
        _require_non_empty_string(task.get("candidate_id"), "task.candidate_id")
    _require_non_empty_string(task.get("instruction"), "task.instruction")
    _require_mapping(task.get("constraints"), "task.constraints")
    _require_mapping(task.get("difficulty"), "task.difficulty")


def _validate_trajectory(raw: object) -> None:
    trajectory = _require_sequence(raw, "trajectory")
    if not trajectory:
        raise ContractValidationError("trajectory must contain at least one event")
    for index, raw_event in enumerate(trajectory):
        event = _require_mapping(raw_event, f"trajectory.{index}")
        _require_non_empty_string(event.get("type"), f"trajectory.{index}.type")
        event_type = event["type"]
        if event_type == "action":
            _require_non_empty_string(event.get("tool"), f"trajectory.{index}.tool")
            _require_mapping(event.get("arguments"), f"trajectory.{index}.arguments")
        elif event_type == "observation":
            _require_non_empty_string(event.get("tool"), f"trajectory.{index}.tool")
            if "observation" not in event:
                raise ContractValidationError(f"trajectory.{index}.observation is required")
        elif event_type == "final_response":
            _require_non_empty_string(event.get("content"), f"trajectory.{index}.content")
        elif event_type == "state_change":
            _require_non_empty_string(event.get("tool"), f"trajectory.{index}.tool")
            _require_mapping(event.get("change"), f"trajectory.{index}.change")
        else:
            raise ContractValidationError(f"trajectory.{index}.type is unsupported: {event_type}")


def _validate_verifier(raw: object) -> None:
    verifier = _require_mapping(raw, "verifier")
    _require_non_empty_string(verifier.get("id"), "verifier.id")
    _require_non_empty_string(verifier.get("version"), "verifier.version")
    _require_sequence(verifier.get("checks"), "verifier.checks")


def _validate_verification(raw: object) -> None:
    verification = _require_mapping(raw, "verification")
    _require_non_empty_string(verification.get("verifier_id"), "verification.verifier_id")
    _require_non_empty_string(verification.get("version"), "verification.version")
    if not isinstance(verification.get("passed"), bool):
        raise ContractValidationError("verification.passed must be a bool")
    checks = _require_sequence(verification.get("checks"), "verification.checks")
    for index, raw_check in enumerate(checks):
        check = _require_mapping(raw_check, f"verification.checks.{index}")
        _require_non_empty_string(check.get("name"), f"verification.checks.{index}.name")
        if not isinstance(check.get("passed"), bool):
            raise ContractValidationError(f"verification.checks.{index}.passed must be a bool")


def _validate_quality(raw: object) -> None:
    quality = _require_mapping(raw, "quality")
    scores = _require_mapping(quality.get("scores"), "quality.scores")
    for key, value in scores.items():
        _require_non_empty_string(key, "quality.scores key")
        _require_number(value, f"quality.scores.{key}")
    _require_sequence(quality.get("tags"), "quality.tags")
    _require_non_empty_string(quality.get("review_status"), "quality.review_status")


def _validate_lineage(raw: object) -> None:
    lineage = _require_mapping(raw, "lineage")
    seed_ids = _require_sequence(lineage.get("seed_ids"), "lineage.seed_ids")
    if not seed_ids:
        raise ContractValidationError("lineage.seed_ids must contain at least one seed id")
    for index, seed_id in enumerate(seed_ids):
        _require_non_empty_string(seed_id, f"lineage.seed_ids.{index}")

    generator = _require_mapping(lineage.get("generator"), "lineage.generator")
    _validate_lineage_role(generator, "lineage.generator")
    if "solution_policy" in lineage:
        solution_policy = _require_mapping(
            lineage.get("solution_policy"),
            "lineage.solution_policy",
        )
        _validate_lineage_role(solution_policy, "lineage.solution_policy")
    if "refinement" in lineage:
        refinement = _require_mapping(lineage.get("refinement"), "lineage.refinement")
        _require_non_empty_string(
            refinement.get("original_candidate_id"),
            "lineage.refinement.original_candidate_id",
        )
        _require_positive_int(
            refinement.get("attempt_number"),
            "lineage.refinement.attempt_number",
        )
        _require_non_empty_string(
            refinement.get("source_failure_cause"),
            "lineage.refinement.source_failure_cause",
        )
        _require_non_empty_string(
            refinement.get("critic_diagnosis"),
            "lineage.refinement.critic_diagnosis",
        )
        _require_non_empty_string(
            refinement.get("repair_decision"),
            "lineage.refinement.repair_decision",
        )
        _validate_lineage_role(refinement, "lineage.refinement")
    if "branching" in lineage:
        _validate_branch_lineage(lineage.get("branching"))
    if "seed_transformation" in lineage:
        _validate_seed_transformation_lineage(lineage.get("seed_transformation"))
    if "task_suggester" in lineage:
        task_suggester = _require_mapping(lineage.get("task_suggester"), "lineage.task_suggester")
        _validate_lineage_role(task_suggester, "lineage.task_suggester")
    if "task_editor" in lineage:
        task_editor = _require_mapping(lineage.get("task_editor"), "lineage.task_editor")
        _validate_lineage_role(task_editor, "lineage.task_editor")
    if "source_provenance" in lineage:
        _validate_source_provenance(
            lineage.get("source_provenance"),
            "lineage.source_provenance",
        )
    if "adapter" in lineage:
        adapters = _require_sequence(lineage.get("adapter"), "lineage.adapter")
        if not adapters:
            raise ContractValidationError("lineage.adapter must contain at least one record")
        for index, adapter in enumerate(adapters):
            _validate_adapter_lineage_record_at_path(adapter, f"lineage.adapter.{index}")
    if "run_profile" in lineage:
        _validate_run_profile_attribution(
            lineage.get("run_profile"),
            "lineage.run_profile",
        )

    verifier = _require_mapping(lineage.get("verifier"), "lineage.verifier")
    _require_non_empty_string(verifier.get("id"), "lineage.verifier.id")
    _require_non_empty_string(verifier.get("version"), "lineage.verifier.version")


def _validate_lineage_role(raw: Mapping[str, Any], path: str) -> None:
    _require_non_empty_string(raw.get("role"), f"{path}.role")
    _require_non_empty_string(raw.get("provider_host"), f"{path}.provider_host")
    _require_non_empty_string(raw.get("model"), f"{path}.model")
    _require_non_empty_string(raw.get("config_hash"), f"{path}.config_hash")


def _validate_source_provenance(raw: object, path: str) -> None:
    provenance = _require_mapping(raw, path)
    _require_non_empty_string(
        provenance.get("source_bundle_id"),
        f"{path}.source_bundle_id",
    )
    _validate_content_hash(
        provenance.get("source_policy_hash"),
        f"{path}.source_policy_hash",
    )
    _require_non_empty_string_sequence(provenance.get("source_ids"), f"{path}.source_ids")
    source_kinds = _require_non_empty_string_sequence(
        provenance.get("source_kinds"),
        f"{path}.source_kinds",
    )
    for index, source_kind in enumerate(source_kinds):
        if source_kind not in SOURCE_KINDS:
            raise ContractValidationError(
                f"{path}.source_kinds.{index} must be one of {sorted(SOURCE_KINDS)}"
            )
    license_labels = _require_non_empty_string_sequence(
        provenance.get("license_labels"),
        f"{path}.license_labels",
    )
    for index, label in enumerate(license_labels):
        if label not in SOURCE_LICENSE_LABELS:
            raise ContractValidationError(
                f"{path}.license_labels.{index} must be one of {sorted(SOURCE_LICENSE_LABELS)}"
            )
    outcomes = _require_non_empty_string_sequence(
        provenance.get("license_outcomes"),
        f"{path}.license_outcomes",
    )
    for index, outcome in enumerate(outcomes):
        if outcome not in LICENSE_POLICY_OUTCOMES and outcome != "missing":
            raise ContractValidationError(f"{path}.license_outcomes.{index} is unsupported")
    if not isinstance(provenance.get("external_source_eligible"), bool):
        raise ContractValidationError(f"{path}.external_source_eligible must be a bool")
    if "rejection_causes" in provenance:
        causes = _require_sequence(provenance.get("rejection_causes"), f"{path}.rejection_causes")
        for index, cause in enumerate(causes):
            _require_non_empty_string(cause, f"{path}.rejection_causes.{index}")


def _validate_adapter_environment(raw: object, path: str) -> None:
    environment = _require_mapping(raw, path)
    _require_non_empty_string(environment.get("id"), f"{path}.id")
    _require_non_empty_string(environment.get("version"), f"{path}.version")
    _require_mapping(environment.get("reset_recipe"), f"{path}.reset_recipe")


def _validate_adapter_tools(raw: object, path: str) -> None:
    tools = _require_sequence(raw, path)
    if not tools:
        raise ContractValidationError(f"{path} must contain at least one tool")
    seen_names: set[str] = set()
    for index, raw_tool in enumerate(tools):
        tool = _require_mapping(raw_tool, f"{path}.{index}")
        name = _require_non_empty_string(tool.get("name"), f"{path}.{index}.name")
        if name in seen_names:
            raise ContractValidationError(f"{path}.{index}.name must be unique")
        seen_names.add(name)
        _require_non_empty_string(tool.get("version"), f"{path}.{index}.version")
        _require_mapping(tool.get("schema"), f"{path}.{index}.schema")
        _require_non_empty_string(tool.get("side_effects"), f"{path}.{index}.side_effects")
        _require_non_empty_string_sequence(
            tool.get("verifier_implications"),
            f"{path}.{index}.verifier_implications",
        )


def _validate_adapter_error(raw: object, path: str) -> None:
    error = _require_mapping(raw, path)
    _require_non_empty_string(error.get("cause"), f"{path}.cause")
    _require_non_empty_string(error.get("message"), f"{path}.message")
    _require_mapping(error.get("details"), f"{path}.details")


def _validate_adapter_lineage_record_at_path(raw: object, path: str) -> None:
    lineage = _require_mapping(raw, path)
    try:
        validate_adapter_lineage_record(lineage)
    except ContractValidationError as exc:
        raise ContractValidationError(f"{path}.{exc}") from exc


def _validate_branch_steps(raw: object, path: str) -> None:
    steps = _require_sequence(raw, path)
    if not steps:
        raise ContractValidationError(f"{path} must contain at least one step")
    for index, raw_step in enumerate(steps):
        step = _require_mapping(raw_step, f"{path}.{index}")
        _require_non_empty_string(step.get("tool_name"), f"{path}.{index}.tool_name")
        _require_mapping(step.get("arguments"), f"{path}.{index}.arguments")


def _validate_edited_candidate(raw: object) -> None:
    candidate = _require_mapping(raw, "candidate")
    _require_non_empty_string(candidate.get("candidate_id"), "candidate.candidate_id")
    _require_non_empty_string(candidate.get("instruction"), "candidate.instruction")
    _require_mapping(candidate.get("constraints"), "candidate.constraints")
    _require_mapping(candidate.get("difficulty"), "candidate.difficulty")
    _require_non_empty_string(candidate.get("tool_name"), "candidate.tool_name")
    _require_mapping(candidate.get("arguments"), "candidate.arguments")
    _require_non_empty_string(candidate.get("expected_answer"), "candidate.expected_answer")


def _validate_seed_transformation_lineage(raw: object) -> None:
    transformation = _require_mapping(raw, "lineage.seed_transformation")
    _require_non_empty_string(
        transformation.get("schema_version"),
        "lineage.seed_transformation.schema_version",
    )
    _require_non_empty_string(
        transformation.get("transformation_id"),
        "lineage.seed_transformation.transformation_id",
    )
    _require_non_empty_string(
        transformation.get("source_seed_id"),
        "lineage.seed_transformation.source_seed_id",
    )
    _require_non_empty_string(
        transformation.get("transformation_type"),
        "lineage.seed_transformation.transformation_type",
    )
    _require_non_empty_string(
        transformation.get("target_taxonomy_node"),
        "lineage.seed_transformation.target_taxonomy_node",
    )
    _require_non_empty_string(
        transformation.get("capability_target"),
        "lineage.seed_transformation.capability_target",
    )
    _require_non_empty_string(
        transformation.get("difficulty_movement"),
        "lineage.seed_transformation.difficulty_movement",
    )
    lineage = _require_mapping(
        transformation.get("lineage"),
        "lineage.seed_transformation.lineage",
    )
    _validate_lineage_role(lineage, "lineage.seed_transformation.lineage")


def _validate_branch_lineage(raw: object) -> None:
    lineage = _require_mapping(raw, "lineage.branching")
    _require_non_empty_string(lineage.get("schema_version"), "lineage.branching.schema_version")
    _require_non_empty_string(lineage.get("plan_id"), "lineage.branching.plan_id")
    _require_non_empty_string(
        lineage.get("selected_branch_id"),
        "lineage.branching.selected_branch_id",
    )
    _require_positive_int(lineage.get("branch_depth"), "lineage.branching.branch_depth")
    _require_int(lineage.get("fallback_count"), "lineage.branching.fallback_count")
    validate_branch_outcomes(_require_sequence(lineage.get("branch_outcomes"), "lineage.branching.branch_outcomes"))


def _validate_run_profile_metadata(raw: object) -> None:
    profile = _require_mapping(raw, "run_profile")
    allowed_keys = {
        "schema_version",
        "profile_id",
        "generation_mode",
        "domain",
        "profile_purpose",
        "target_candidate_count",
        "config_hash",
        "enabled_features",
        "seed",
        "source",
        "generation_contract",
    }
    unexpected = sorted(str(key) for key in profile if key not in allowed_keys)
    if unexpected:
        raise ContractValidationError(
            f"run_profile contains unsupported keys: {', '.join(unexpected)}"
        )
    schema_version = _require_non_empty_string(
        profile.get("schema_version"),
        "run_profile.schema_version",
    )
    if schema_version not in {"run_profile_v1", "run_profile_v2", "run_profile_v3"}:
        raise ContractValidationError("run_profile.schema_version is unsupported")
    _require_non_empty_string(profile.get("profile_id"), "run_profile.profile_id")
    mode = _require_non_empty_string(
        profile.get("generation_mode"),
        "run_profile.generation_mode",
    )
    if mode not in RUN_PROFILE_GENERATION_MODES:
        raise ContractValidationError("run_profile.generation_mode is unsupported")
    if "profile_purpose" in profile:
        _validate_run_profile_purpose(
            profile.get("profile_purpose"),
            "run_profile.profile_purpose",
        )
    target_count = profile.get("target_candidate_count")
    if target_count is not None:
        _require_positive_int(target_count, "run_profile.target_candidate_count")
    _validate_content_hash(profile.get("config_hash"), "run_profile.config_hash")
    enabled_features = _require_sequence(
        profile.get("enabled_features"),
        "run_profile.enabled_features",
    )
    for index, feature in enumerate(enabled_features):
        feature_name = _require_non_empty_string(
            feature,
            f"run_profile.enabled_features.{index}",
        )
        if feature_name not in RUN_PROFILE_FEATURE_KEYS:
            raise ContractValidationError(
                f"run_profile.enabled_features.{index} is unsupported"
            )
    if "seed" in profile:
        seed = _require_mapping(profile.get("seed"), "run_profile.seed")
        domain = _require_non_empty_string(seed.get("domain"), "run_profile.seed.domain")
        if domain not in {
            "contacts",
            "contacts_fixture",
            "mobile_messages_fixture",
            "workspace_tasks_fixture",
        }:
            raise ContractValidationError("run_profile.seed.domain is unsupported")
    if "source" in profile:
        if schema_version != "run_profile_v2":
            raise ContractValidationError("run_profile.source requires run_profile_v2")
        _validate_run_profile_source_metadata(profile.get("source"))
    if "generation_contract" in profile:
        validate_generation_contract_record(profile.get("generation_contract"))
        contract = _require_mapping(profile.get("generation_contract"), "run_profile.generation_contract")
        if schema_version != "run_profile_v3" or mode != "llm":
            raise ContractValidationError("run_profile.generation_contract requires run_profile_v3 llm")
        if profile.get("profile_purpose") != "benchmark":
            raise ContractValidationError("run_profile.generation_contract requires benchmark purpose")
        if target_count != contract.get("target_candidate_count"):
            raise ContractValidationError("run_profile target and generation contract target mismatch")


def validate_generation_contract_record(raw: object) -> None:
    contract = _require_mapping(raw, "generation_contract")
    keys = {
        "spec_version", "context_policy", "target_candidate_count",
        "generated_candidate_count", "target_fulfilled",
        "representative_eligible", "reason_codes", "grounding_context_hash",
    }
    unexpected = sorted(str(key) for key in contract if key not in keys)
    missing = sorted(key for key in keys if key not in contract)
    if unexpected or missing:
        raise ContractValidationError("generation_contract must contain exact supported keys")
    if contract.get("spec_version") != "domain_generation_spec_v1":
        raise ContractValidationError("generation_contract.spec_version is unsupported")
    if contract.get("context_policy") != "synthetic_fixture":
        raise ContractValidationError("generation_contract.context_policy is unsupported")
    target = _require_positive_int(
        contract.get("target_candidate_count"),
        "generation_contract.target_candidate_count",
    )
    generated = _require_int(
        contract.get("generated_candidate_count"),
        "generation_contract.generated_candidate_count",
    )
    if generated < 0 or generated > target:
        raise ContractValidationError("generation_contract.generated_candidate_count is invalid")
    fulfilled = contract.get("target_fulfilled")
    if not isinstance(fulfilled, bool):
        raise ContractValidationError("generation_contract.target_fulfilled must be a bool")
    if fulfilled != (generated == target):
        raise ContractValidationError("generation_contract.target_fulfilled is inconsistent")
    eligible = contract.get("representative_eligible")
    if not isinstance(eligible, bool):
        raise ContractValidationError("generation_contract.representative_eligible must be a bool")
    allowed_reasons = (
        "profile_contract_not_representative",
        "generation_spec_missing_or_mismatched",
        "context_policy_not_allowed",
        "source_backed_remote_context_not_allowed",
        "target_candidate_count_unfulfilled",
        "generation_evidence_missing",
    )
    reasons = _require_sequence(contract.get("reason_codes"), "generation_contract.reason_codes")
    normalized = [
        _require_non_empty_string(reason, f"generation_contract.reason_codes.{index}")
        for index, reason in enumerate(reasons)
    ]
    if normalized != [reason for reason in allowed_reasons if reason in normalized]:
        raise ContractValidationError("generation_contract.reason_codes are unsupported or unordered")
    if eligible != (fulfilled and not normalized):
        raise ContractValidationError("generation_contract.representative_eligible is inconsistent")
    _validate_content_hash(
        contract.get("grounding_context_hash"),
        "generation_contract.grounding_context_hash",
    )


def _validate_run_profile_source_metadata(raw: object) -> None:
    source = _require_mapping(raw, "run_profile.source")
    allowed_keys = {
        "kind",
        "source_id",
        "content_hash",
        "license_label",
        "source_policy_hash",
    }
    unexpected = sorted(str(key) for key in source if key not in allowed_keys)
    if unexpected:
        raise ContractValidationError(
            f"run_profile.source contains unsupported keys: {', '.join(unexpected)}"
        )
    kind = _require_non_empty_string(source.get("kind"), "run_profile.source.kind")
    if kind not in RUN_PROFILE_SOURCE_KINDS:
        raise ContractValidationError("run_profile.source.kind is unsupported")
    _require_non_empty_string(source.get("source_id"), "run_profile.source.source_id")
    _validate_content_hash(source.get("content_hash"), "run_profile.source.content_hash")
    license_label = _require_non_empty_string(
        source.get("license_label"),
        "run_profile.source.license_label",
    )
    if license_label not in SOURCE_LICENSE_LABELS:
        raise ContractValidationError("run_profile.source.license_label is unsupported")
    _validate_content_hash(
        source.get("source_policy_hash"),
        "run_profile.source.source_policy_hash",
    )


def _validate_run_profile_attribution(raw: object, path: str) -> None:
    attribution = _require_mapping(raw, path)
    if _contains_raw_secret(attribution):
        raise ContractValidationError(f"{path} contains raw secret material")
    allowed_keys = {
        "schema_version",
        "profile_schema_version",
        "profile_id",
        "generation_mode",
        "profile_purpose",
        "config_hash",
        "source",
    }
    unexpected = sorted(str(key) for key in attribution if key not in allowed_keys)
    if unexpected:
        raise ContractValidationError(
            f"{path} contains unsupported keys: {', '.join(unexpected)}"
        )
    schema_version = _require_non_empty_string(
        attribution.get("schema_version"),
        f"{path}.schema_version",
    )
    if schema_version != "run_profile_attribution_v1":
        raise ContractValidationError(f"{path}.schema_version is unsupported")
    profile_schema_version = _require_non_empty_string(
        attribution.get("profile_schema_version"),
        f"{path}.profile_schema_version",
    )
    if profile_schema_version not in {"run_profile_v1", "run_profile_v2", "run_profile_v3"}:
        raise ContractValidationError(f"{path}.profile_schema_version is unsupported")
    _require_non_empty_string(attribution.get("profile_id"), f"{path}.profile_id")
    mode = _require_non_empty_string(
        attribution.get("generation_mode"),
        f"{path}.generation_mode",
    )
    if mode not in RUN_PROFILE_GENERATION_MODES:
        raise ContractValidationError(f"{path}.generation_mode is unsupported")
    if "profile_purpose" in attribution:
        _validate_run_profile_purpose(
            attribution.get("profile_purpose"),
            f"{path}.profile_purpose",
        )
    _validate_content_hash(attribution.get("config_hash"), f"{path}.config_hash")
    if "source" in attribution:
        _validate_run_profile_source_attribution(
            attribution.get("source"),
            f"{path}.source",
        )


def _validate_run_profile_source_attribution(raw: object, path: str) -> None:
    source = _require_mapping(raw, path)
    allowed_keys = {
        "kind",
        "source_id",
        "content_hash",
        "license_label",
        "source_policy_hash",
    }
    unexpected = sorted(str(key) for key in source if key not in allowed_keys)
    if unexpected:
        raise ContractValidationError(
            f"{path} contains unsupported keys: {', '.join(unexpected)}"
        )
    kind = _require_non_empty_string(source.get("kind"), f"{path}.kind")
    if kind not in RUN_PROFILE_SOURCE_KINDS:
        raise ContractValidationError(f"{path}.kind is unsupported")
    _require_non_empty_string(source.get("source_id"), f"{path}.source_id")
    _validate_content_hash(source.get("content_hash"), f"{path}.content_hash")
    license_label = _require_non_empty_string(
        source.get("license_label"),
        f"{path}.license_label",
    )
    if license_label not in SOURCE_LICENSE_LABELS:
        raise ContractValidationError(f"{path}.license_label is unsupported")
    _validate_content_hash(
        source.get("source_policy_hash"),
        f"{path}.source_policy_hash",
    )


def _validate_run_profile_purpose(raw: object, path: str) -> None:
    purpose = _require_non_empty_string(raw, path)
    if purpose not in RUN_PROFILE_PURPOSES:
        raise ContractValidationError(f"{path} is unsupported")


def _validate_profile_decision(
    raw: object,
    path: str,
    *,
    allowed_statuses: set[str] | None = None,
) -> None:
    decision = _require_mapping(raw, path)
    status = _require_non_empty_string(decision.get("status"), f"{path}.status")
    statuses = allowed_statuses or {
        "activate",
        "defer",
        "passed",
        "failed",
        "insufficient_evidence",
    }
    if status not in statuses:
        raise ContractValidationError(f"{path}.status is unsupported")
    reasons = _require_sequence(decision.get("reasons"), f"{path}.reasons")
    if not reasons:
        raise ContractValidationError(f"{path}.reasons must contain at least one reason")
    for index, reason in enumerate(reasons):
        _require_non_empty_string(reason, f"{path}.reasons.{index}")
    triggered_by = _require_sequence(decision.get("triggered_by"), f"{path}.triggered_by")
    for index, trigger in enumerate(triggered_by):
        _require_non_empty_string(trigger, f"{path}.triggered_by.{index}")


def _validate_profile_decision_profile(raw: object) -> None:
    profile = _require_mapping(raw, "profile")
    allowed_keys = {
        "schema_version",
        "profile_id",
        "generation_mode",
        "domain",
        "profile_purpose",
        "target_candidate_count",
        "config_hash",
        "generation_contract",
    }
    unexpected = sorted(str(key) for key in profile if key not in allowed_keys)
    if unexpected:
        raise ContractValidationError(
            f"profile contains unsupported keys: {', '.join(unexpected)}"
        )
    schema_version = _require_non_empty_string(profile.get("schema_version"), "profile.schema_version")
    if schema_version not in {"run_profile_v1", "run_profile_v2", "run_profile_v3"}:
        raise ContractValidationError("profile.schema_version is unsupported")
    _require_non_empty_string(profile.get("profile_id"), "profile.profile_id")
    mode = _require_non_empty_string(profile.get("generation_mode"), "profile.generation_mode")
    if mode not in RUN_PROFILE_GENERATION_MODES:
        raise ContractValidationError("profile.generation_mode is unsupported")
    if "profile_purpose" in profile:
        _validate_run_profile_purpose(
            profile.get("profile_purpose"),
            "profile.profile_purpose",
        )
    target_count = profile.get("target_candidate_count")
    if target_count is not None:
        _require_positive_int(target_count, "profile.target_candidate_count")
    _validate_content_hash(profile.get("config_hash"), "profile.config_hash")
    if "generation_contract" in profile:
        validate_generation_contract_record(profile.get("generation_contract"))
        contract = _require_mapping(profile.get("generation_contract"), "profile.generation_contract")
        if schema_version != "run_profile_v3" or mode != "llm":
            raise ContractValidationError("profile.generation_contract requires run_profile_v3 llm")
        if profile.get("profile_purpose") != "benchmark":
            raise ContractValidationError("profile.generation_contract requires benchmark purpose")
        if target_count != contract.get("target_candidate_count"):
            raise ContractValidationError("profile target and generation contract target mismatch")


def _validate_profile_decision_evaluation(raw: object) -> None:
    evaluation = _require_mapping(raw, "evaluation")
    status = _require_non_empty_string(
        evaluation.get("decision_status"),
        "evaluation.decision_status",
    )
    if status not in EVALUATION_DECISION_STATUSES:
        raise ContractValidationError("evaluation.decision_status is unsupported")
    pass_rate = evaluation.get("heldout_pass_rate")
    if pass_rate is not None:
        _validate_rate(_require_number(pass_rate, "evaluation.heldout_pass_rate"), "evaluation.heldout_pass_rate")
    regression_count = evaluation.get("regression_count")
    if regression_count is not None:
        _require_int(regression_count, "evaluation.regression_count")


def _validate_manifest_artifacts(raw: object) -> None:
    artifacts = _require_mapping(raw, "artifacts")
    for raw_key, raw_value in artifacts.items():
        key = _require_non_empty_string(raw_key, "artifacts key")
        if key not in MANIFEST_ARTIFACT_KEYS:
            raise ContractValidationError(f"artifacts.{key} is unsupported")
        value = _require_non_empty_string(raw_value, f"artifacts.{key}")
        _validate_artifact_filename(value, f"artifacts.{key}")


def _validate_string_count_mapping(raw: object, path: str) -> set[str]:
    values = _require_mapping(raw, path)
    keys: set[str] = set()
    for raw_key, raw_value in values.items():
        key = _require_non_empty_string(raw_key, f"{path} key")
        _require_int(raw_value, f"{path}.{key}")
        keys.add(key)
    return keys


def _validate_evaluation_capability_slices(raw: object, *, total: int) -> None:
    slices = _require_mapping(raw, "capability_slices")
    if not slices and total:
        raise ContractValidationError("capability_slices must not be empty")
    for raw_tag, raw_slice in slices.items():
        tag = _require_non_empty_string(raw_tag, "capability_slices key")
        capability_slice = _require_mapping(raw_slice, f"capability_slices.{tag}")
        slice_total = _require_int(capability_slice.get("total"), f"capability_slices.{tag}.total")
        slice_passed = _require_int(
            capability_slice.get("passed"),
            f"capability_slices.{tag}.passed",
        )
        slice_failed = _require_int(
            capability_slice.get("failed"),
            f"capability_slices.{tag}.failed",
        )
        if slice_passed + slice_failed != slice_total:
            raise ContractValidationError(
                f"capability_slices.{tag}.passed + failed must equal total"
            )
        _validate_rate(
            _require_number(
                capability_slice.get("pass_rate"),
                f"capability_slices.{tag}.pass_rate",
            ),
            f"capability_slices.{tag}.pass_rate",
        )


def _validate_evaluation_thresholds(raw: object) -> None:
    thresholds = _require_mapping(raw, "thresholds")
    _validate_rate(
        _require_number(
            thresholds.get("mvp_min_heldout_pass_rate"),
            "thresholds.mvp_min_heldout_pass_rate",
        ),
        "thresholds.mvp_min_heldout_pass_rate",
    )
    _require_int(thresholds.get("max_regression_count"), "thresholds.max_regression_count")
    capability_thresholds = thresholds.get("min_capability_pass_rates")
    if capability_thresholds is None:
        return
    mapping = _require_mapping(
        capability_thresholds,
        "thresholds.min_capability_pass_rates",
    )
    for raw_capability, raw_minimum in mapping.items():
        capability = _require_non_empty_string(
            raw_capability,
            "thresholds.min_capability_pass_rates key",
        )
        _require_number(
            raw_minimum,
            f"thresholds.min_capability_pass_rates.{capability}",
        )


def _validate_evaluation_decision(raw: object) -> None:
    decision = _require_mapping(raw, "decision")
    status = _require_non_empty_string(decision.get("status"), "decision.status")
    if status not in EVALUATION_DECISION_STATUSES:
        raise ContractValidationError("decision.status is unsupported")
    reasons = _require_sequence(decision.get("reasons"), "decision.reasons")
    if not reasons:
        raise ContractValidationError("decision.reasons must contain at least one reason")
    for index, reason in enumerate(reasons):
        _require_non_empty_string(reason, f"decision.reasons.{index}")
    triggered_by = _require_sequence(decision.get("triggered_by"), "decision.triggered_by")
    for index, trigger in enumerate(triggered_by):
        _require_non_empty_string(trigger, f"decision.triggered_by.{index}")


def _validate_artifact_filename(raw: str, path: str) -> None:
    if (
        "/" in raw
        or "\\" in raw
        or raw in {".", ".."}
        or raw.startswith("~")
    ):
        raise ContractValidationError(f"{path} must be a relative artifact name")


def _require_exact_keys(
    value: Mapping[str, Any],
    allowed_keys: set[str],
    path: str,
) -> None:
    unexpected = sorted(str(key) for key in value if key not in allowed_keys)
    if unexpected:
        raise ContractValidationError(
            f"{path} contains unsupported keys: {', '.join(unexpected)}"
        )
    missing = sorted(key for key in allowed_keys if key not in value)
    if missing:
        raise ContractValidationError(
            f"{path} is missing required keys: {', '.join(missing)}"
        )


def _require_mapping(raw: object, path: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise ContractValidationError(f"{path} must be an object")
    return raw


def _require_sequence(raw: object, path: str) -> Sequence[Any]:
    if isinstance(raw, str) or not isinstance(raw, Sequence):
        raise ContractValidationError(f"{path} must be a list")
    return raw


def _require_non_empty_string_sequence(raw: object, path: str) -> Sequence[Any]:
    values = _require_sequence(raw, path)
    if not values:
        raise ContractValidationError(f"{path} must contain at least one entry")
    for index, value in enumerate(values):
        _require_non_empty_string(value, f"{path}.{index}")
    return values


def _require_non_empty_string(raw: object, path: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ContractValidationError(f"{path} must be a non-empty string")
    return raw


def _require_int(raw: object, path: str) -> int:
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
        raise ContractValidationError(f"{path} must be a non-negative integer")
    return raw


def _require_positive_int(raw: object, path: str) -> int:
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < 1:
        raise ContractValidationError(f"{path} must be a positive integer")
    return raw


def _require_number(raw: object, path: str) -> float:
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        raise ContractValidationError(f"{path} must be a number")
    return float(raw)


def _validate_rate(raw: float, path: str) -> None:
    if (
        not math.isfinite(raw)
        or raw < 0.0
        or raw > 1.0
        or (raw == 0.0 and math.copysign(1.0, raw) < 0.0)
    ):
        raise ContractValidationError(f"{path} must be between 0.0 and 1.0")


def _validate_content_hash(raw: object, path: str) -> None:
    value = _require_non_empty_string(raw, path)
    if not value.startswith("sha256:") or len(value) != 71:
        raise ContractValidationError(f"{path} must be a sha256 content hash")
    digest = value.removeprefix("sha256:")
    if any(character not in "0123456789abcdef" for character in digest):
        raise ContractValidationError(f"{path} must be a sha256 content hash")


def _contains_raw_secret(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            lowered_key = str(key).lower()
            if lowered_key in {"raw_payload", "raw_content", "credentials", "authorization"}:
                return True
            if "api_key" in lowered_key or "secret" in lowered_key:
                return True
            if _contains_raw_secret(nested):
                return True
        return False
    if isinstance(value, Sequence) and not isinstance(value, str):
        return any(_contains_raw_secret(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return (
            "agent_data_api_key" in lowered
            or "authorization:" in lowered
            or "secret-test-key" in lowered
            or "sk-live" in lowered
            or "sk-test" in lowered
        )
    return False


def _contains_runtime_action_unsafe_material(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            lowered_key = str(key).lower()
            if any(
                fragment in lowered_key
                for fragment in (
                    "raw_source",
                    "provider_prompt",
                    "provider_payload",
                    "profile_path",
                    "credential",
                )
            ):
                return True
            if _contains_runtime_action_unsafe_material(nested):
                return True
        return False
    if isinstance(value, Sequence) and not isinstance(value, str):
        return any(_contains_runtime_action_unsafe_material(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return (
            lowered.startswith("/")
            or lowered.startswith("~")
            or ":\\" in lowered
            or "/users/" in lowered
            or "/private/" in lowered
            or "/tmp/" in lowered
            or "authorization:" in lowered
            or "secret-test-key" in lowered
            or "sk-live" in lowered
            or "sk-test" in lowered
        )
    return False


def _validate_revised_policy(raw: object) -> None:
    policy = _require_mapping(raw, "revised_policy")
    _require_non_empty_string(policy.get("policy_id"), "revised_policy.policy_id")
    steps = _require_sequence(policy.get("steps"), "revised_policy.steps")
    if not steps:
        raise ContractValidationError("revised_policy.steps must contain at least one step")
    for index, raw_step in enumerate(steps):
        step = _require_mapping(raw_step, f"revised_policy.steps.{index}")
        _require_non_empty_string(
            step.get("tool_name"),
            f"revised_policy.steps.{index}.tool_name",
        )
        _require_mapping(step.get("arguments"), f"revised_policy.steps.{index}.arguments")
    _require_non_empty_string(
        policy.get("final_response_template"),
        "revised_policy.final_response_template",
    )
