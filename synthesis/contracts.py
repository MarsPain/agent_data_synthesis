from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

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
}

REFINEMENT_DECISIONS = {
    "not_repairable",
    "repair_candidate",
    "repair_policy",
}


def validate_candidate_task(task: object) -> CandidateTask:
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
    _require_mapping(record.get("details"), "details")


def validate_manifest_record(record: Mapping[str, Any]) -> None:
    _require_mapping(record, "manifest")
    _require_non_empty_string(record.get("schema_version"), "schema_version")
    _require_non_empty_string(record.get("dataset_version"), "dataset_version")
    parent = record.get("parent_dataset_version")
    if parent is not None:
        _require_non_empty_string(parent, "parent_dataset_version")
    _require_int(record.get("accepted_count"), "accepted_count")
    _require_int(record.get("rejected_count"), "rejected_count")
    _require_mapping(record.get("artifacts"), "artifacts")
    quality = _require_mapping(record.get("quality"), "quality")
    _require_number(quality.get("success_rate"), "quality.success_rate")
    _require_number(quality.get("executable_rate"), "quality.executable_rate")
    _require_sequence(record.get("environment_versions"), "environment_versions")
    _require_sequence(record.get("tool_versions"), "tool_versions")
    _require_sequence(record.get("verifier_versions"), "verifier_versions")
    _require_sequence(record.get("generator_config_hashes"), "generator_config_hashes")
    _require_mapping(record.get("rejection_causes"), "rejection_causes")


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

    verifier = _require_mapping(lineage.get("verifier"), "lineage.verifier")
    _require_non_empty_string(verifier.get("id"), "lineage.verifier.id")
    _require_non_empty_string(verifier.get("version"), "lineage.verifier.version")


def _validate_lineage_role(raw: Mapping[str, Any], path: str) -> None:
    _require_non_empty_string(raw.get("role"), f"{path}.role")
    _require_non_empty_string(raw.get("provider_host"), f"{path}.provider_host")
    _require_non_empty_string(raw.get("model"), f"{path}.model")
    _require_non_empty_string(raw.get("config_hash"), f"{path}.config_hash")


def _require_mapping(raw: object, path: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise ContractValidationError(f"{path} must be an object")
    return raw


def _require_sequence(raw: object, path: str) -> Sequence[Any]:
    if isinstance(raw, str) or not isinstance(raw, Sequence):
        raise ContractValidationError(f"{path} must be a list")
    return raw


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
