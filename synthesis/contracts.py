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
    "task_editor_rejected",
    "task_suggestion_rejected",
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
}
TASK_SUGGESTION_OUTCOMES = {"accepted", "rejected"}


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

    verifier = _require_mapping(lineage.get("verifier"), "lineage.verifier")
    _require_non_empty_string(verifier.get("id"), "lineage.verifier.id")
    _require_non_empty_string(verifier.get("version"), "lineage.verifier.version")


def _validate_lineage_role(raw: Mapping[str, Any], path: str) -> None:
    _require_non_empty_string(raw.get("role"), f"{path}.role")
    _require_non_empty_string(raw.get("provider_host"), f"{path}.provider_host")
    _require_non_empty_string(raw.get("model"), f"{path}.model")
    _require_non_empty_string(raw.get("config_hash"), f"{path}.config_hash")


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
